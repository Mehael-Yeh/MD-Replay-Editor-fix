import copy
import struct
import tempfile
import unittest
from pathlib import Path

import lz4.block
import msgpack

from replay_store import ReplayStore, replay_identity


def packet(duel, request_id=50, token="session-a", compression=True):
    payload = msgpack.packb({
        None: "stdClass", "code": 0,
        "res": [[request_id, {"Duel": duel, "Persistence": {"System": {"duel": token}}}, 0, 0]],
    }, use_bin_type=True)
    block = lz4.block.compress(payload, store_size=False, mode="high_compression" if compression else "default")
    return (b"\x01\x02\x00" + struct.pack("<II", len(block) + 4, len(payload)) + block + b"\0" * 4).hex()


DUEL = {
    None: "stdClass", "replaym": "recorded-actions", "RandSeed": 231233232,
    "FirstPlayer": 0, "Deck": [{None: "stdClass", "Main": {"CardIds": [1, 2, 3]}}],
    "life": [8000, 8000], "engver": 80460, "repver": "2.8.0",
    "did": 123, "duel": "session-a", "duel_start_timestamp": 100,
    "name": ["player-a", "player-b"],
}


class ReplayIdentityTests(unittest.TestCase):
    def test_different_playback_requests_reuse_renamed_original_without_rewriting(self):
        other = copy.deepcopy(DUEL)
        other.update(did=999, duel="session-b", duel_start_timestamp=200, name=["new-name", "player-b"])
        original = packet(DUEL)
        captured = packet(dict(reversed(list(other.items()))), 47, "session-b", False)
        self.assertNotEqual(original, captured)
        with tempfile.TemporaryDirectory() as tmp:
            store = ReplayStore(Path(tmp))
            path = Path(tmp) / "自定义旧录像.replay"
            path.write_text(original, encoding="ascii")
            before = path.stat().st_mtime_ns
            saved = store.save(captured)
            self.assertFalse(saved.created)
            self.assertEqual(saved.path, path)
            self.assertEqual(path.read_text(encoding="ascii"), original)
            self.assertEqual(path.stat().st_mtime_ns, before)
            self.assertEqual(len(store.list()), 1)

    def test_different_playback_inputs_are_not_merged(self):
        for key, value in (
            ("replaym", "different-actions"), ("RandSeed", 42),
            ("Deck", [{"Main": {"CardIds": [3, 2, 1]}}]),
            ("FirstPlayer", 1), ("life", [4000, 8000]),
            ("engver", 80461), ("repver", "2.9.0"),
        ):
            with self.subTest(key=key), tempfile.TemporaryDirectory() as tmp:
                store = ReplayStore(Path(tmp))
                store.save(packet(DUEL))
                other = copy.deepcopy(DUEL)
                other[key] = value
                self.assertTrue(store.save(packet(other)).created)

    def test_unknown_or_malformed_packets_fall_back_to_exact_bytes(self):
        raw = bytes.fromhex(packet(DUEL))
        missing_seed = dict(DUEL)
        del missing_seed["RandSeed"]
        for value in (
            b"prefix-replaym", raw[:-1], raw[:7] + struct.pack("<I", 0xFFFFFFFF) + raw[11:],
            raw[:11] + b"replaym" + raw[-4:], bytes.fromhex(packet(missing_seed)),
        ):
            with self.subTest(value=value[:20]):
                self.assertEqual(replay_identity(value.hex()), b"raw\0" + value)


if __name__ == "__main__":
    unittest.main()
