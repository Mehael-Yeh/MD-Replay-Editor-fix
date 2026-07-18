#!/usr/bin/env python3
"""Track YgoMaster files that signal Master Duel compatibility changes."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional


UPSTREAM_REPOSITORY = "pixeltris/YgoMaster"
UPSTREAM_REF = "master"
TRACKED_FILES = {
    "YgoMaster/Data/ClientData/ClientSettings.json": (
        '"SupportedGameVersion"',
        '"UnityPlayerVersion"',
    ),
    "Docs/updatediff.cs": ("// Client version ",),
    "YgoMasterClient/Program.cs": ("AppCommonVersion",),
    "YgoMasterClient/ConsoleHelper.cs": ("AppVersion",),
    "YgoMasterClient/DuelReplayUtils.cs": ("replaym",),
    "YgoMasterServer/GameServer.cs": ("YgomSystem.Network.FormatYgom",),
    "YgoMasterServer/Acts/Act_Duel.cs": ("replaym",),
}


def parse_client_settings(text: str) -> tuple[str, str]:
    supported = re.search(r'"SupportedGameVersion"\s*:\s*"([^"]+)"', text)
    unity = re.search(r'"UnityPlayerVersion"\s*:\s*"([^"]+)"', text)
    if not supported or not unity:
        raise ValueError("YgoMaster ClientSettings.json is missing version fields")
    return supported.group(1), unity.group(1)


def parse_updatediff_version(text: str) -> str:
    match = re.search(r"^// Client version\s+([^\s]+)", text, re.MULTILINE)
    if not match:
        raise ValueError("YgoMaster Docs/updatediff.cs is missing its client version header")
    return match.group(1)


def replace_supported_game_version(text: str, version: str) -> tuple[str, bool]:
    pattern = r'^(SUPPORTED_GAME_VERSION\s*=\s*)"[^"]+"'
    updated, count = re.subn(pattern, rf'\1"{version}"', text, count=1, flags=re.MULTILINE)
    if count != 1:
        raise ValueError("main.py does not contain one SUPPORTED_GAME_VERSION assignment")
    return updated, updated != text


def fetch_github_file(
    path: str,
    *,
    repository: str = UPSTREAM_REPOSITORY,
    ref: str = UPSTREAM_REF,
    token: Optional[str] = None,
) -> tuple[str, str]:
    encoded_path = urllib.parse.quote(path, safe="/")
    encoded_ref = urllib.parse.quote(ref, safe="")
    url = f"https://api.github.com/repos/{repository}/contents/{encoded_path}?ref={encoded_ref}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "MD-Replay-Editor-fix-upstream-sync",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)
    if payload.get("encoding") != "base64" or not payload.get("content") or not payload.get("sha"):
        raise RuntimeError(f"Unexpected GitHub response for {path}")
    content = base64.b64decode(payload["content"]).decode("utf-8-sig")
    return content, str(payload["sha"])


def make_snapshot(contents: dict[str, tuple[str, str]]) -> dict[str, object]:
    for path, required_patterns in TRACKED_FILES.items():
        text, _blob_sha = contents[path]
        missing = [pattern for pattern in required_patterns if pattern not in text]
        if missing:
            raise ValueError(f"{path} is missing expected compatibility markers: {missing}")

    settings = contents["YgoMaster/Data/ClientData/ClientSettings.json"][0]
    supported_version, unity_version = parse_client_settings(settings)
    updatediff_version = parse_updatediff_version(contents["Docs/updatediff.cs"][0])
    if updatediff_version != supported_version:
        raise ValueError(
            "YgoMaster version sources disagree: "
            f"ClientSettings={supported_version}, updatediff={updatediff_version}"
        )

    files: dict[str, dict[str, str]] = {}
    for path in sorted(contents):
        text, blob_sha = contents[path]
        files[path] = {
            "git_blob_sha": blob_sha,
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        }
    return {
        "schema": 1,
        "repository": UPSTREAM_REPOSITORY,
        "ref": UPSTREAM_REF,
        "supported_game_version": supported_version,
        "unity_player_version": unity_version,
        "updatediff_client_version": updatediff_version,
        "files": files,
    }


def write_github_output(name: str, value: str) -> None:
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with Path(output).open("a", encoding="utf-8") as stream:
            stream.write(f"{name}={value}\n")


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("upstream/ygomaster.json"))
    parser.add_argument("--main-file", type=Path, default=Path("main.py"))
    parser.add_argument("--update-supported-version", action="store_true")
    parser.add_argument("--repository", default=UPSTREAM_REPOSITORY)
    parser.add_argument("--ref", default=UPSTREAM_REF)
    args = parser.parse_args(argv)

    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    contents = {
        path: fetch_github_file(path, repository=args.repository, ref=args.ref, token=token)
        for path in TRACKED_FILES
    }
    snapshot = make_snapshot(contents)
    rendered = json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=False) + "\n"
    previous = args.output.read_text(encoding="utf-8") if args.output.exists() else ""
    snapshot_changed = rendered != previous
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8", newline="\n")

    version_changed = False
    if args.update_supported_version:
        source = args.main_file.read_text(encoding="utf-8")
        updated, version_changed = replace_supported_game_version(
            source, str(snapshot["supported_game_version"])
        )
        if version_changed:
            args.main_file.write_text(updated, encoding="utf-8", newline="\n")

    write_github_output("changed", str(snapshot_changed or version_changed).lower())
    write_github_output("snapshot_changed", str(snapshot_changed).lower())
    write_github_output("version_changed", str(version_changed).lower())
    write_github_output("supported_version", str(snapshot["supported_game_version"]))
    write_github_output("unity_version", str(snapshot["unity_player_version"]))
    print(
        "YgoMaster compatibility snapshot: "
        f"game={snapshot['supported_game_version']}, "
        f"unity={snapshot['unity_player_version']}, "
        f"changed={snapshot_changed or version_changed}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
