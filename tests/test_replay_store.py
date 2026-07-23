import hashlib
import tempfile
import unittest
import os
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock, patch

from main import (
    MASTER_DUEL_STEAM_URI,
    ReplayManager,
    ReplayStore,
    find_master_duel_process,
    launch_master_duel,
    replay_marker_pixels,
    validate_replay_hex,
    wait_for_master_duel_process,
)


VALID = (b"\x01prefix-replaym-payload\xff").hex()


class ReplayStoreTests(unittest.TestCase):
    def test_validate_normalizes_whitespace_and_case(self):
        value = f"  {VALID[:8].upper()}\n{VALID[8:]}  "
        self.assertEqual(validate_replay_hex(value), VALID)

    def test_invalid_replay_is_rejected(self):
        for value in ("", "xyz", "00", "abc"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    validate_replay_hex(value)

    def test_save_deduplicates_identical_packets(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ReplayStore(Path(tmp))
            first = store.save(VALID)
            second = store.save(VALID)
            self.assertTrue(first.created)
            self.assertFalse(second.created)
            self.assertEqual(first.path, second.path)
            self.assertEqual(store.read(first.path), VALID)

    def test_save_deduplicates_normalized_legacy_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ReplayStore(Path(tmp))
            legacy = Path(tmp) / "自定义名称.replay"
            legacy.write_text(f"  {VALID[:10].upper()}\n{VALID[10:]}  ", encoding="ascii")

            saved = store.save(VALID)

            self.assertFalse(saved.created)
            self.assertEqual(saved.path, legacy)
            self.assertEqual(len(store.list()), 1)

    def test_digest_in_filename_does_not_skip_full_content_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ReplayStore(Path(tmp))
            digest = hashlib.sha256(bytes.fromhex(VALID)).hexdigest()[:12]
            misleading = Path(tmp) / f"misleading_{digest}.replay"
            misleading.write_text((b"\x02replaym-other").hex(), encoding="ascii")

            saved = store.save(VALID)

            self.assertTrue(saved.created)
            self.assertNotEqual(saved.path, misleading)
            self.assertEqual(len(store.list()), 2)

    def test_concurrent_saves_create_only_one_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ReplayStore(Path(tmp))
            with ThreadPoolExecutor(max_workers=8) as executor:
                results = list(executor.map(store.save, [VALID] * 16))

            self.assertEqual(sum(result.created for result in results), 1)
            self.assertEqual(len({result.path for result in results}), 1)
            self.assertEqual(len(store.list()), 1)

    def test_list_is_newest_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ReplayStore(Path(tmp))
            old = Path(tmp) / "old.replay"
            new = Path(tmp) / "new.replay"
            old.write_text(VALID, encoding="ascii")
            new.write_text((b"\x02replaym-new").hex(), encoding="ascii")
            os.utime(old, (100, 100))
            os.utime(new, (200, 200))
            self.assertEqual(store.list()[-1].name, "old.replay")

    def test_delete_only_allows_replays_inside_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = ReplayStore(root / "replays")
            replay = store.save(VALID).path
            store.delete(replay)
            self.assertFalse(replay.exists())

            outside = root / "outside.replay"
            outside.write_text(VALID, encoding="ascii")
            with self.assertRaises(ValueError):
                store.delete(outside)
            self.assertTrue(outside.exists())

    def test_rename_uses_friendly_name_and_keeps_deduplication(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ReplayStore(Path(tmp))
            replay = store.save(VALID).path
            renamed = store.rename(replay, "我的决斗.replay")
            self.assertEqual(renamed.name, "我的决斗.replay")
            self.assertTrue(renamed.exists())
            self.assertFalse(store.save(VALID).created)
            self.assertEqual(store.save(VALID).path, renamed)

    def test_rename_rejects_invalid_or_duplicate_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ReplayStore(Path(tmp))
            replay = store.save(VALID).path
            (Path(tmp) / "已有名称.replay").write_text((b"\x02replaym-other").hex(), encoding="ascii")
            for name in ("", "bad/name", "CON", "已有名称"):
                with self.subTest(name=name):
                    with self.assertRaises((ValueError, FileExistsError)):
                        store.rename(replay, name)


class FakeScript:
    def __init__(self):
        self.messages = []

    def post(self, message):
        self.messages.append(message)

class FakeProcess:
    def __init__(self, name, pid=1):
        self.name = name
        self.pid = pid


class FakeDevice:
    def __init__(self, snapshots):
        self.snapshots = list(snapshots)

    def enumerate_processes(self):
        if len(self.snapshots) > 1:
            return self.snapshots.pop(0)
        return self.snapshots[0]


class GameLaunchTests(unittest.TestCase):
    def test_find_master_duel_process_is_case_insensitive(self):
        expected = FakeProcess("MASTERDUEL.EXE", 42)
        device = FakeDevice([[FakeProcess("steam.exe"), expected]])
        self.assertIs(find_master_duel_process(device), expected)

    def test_wait_for_process_retries_until_game_appears(self):
        expected = FakeProcess("masterduel.exe", 42)
        device = FakeDevice([[], [], [expected]])
        with patch("main.time.sleep") as sleep:
            self.assertIs(wait_for_master_duel_process(device, timeout=3, poll_interval=1), expected)
        self.assertEqual(sleep.call_count, 2)

    def test_launch_uses_master_duel_steam_uri_on_windows(self):
        with patch("main.os.name", "nt"), patch("main.os.startfile", create=True) as startfile:
            launch_master_duel()
        startfile.assert_called_once_with(MASTER_DUEL_STEAM_URI)


class ReplayMarkerTests(unittest.TestCase):
    def test_marker_has_padding_symmetry_and_complete_tip(self):
        pixels = replay_marker_pixels()
        self.assertEqual(min(x for x, _ in pixels), 4)
        self.assertEqual(max(x for x, _ in pixels), 13)
        self.assertEqual(min(y for _, y in pixels), 3)
        self.assertEqual(max(y for _, y in pixels), 13)
        self.assertEqual({y for x, y in pixels if x == 13}, {8})
        for x, y in pixels:
            self.assertIn((x, 16 - y), pixels)


class ReplayManagerTests(unittest.TestCase):
    def test_agent_uses_frida_17_module_export_api(self):
        agent_source = (
            Path(__file__).resolve().parents[1] / "agent" / "index.ts"
        ).read_text(encoding="utf-8")

        self.assertNotIn("Module.getExportByName(", agent_source)
        self.assertIn(
            'Process.getModuleByName("user32.dll")',
            agent_source,
        )
        self.assertIn(
            '.assembly("UnityEngine.CoreModule")',
            agent_source,
        )
        self.assertIn('method.name === "Quit"', agent_source)

    def test_game_close_detaches_before_forwarding_window_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            events = []
            manager = ReplayManager(
                ReplayStore(Path(tmp)),
                lambda kind, data=None: events.append((kind, data)),
            )
            manager.process_pid = 1234
            manager.detach = Mock()
            manager.cancel_override = Mock()

            class FakeUser32:
                def __init__(self):
                    self.forwarded = []

                def GetWindowThreadProcessId(self, _hwnd, pid_pointer):
                    pid_pointer._obj.value = 1234
                    return 1

                def SendMessageTimeoutW(
                    self,
                    hwnd,
                    message,
                    wparam,
                    lparam,
                    flags,
                    timeout,
                    result_pointer,
                ):
                    result_pointer._obj.value = 1
                    self.forwarded.append(
                        (hwnd.value, message, wparam, lparam, flags, timeout)
                    )
                    return 1

            fake_user32 = FakeUser32()
            with patch.object(
                __import__("game_bridge").ctypes,
                "windll",
                SimpleNamespace(user32=fake_user32),
            ):
                with patch("game_bridge.time.sleep"):
                    manager._detach_and_forward_game_close(
                        0x123456,
                        0x0112,
                        0xF060,
                    )

            manager.cancel_override.assert_called_once_with(False)
            manager.detach.assert_called_once_with()
            self.assertEqual(
                fake_user32.forwarded,
                [(0x123456, 0x0112, 0xF060, 0, 0x0003, 5000)],
            )
            self.assertEqual(events[-1], ("game_closing", {"pid": 1234}))

    def test_game_close_rejects_window_from_another_process(self):
        with tempfile.TemporaryDirectory() as tmp:
            events = []
            manager = ReplayManager(
                ReplayStore(Path(tmp)),
                lambda kind, data=None: events.append((kind, data)),
            )
            manager.process_pid = 1234
            manager.detach = Mock()

            class FakeUser32:
                @staticmethod
                def GetWindowThreadProcessId(_hwnd, pid_pointer):
                    pid_pointer._obj.value = 9999
                    return 1

            with patch.object(
                __import__("game_bridge").ctypes,
                "windll",
                SimpleNamespace(user32=FakeUser32()),
            ):
                manager._detach_and_forward_game_close(0x123456)

            manager.detach.assert_not_called()
            self.assertEqual(events[-1][0], "error")

    def test_ready_message_records_game_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = ReplayManager(ReplayStore(Path(tmp)))
            manager._on_message(
                {
                    "type": "send",
                    "payload": {
                        "type": "ready",
                        "data": {"version": "v2.7.0_R5", "gameVersion": "2.7.0"},
                    },
                },
                None,
            )
            self.assertTrue(manager._ready_event.is_set())
            self.assertEqual(manager.game_version, "2.7.0")

    def test_fatal_agent_message_unblocks_startup(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = ReplayManager(ReplayStore(Path(tmp)))
            manager._on_message(
                {"type": "send", "payload": {"type": "fatal", "data": "bad Unity version"}},
                None,
            )
            self.assertTrue(manager._ready_event.is_set())
            self.assertEqual(manager._startup_error, "bad Unity version")
            self.assertFalse(manager.attached)

    def test_capture_saves_and_replies_with_original(self):
        with tempfile.TemporaryDirectory() as tmp:
            events = []
            manager = ReplayManager(ReplayStore(Path(tmp)), lambda kind, data=None: events.append((kind, data)))
            manager.script = FakeScript()
            manager._on_message(
                {
                    "type": "send",
                    "payload": {
                        "type": "replay_packet",
                        "data": {"hex": VALID, "replacementAllowed": True},
                    },
                },
                None,
            )
            self.assertEqual(manager.script.messages[-1]["replay"], VALID)
            self.assertEqual(len(manager.store.list()), 1)
            self.assertEqual(events[-1][0], "saved")

    def test_armed_override_is_one_shot_and_does_not_capture_carrier(self):
        with tempfile.TemporaryDirectory() as tmp:
            events = []
            store = ReplayStore(Path(tmp))
            selected = store.save(VALID).path
            carrier = (b"\x03replaym-carrier").hex()
            manager = ReplayManager(store, lambda kind, data=None: events.append((kind, data)))
            manager.script = FakeScript()
            manager.attached = True
            manager.arm_override(selected)
            manager._on_message(
                {
                    "type": "send",
                    "payload": {
                        "type": "replay_packet",
                        "data": {"hex": carrier, "replacementAllowed": True},
                    },
                },
                None,
            )
            self.assertEqual(manager.script.messages[-1]["replay"], VALID)
            self.assertFalse(manager.override_armed)
            self.assertEqual(len(store.list()), 1)
            self.assertNotIn(("loaded", selected), events)

            manager._on_message(
                {"type": "send", "payload": {"type": "replay_replacement_applied"}},
                None,
            )
            self.assertEqual(events[-1], ("loaded", selected))

    def test_armed_override_ignores_live_duel_packet(self):
        with tempfile.TemporaryDirectory() as tmp:
            events = []
            store = ReplayStore(Path(tmp))
            selected = store.save(VALID).path
            live_duel = (b"\x04replaym-live-duel").hex()
            manager = ReplayManager(store, lambda kind, data=None: events.append((kind, data)))
            manager.script = FakeScript()
            manager.attached = True
            manager.arm_override(selected)

            manager._on_message(
                {
                    "type": "send",
                    "payload": {
                        "type": "replay_packet",
                        "data": {
                            "hex": live_duel,
                            "byteLength": len(bytes.fromhex(live_duel)),
                            "replacementAllowed": False,
                        },
                    },
                },
                None,
            )

            self.assertEqual(manager.script.messages[-1]["replay"], live_duel)
            self.assertTrue(manager.override_armed)
            self.assertEqual(len(store.list()), 1)
            self.assertEqual(events[-1][0], "non_replay_packet_ignored")

    def test_rejected_replacement_reports_error_without_loaded_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            events = []
            store = ReplayStore(Path(tmp))
            selected = store.save(VALID).path
            manager = ReplayManager(store, lambda kind, data=None: events.append((kind, data)))
            manager.pending_replacement = selected

            manager._on_message(
                {
                    "type": "send",
                    "payload": {
                        "type": "replay_replacement_rejected",
                        "data": {"error": "system error"},
                    },
                },
                None,
            )

            self.assertIsNone(manager.pending_replacement)
            self.assertEqual(events[-1][0], "error")
            self.assertIn("system error", events[-1][1])
            self.assertNotIn(("loaded", selected), events)

    def test_direct_play_request_arms_override_and_posts_agent_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            events = []
            store = ReplayStore(Path(tmp))
            selected = store.save(VALID).path
            manager = ReplayManager(store, lambda kind, data=None: events.append((kind, data)))
            manager.script = FakeScript()
            manager.attached = True
            manager.request_direct_play(selected, fallback_to_next=True)
            self.assertTrue(manager.override_armed)
            self.assertTrue(manager.direct_pending)
            self.assertEqual(manager.script.messages[-1], {"type": "direct_play", "fallback": True})
            self.assertEqual(events[-1][0], "direct_requested")

    def test_smart_direct_play_falls_back_to_next_when_not_home(self):
        with tempfile.TemporaryDirectory() as tmp:
            events = []
            store = ReplayStore(Path(tmp))
            selected = store.save(VALID).path
            manager = ReplayManager(store, lambda kind, data=None: events.append((kind, data)))
            manager.script = FakeScript()
            manager.attached = True
            manager.request_direct_play(selected, fallback_to_next=True)
            manager._on_message(
                {
                    "type": "send",
                    "payload": {
                        "type": "direct_play_blocked",
                        "data": {"topClass": "DuelClient", "fallback": True},
                    },
                },
                None,
            )
            self.assertTrue(manager.override_armed)
            self.assertFalse(manager.direct_pending)
            self.assertEqual(events[-1][0], "direct_fallback")

    def test_explicit_direct_play_is_cancelled_when_not_home(self):
        with tempfile.TemporaryDirectory() as tmp:
            events = []
            store = ReplayStore(Path(tmp))
            selected = store.save(VALID).path
            manager = ReplayManager(store, lambda kind, data=None: events.append((kind, data)))
            manager.script = FakeScript()
            manager.attached = True
            manager.request_direct_play(selected, fallback_to_next=False)
            manager._on_message(
                {
                    "type": "send",
                    "payload": {
                        "type": "direct_play_blocked",
                        "data": {"topClass": "DuelClient", "fallback": False},
                    },
                },
                None,
            )
            self.assertFalse(manager.override_armed)
            self.assertFalse(manager.direct_pending)
            self.assertEqual(events[-1], ("direct_blocked", "DuelClient"))

    def test_armed_override_can_be_cancelled(self):
        with tempfile.TemporaryDirectory() as tmp:
            events = []
            store = ReplayStore(Path(tmp))
            selected = store.save(VALID).path
            manager = ReplayManager(store, lambda kind, data=None: events.append((kind, data)))
            manager.attached = True
            manager.arm_override(selected)
            manager.cancel_override()
            self.assertFalse(manager.override_armed)
            self.assertEqual(events[-1], ("cancelled", None))


if __name__ == "__main__":
    unittest.main()
