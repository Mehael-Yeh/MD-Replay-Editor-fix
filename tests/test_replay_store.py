import tempfile
import unittest
import os
from pathlib import Path

from main import ReplayManager, ReplayStore, validate_replay_hex


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


class FakeScript:
    def __init__(self):
        self.messages = []

    def post(self, message):
        self.messages.append(message)


class ReplayManagerTests(unittest.TestCase):
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
                {"type": "send", "payload": {"type": "replay_packet", "data": {"hex": VALID}}},
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
                {"type": "send", "payload": {"type": "replay_packet", "data": {"hex": carrier}}},
                None,
            )
            self.assertEqual(manager.script.messages[-1]["replay"], VALID)
            self.assertFalse(manager.override_armed)
            self.assertEqual(len(store.list()), 1)
            self.assertEqual(events[-1], ("loaded", selected))


if __name__ == "__main__":
    unittest.main()
