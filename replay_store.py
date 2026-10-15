"""Validation and persistence for saved Master Duel replay packets."""

from __future__ import annotations

import hashlib
import os
import stat
import re
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional


REPLAY_MARKER = b"replaym"
HEX_RE = re.compile(r"^[0-9a-fA-F]+$")


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
        # Cache only fingerprints and digests, never replay payloads.
        self._index: dict[Path, tuple[tuple[int, ...], str | None]] = {}
        self._digests: dict[str, set[Path]] = {}

    def list(self) -> list[Path]:
        return [path for path, _ in self.list_entries()]

    def list_entries(self) -> list[tuple[Path, os.stat_result]]:
        """Take one metadata snapshot, tolerating files removed during enumeration."""
        entries = []
        for path in self.directory.glob("*.replay"):
            try:
                info = path.stat()
            except OSError:
                continue
            if stat.S_ISREG(info.st_mode):
                entries.append((path, info))
        return sorted(entries, key=lambda entry: entry[1].st_mtime, reverse=True)

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
        if name.split(".", 1)[0].rstrip().upper() in reserved:
            raise ValueError(self.tr("这个名称由 Windows 系统保留，请换一个名称"))

        target = self.directory / f"{name}.replay"
        if target == source:
            return source
        if target.exists():
            raise FileExistsError(self.tr("已经存在名为“{name}”的回放", name=target.name))
        source.rename(target)
        return target

    @staticmethod
    def _signature(info: os.stat_result) -> tuple[int, ...]:
        return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)

    def _forget(self, path: Path) -> None:
        previous = self._index.pop(path, None)
        if previous is not None and previous[1] is not None:
            bucket = self._digests[previous[1]]
            bucket.discard(path)
            if not bucket:
                del self._digests[previous[1]]

    def _remember(self, path: Path, signature: tuple[int, ...], digest: str | None) -> None:
        self._forget(path)
        self._index[path] = (signature, digest)
        if digest is not None:
            self._digests.setdefault(digest, set()).add(path)

    def warm_index(self, stop: threading.Event | None = None) -> None:
        """Reconcile external edits; unchanged files require metadata reads only.

        Also used before saving, so external additions cannot be missed just because
        a background scan has not run yet. Cold indexing is linear in library size.
        """
        with self._save_lock:
            entries = self.list_entries()
            present = {path for path, _ in entries}
            for path in self._index.keys() - present:
                self._forget(path)
            for path, info in entries:
                if stop is not None and stop.is_set():
                    return
                signature = self._signature(info)
                if path in self._index and self._index[path][0] == signature:
                    continue
                self._forget(path)
                try:
                    try:
                        value = self.read(path)
                        digest = hashlib.sha256(bytes.fromhex(value)).hexdigest()
                    except ValueError:
                        digest = None  # Remember invalid files until their metadata changes.
                    if self._signature(path.stat()) == signature:
                        self._remember(path, signature, digest)
                except OSError:
                    continue  # Retry transient read failures on the next scan.

    def _find_duplicate(self, replay_hex: str, digest: str) -> Optional[Path]:
        self.warm_index()
        for candidate in sorted(self._digests.get(digest, ())):
            try:
                # Never trust the digest (or a digest-looking filename) alone.
                if self.read(candidate) == replay_hex:
                    return candidate
            except (OSError, ValueError):
                pass
            self._forget(candidate)
        return None

    def save(self, replay_hex: str) -> SavedReplay:
        replay_hex = validate_replay_hex(replay_hex, self.tr)
        digest = hashlib.sha256(bytes.fromhex(replay_hex)).hexdigest()
        with self._save_lock:
            existing = self._find_duplicate(replay_hex, digest)
            if existing:
                return SavedReplay(existing, False)

            stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            path = self.directory / f"{stamp}_{digest[:12]}.replay"
            suffix = 2
            while path.exists():
                path = self.directory / f"{stamp}_{suffix}_{digest[:12]}.replay"
                suffix += 1
            temporary = path.with_suffix(".tmp")
            try:
                temporary.write_text(replay_hex, encoding="ascii")
                temporary.replace(path)
            finally:
                temporary.unlink(missing_ok=True)
            self._remember(path, self._signature(path.stat()), digest)
            return SavedReplay(path, True)

