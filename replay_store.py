"""Validation and persistence for saved Master Duel replay packets."""

from __future__ import annotations

import hashlib
import re
import threading
import struct
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

import lz4.block
import msgpack


REPLAY_MARKER = b"replaym"
HEX_RE = re.compile(r"^[0-9a-fA-F]+$")

# Playback inputs, rather than request IDs, session tokens or player cosmetics.
# replaym alone is insufficient: short duels can have the same action stream.
REPLAY_IDENTITY_FIELDS = (
    "replaym", "RandSeed", "FirstPlayer", "MyID", "MyType", "Type", "Limit",
    "GameMode", "Deck", "life", "Choice", "regulation_id", "LeftTimeMax",
    "TurnTimeMax", "TotalTimeMax", "MaxTurn", "engver", "repver",
)
MAX_REPLAY_PACKET_SIZE = 64 * 1024 * 1024


def _canonical(value):
    if isinstance(value, dict):
        return {key: _canonical(value[key]) for key in sorted(value, key=lambda key: msgpack.packb(key))}
    if isinstance(value, list):
        return [_canonical(item) for item in value]
    return value


def replay_identity(replay_hex: str) -> bytes:
    """Decode the known LZ4/MessagePack response; unknown packets use exact bytes.

    Never rewrite a saved packet. Duel.did, Duel.duel, duel_start_timestamp and
    the surrounding response describe a playback request, not the recording.
    """
    raw = bytes.fromhex(replay_hex)
    try:
        if raw[:3] != b"\x01\x02\x00" or len(raw) < 15:
            return b"raw\0" + raw
        block_size, unpacked_size = struct.unpack_from("<II", raw, 3)
        if (block_size < 4 or len(raw) != block_size + 11
                or raw[-4:] != b"\0" * 4
                or not 0 < unpacked_size <= MAX_REPLAY_PACKET_SIZE):
            return b"raw\0" + raw
        payload = lz4.block.decompress(raw[11:-4], uncompressed_size=unpacked_size)
        if len(payload) != unpacked_size:
            return b"raw\0" + raw
        response = msgpack.unpackb(payload, strict_map_key=False)
        duels = [entry[1]["Duel"] for entry in response["res"]
                 if isinstance(entry, list) and len(entry) > 1
                 and isinstance(entry[1], dict) and "Duel" in entry[1]]
        if len(duels) != 1 or not isinstance(duels[0], dict):
            return b"raw\0" + raw
        duel = duels[0]
        if (not isinstance(duel.get("replaym"), (str, bytes)) or not duel["replaym"]
                or not all(key in duel for key in ("RandSeed", "Deck", "engver", "repver"))):
            return b"raw\0" + raw
        identity = {key: duel[key] for key in REPLAY_IDENTITY_FIELDS if key in duel}
        return b"duel-v1\0" + msgpack.packb(_canonical(identity), use_bin_type=True)
    except (ValueError, TypeError, KeyError, OverflowError, lz4.block.LZ4BlockError):
        return b"raw\0" + raw


def validate_replay_hex(value: str, translator: Optional[Callable[..., str]] = None) -> str:
    tr = translator or (lambda text, **values: text.format(**values))
    value = "".join(value.split()).lower()
    if not value or len(value) % 2 or not HEX_RE.fullmatch(value):
        raise ValueError(tr("文件不是有效的十六进制回放数据"))
    raw = bytes.fromhex(value)
    if REPLAY_MARKER not in raw:
        raise ValueError(tr("文件中未找到 Master Duel 回放标记"))
    return value


@dataclass(frozen=True)
class SavedReplay:
    path: Path
    created: bool


class ReplayStore:
    def __init__(self, directory: Path, translator: Optional[Callable[..., str]] = None):
        self.directory = directory
        self.tr = translator or (lambda text, **values: text.format(**values))
        self._save_lock = threading.RLock()
        self.directory.mkdir(parents=True, exist_ok=True)

    def list(self, sort_by: str = "time", descending: bool = True) -> list[Path]:
        keys = {
            "name": lambda p: p.name.casefold(),
            "time": lambda p: p.stat().st_mtime_ns,
            "size": lambda p: p.stat().st_size,
        }
        # A filename tie-breaker keeps equal sizes/times in a predictable order.
        paths = sorted(self.directory.glob("*.replay"), key=lambda p: (p.name.casefold(), p.name))
        return sorted(paths, key=keys[sort_by], reverse=descending)

    def read(self, path: Path) -> str:
        return validate_replay_hex(path.read_text(encoding="ascii"), self.tr)

    def _checked_path(self, path: Path) -> Path:
        directory = self.directory.resolve()
        target = path.resolve()
        if target.parent != directory or target.suffix.lower() != ".replay":
            raise ValueError(self.tr("只能管理回放保存目录中的 .replay 文件"))
        return target

    def delete(self, path: Path) -> None:
        self._checked_path(path).unlink()

    def rename(self, path: Path, new_name: str) -> Path:
        source = self._checked_path(path)
        name = new_name.strip()
        if name.lower().endswith(".replay"):
            name = name[:-7].rstrip()
        if not name:
            raise ValueError(self.tr("请输入新的回放名称"))
        if any(ord(char) < 32 or char in '<>:"/\\|?*' for char in name):
            raise ValueError(self.tr('名称不能包含以下字符：< > : " / \\ | ? *'))
        if name.endswith((".", " ")):
            raise ValueError(self.tr("名称不能以句点或空格结尾"))
        reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
        if name.upper() in reserved:
            raise ValueError(self.tr("这个名称由 Windows 系统保留，请换一个名称"))

        target = self.directory / f"{name}.replay"
        if target == source:
            return source
        if target.exists():
            raise FileExistsError(self.tr("已经存在名为“{name}”的回放", name=target.name))
        source.rename(target)
        return target

    def _find_duplicate(self, replay_hex: str, digest: str) -> Optional[Path]:
        identity = replay_identity(replay_hex)
        preferred = list(self.directory.glob(f"*_{digest}.replay"))
        preferred_set = set(preferred)
        candidates = preferred + [
            candidate
            for candidate in self.directory.glob("*.replay")
            if candidate not in preferred_set
        ]
        for candidate in candidates:
            try:
                if replay_identity(self.read(candidate)) == identity:
                    return candidate
            except (OSError, ValueError):
                continue
        return None

    def save(self, replay_hex: str) -> SavedReplay:
        replay_hex = validate_replay_hex(replay_hex, self.tr)
        digest = hashlib.sha256(bytes.fromhex(replay_hex)).hexdigest()[:12]
        with self._save_lock:
            existing = self._find_duplicate(replay_hex, digest)
            if existing:
                return SavedReplay(existing, False)

            stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            path = self.directory / f"{stamp}_{digest}.replay"
            suffix = 2
            while path.exists():
                path = self.directory / f"{stamp}_{suffix}_{digest}.replay"
                suffix += 1
            temporary = path.with_suffix(".tmp")
            temporary.write_text(replay_hex, encoding="ascii")
            temporary.replace(path)
            return SavedReplay(path, True)
