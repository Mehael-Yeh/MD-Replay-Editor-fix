"""Validation and persistence for saved Master Duel replay packets."""

from __future__ import annotations

import hashlib
import re
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
        self.directory.mkdir(parents=True, exist_ok=True)

    def list(self) -> list[Path]:
        return sorted(self.directory.glob("*.replay"), key=lambda p: p.stat().st_mtime, reverse=True)

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

    def save(self, replay_hex: str) -> SavedReplay:
        replay_hex = validate_replay_hex(replay_hex, self.tr)
        digest = hashlib.sha256(bytes.fromhex(replay_hex)).hexdigest()[:12]
        existing = next(self.directory.glob(f"*_{digest}.replay"), None)
        if existing is None:
            for candidate in self.directory.glob("*.replay"):
                try:
                    candidate_hex = self.read(candidate)
                    candidate_digest = hashlib.sha256(bytes.fromhex(candidate_hex)).hexdigest()[:12]
                    if candidate_digest == digest:
                        existing = candidate
                        break
                except (OSError, ValueError):
                    continue
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
