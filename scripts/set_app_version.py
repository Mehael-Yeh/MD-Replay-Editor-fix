from __future__ import annotations

import argparse
import re
from pathlib import Path


VERSION_PATTERN = re.compile(r"^v(\d+)\.(\d+)\.(\d+)_R\d+$")
VERSION_DECLARATIONS = (
    (Path("main.py"), re.compile(r'^(APP_VERSION\s*=\s*)"[^"]+"', re.MULTILINE), "release"),
    (
        Path("main.py"),
        re.compile(r'^(SUPPORTED_GAME_VERSION\s*=\s*)"[^"]+"', re.MULTILINE),
        "game",
    ),
    (
        Path("agent/index.ts"),
        re.compile(r'^(const AGENT_VERSION\s*=\s*)"[^"]+"', re.MULTILINE),
        "release",
    ),
)


def replace_version(source: str, pattern: re.Pattern[str], version: str) -> str:
    updated, count = pattern.subn(lambda match: f'{match.group(1)}"{version}"', source, count=1)
    if count != 1:
        raise ValueError("expected exactly one version declaration")
    return updated


def game_version_from_release(version: str) -> str:
    match = VERSION_PATTERN.fullmatch(version)
    if match is None:
        raise ValueError("invalid release version")
    return ".".join(match.groups())


def main() -> None:
    parser = argparse.ArgumentParser(description="Set the application version before packaging")
    parser.add_argument("version", help="release tag, for example v2.8.0_R1")
    args = parser.parse_args()

    if not VERSION_PATTERN.fullmatch(args.version):
        parser.error("version must match v<major>.<minor>.<patch>_R<revision>")

    repository_root = Path(__file__).resolve().parent.parent
    versions = {
        "release": args.version,
        "game": game_version_from_release(args.version),
    }
    updates = {}
    for relative_path, pattern, version_kind in VERSION_DECLARATIONS:
        path = repository_root / relative_path
        source = updates[path] if path in updates else path.read_text(encoding="utf-8")
        updates[path] = replace_version(source, pattern, versions[version_kind])

    for path, updated in updates.items():
        path.write_text(updated, encoding="utf-8")
        print(f"Updated versions in {path.relative_to(repository_root).as_posix()}")


if __name__ == "__main__":
    main()
