"""Shared, atomic persistence for independent application preferences."""
import json
import os
import tempfile
from pathlib import Path


def settings_path(data_dir: Path) -> Path:
    return data_dir.parent / "settings.json"


def load_settings(data_dir: Path) -> dict:
    try:
        value = json.loads(settings_path(data_dir).read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def save_setting(data_dir: Path, key: str, value: str) -> None:
    path = settings_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    settings = load_settings(data_dir)
    settings[key] = value
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".settings-", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(settings, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
