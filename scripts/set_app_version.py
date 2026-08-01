from __future__ import annotations

import argparse
import re
from pathlib import Path


VERSION_PATTERN = re.compile(r"^v\d+\.\d+\.\d+_R\d+$")
VERSION_FILES = (
    (Path("main.py"), re.compile(r'^(APP_VERSION\s*=\s*)"[^"]+"', re.MULTILINE)),
    (Path("agent/index.ts"), re.compile(r'^(const AGENT_VERSION\s*=\s*)"[^"]+"', re.MULTILINE)),
)


def replace_version(source: str, pattern: re.Pattern[str], version: str) -> str:
    updated, count = pattern.subn(lambda match: f'{match.group(1)}"{version}"', source, count=1)
    if count != 1:
        raise ValueError("expected exactly one version declaration")
    return updated


def main() -> None:
    parser = argparse.ArgumentParser(description="Set the application version before packaging")
    parser.add_argument("version", help="release tag, for example v2.8.0_R1")
    args = parser.parse_args()

    if not VERSION_PATTERN.fullmatch(args.version):
        parser.error("version must match v<major>.<minor>.<patch>_R<revision>")

    repository_root = Path(__file__).resolve().parent.parent
    updates = []
    for relative_path, pattern in VERSION_FILES:
        path = repository_root / relative_path
        source = path.read_text(encoding="utf-8")
        updates.append((relative_path, path, replace_version(source, pattern, args.version)))

    for relative_path, path, updated in updates:
        path.write_text(updated, encoding="utf-8")
        print(f"Set {relative_path.as_posix()} version to {args.version}")


if __name__ == "__main__":
    main()
