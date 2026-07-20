#!/usr/bin/env python3
"""Portable GUI for capturing and replaying Master Duel replay packets."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import queue
import re
import subprocess
import sys
import threading
import time
import webbrowser
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional


APP_NAME = "MD-Replay-Editor-fix"
APP_VERSION = "v2.7.0_R4"
SUPPORTED_GAME_VERSION = "2.7.0"
GITHUB_URL = "https://github.com/Mehael-Yeh/MD-Replay-Editor-fix"
GITHUB_ISSUES_URL = f"{GITHUB_URL}/issues/new"
REPLAY_MARKER = b"replaym"
HEX_RE = re.compile(r"^[0-9a-fA-F]+$")
READY_TIMEOUT_SECONDS = 20
DEFAULT_LANGUAGE = "zh-CN"
LANGUAGE_NAMES = {"zh-CN": "中文", "en": "English"}
AGENT_MESSAGE_TEMPLATES = {
    "agent.game_version_read_failed": "无法读取游戏版本：{error}",
    "agent.replay_processing_failed": "回放数据处理失败，使用游戏原响应：{error}",
    "agent.il2cpp_initialization_failed": "IL2CPP 初始化失败：{error}",
}

ENGLISH_TRANSLATIONS = {
    "文件不是有效的十六进制回放数据": "The file does not contain valid hexadecimal replay data.",
    "文件中未找到 Master Duel 回放标记": "The Master Duel replay marker was not found in the file.",
    "只能管理回放保存目录中的 .replay 文件": "Only .replay files in the replay folder can be managed.",
    "请输入新的回放名称": "Enter a new replay name.",
    '名称不能包含以下字符：< > : " / \\ | ? *': 'The name cannot contain these characters: < > : " / \\ | ? *',
    "名称不能以句点或空格结尾": "The name cannot end with a period or space.",
    "这个名称由 Windows 系统保留，请换一个名称": "This name is reserved by Windows. Choose a different name.",
    "已经存在名为“{name}”的回放": 'A replay named "{name}" already exists.',
    "代理发生未知错误": "An unknown agent error occurred.",
    "代理初始化失败": "Agent initialization failed.",
    "无法读取游戏版本：{error}": "Failed to read the game version: {error}",
    "回放数据处理失败，使用游戏原响应：{error}": "Replay processing failed; using the original game response: {error}",
    "IL2CPP 初始化失败：{error}": "IL2CPP initialization failed: {error}",
    "处理回放失败：{error}": "Failed to process replay: {error}",
    "代理启动期间连接断开：{reason}": "The connection was lost while the agent was starting: {reason}",
    "缺少 Frida 运行库，请使用 Release 中的完整 EXE": "The Frida runtime is missing. Use the complete EXE from Releases.",
    "未找到已编译代理 agent/_.js": "The compiled agent agent/_.js was not found.",
    "未检测到 Master Duel，请先启动游戏": "Master Duel was not detected. Start the game first.",
    "代理在 {seconds} 秒内没有就绪": "The agent was not ready within {seconds} seconds.",
    "连接游戏失败：{error}": "Failed to connect to the game: {error}",
    "请先点击“连接游戏并开始自动保存”": 'Click "Connect to game and start auto-save" first.',
    "Master Duel 回放助手": "Master Duel Replay Editor",
    "自动保存看过的回放，也能把本地回放重新放进游戏播放": "Automatically save watched replays and play local replays in-game",
    "运行记录": "Activity Log",
    "教程": "Tutorial",
    "语言": "Language",
    "还没有连接游戏": "Not connected to the game",
    "先打开 Master Duel，再点击下面的蓝色按钮。": "Open Master Duel first, then click the blue button below.",
    "1. 连接游戏并开始自动保存": "1. Connect to game and start auto-save",
    "2. 游戏内回放": "2. Play in game",
    "已保存的回放": "Saved Replays",
    "已保存的回放（{count}）": "Saved Replays ({count})",
    "打开保存位置": "Open Folder",
    "刷新列表": "Refresh",
    "文件名": "File Name",
    "保存时间": "Saved At",
    "文件大小": "Size",
    "下一条播放": "Play Next",
    "重命名": "Rename",
    "删除": "Delete",
    "双击可准备播放；右键可选择“下一条播放”或“删除”。准备播放后，回到游戏播放任意一条可用的官方回放即可。": 'Double-click to prepare playback, or right-click and choose "Play Next" or "Delete." Then return to the game and play any available official replay.',
    "{app} {version} 已启动": "{app} {version} started",
    "回放目录：{directory}": "Replay folder: {directory}",
    "使用教程": "Tutorial",
    "三步开始自动保存回放": "Start Auto-Saving Replays in Three Steps",
    "程序只保存你在游戏里实际播放过的回放，不需要修改游戏文件。": "The program only saves replays you actually play in-game and does not modify game files.",
    "打开并连接游戏": "Open and Connect to the Game",
    "先启动 Master Duel，再点击主界面的蓝色连接按钮。": "Start Master Duel, then click the blue connect button on the main screen.",
    "正常播放一条回放": "Play a Replay Normally",
    "回到游戏，打开你想保存的回放并开始播放。": "Return to the game, open the replay you want to save, and start playing it.",
    "等待保存成功": "Wait for It to Save",
    "程序检测到数据后会自动保存，并显示在回放列表中。": "The program saves detected replay data automatically and adds it to the replay list.",
    "怎样播放已保存的回放？": "How Do I Play a Saved Replay?",
    "在主界面选中一条回放，双击它或右键选择“下一条播放”。随后回到游戏，播放任意一条当前可用的官方回放；程序只替换这一次播放。如果临时不想播放，点击主界面的“取消回放”即可。": 'Select a replay on the main screen, then double-click it or right-click and choose "Play Next." Return to the game and play any currently available official replay; only that playback is replaced. Click "Cancel Replay" on the main screen if you change your mind.',
    "知道了": "Got It",
    "正常使用时不需要查看。提交 Issue 时，请先复制下面的内容。": "You normally do not need this. Copy the content below before submitting an issue.",
    "复制全部": "Copy All",
    "打开 GitHub Issues": "Open GitHub Issues",
    "关闭": "Close",
    "程序版本：{version}": "App version: {version}",
    "适配游戏版本：{version}": "Supported game version: {version}",
    "检测到的游戏版本：{version}": "Detected game version: {version}",
    "尚未读取": "Not detected",
    "系统：{system}": "System: {system}",
    "Python：{version}": "Python: {version}",
    "回放目录：{directory}": "Replay folder: {directory}",
    "运行记录：": "Activity log:",
    "已将运行记录复制到剪贴板": "Activity log copied to the clipboard",
    "取消回放": "Cancel Replay",
    "已经连接游戏": "Already Connected",
    "自动保存正在运行，不需要重复点击。": "Auto-save is running; you do not need to connect again.",
    "正在连接游戏…": "Connecting to the Game…",
    "通常只需要几秒，请不要关闭游戏。": "This usually takes only a few seconds. Do not close the game.",
    "正在连接，请稍候…": "Connecting, please wait…",
    "还没有选择文件": "No File Selected",
    "请先在下方列表中点选一条回放。": "Select a replay from the list below first.",
    "请先连接游戏": "Connect to the Game First",
    "点击第 1 个蓝色按钮，连接成功后再播放本地文件。": "Click the first blue button and wait for a successful connection before playing a local file.",
    "准备本地回放失败": "Failed to Prepare Local Replay",
    "请先在列表中选择要重命名的回放。": "Select the replay you want to rename first.",
    "重命名回放": "Rename Replay",
    "起一个容易辨认的名称，回放内容不会改变。": "Choose an easy-to-recognize name. The replay content will not change.",
    "回放名称": "Replay Name",
    "重命名成功": "Replay Renamed",
    "新的名称是 {name}": "The new name is {name}",
    "已将 {old} 重命名为 {new}": "Renamed {old} to {new}",
    "文件已经不存在": "File No Longer Exists",
    "列表已自动刷新。": "The list has been refreshed automatically.",
    "取消": "Cancel",
    "请先在列表中选择要删除的回放。": "Select the replay you want to delete first.",
    "删除回放": "Delete Replay",
    "确定要永久删除这条回放吗？\n\n{name}": "Permanently delete this replay?\n\n{name}",
    "此操作无法撤销。删除后，这条回放将从本地永久移除。": "This action cannot be undone. The replay will be permanently removed from this device.",
    "要删除的文件": "File to delete",
    "回放已删除": "Replay Deleted",
    "{name} 已从本地删除。": "{name} was deleted locally.",
    "已删除 {name}": "Deleted {name}",
    "删除失败": "Delete Failed",
    "删除失败：{error}": "Delete failed: {error}",
    "游戏版本可能不兼容": "Game Version May Be Incompatible",
    "检测到 Master Duel {game}，本程序适配 {supported}。请前往 GitHub 获取新版。": "Master Duel {game} was detected, but this app supports {supported}. Visit GitHub for an update.",
    "版本不匹配：游戏 {game}，程序适配 {supported}": "Version mismatch: game {game}, app supports {supported}",
    "已确认游戏版本 {version}。": "Game version {version} confirmed. ",
    "连接成功，自动保存已开启": "Connected; Auto-Save Is On",
    "{version_detail}现在去游戏里播放回放；播放过的内容会自动出现在下方。": "{version_detail}Play replays in-game and they will appear below automatically.",
    "已连接 · 自动保存运行中": "Connected · Auto-Save Running",
    "未读取": "Not detected",
    "已连接 Master Duel（PID {pid}，游戏版本 {version}）": "Connected to Master Duel (PID {pid}, game version {version})",
    "回放组件已就绪（{version}，游戏版本 {game}）": "Replay component ready ({version}, game version {game})",
    "没有找到 Master Duel": "Master Duel Not Found",
    "请先启动游戏并进入主界面，然后重新点击连接。": "Start the game and reach the main screen, then click connect again.",
    "1. 重新连接游戏": "1. Reconnect to Game",
    "保存成功": "Replay Saved",
    "{name} 已加入下方列表。": "{name} was added to the list below.",
    "已保存 {name}": "Saved {name}",
    "这条回放已经保存过": "Replay Already Saved",
    "程序不会重复保存，因此不会浪费磁盘空间。": "Duplicate replays are skipped to avoid wasting disk space.",
    "跳过重复文件 {name}": "Skipped duplicate file {name}",
    "本地回放已经准备好": "Local Replay Ready",
    "现在回到游戏，播放任意一条可用回放。": "Return to the game and play any available replay.",
    "下一次播放将使用 {name}": "The next playback will use {name}",
    "已取消回放": "Replay Cancelled",
    "不会再替换下一条游戏回放，自动保存仍在运行。": "The next replay will not be replaced; auto-save is still running.",
    "已取消准备好的本地回放": "Cancelled the prepared local replay",
    "本地回放已送入游戏": "Local Replay Sent to Game",
    "本次播放已替换；程序现在自动恢复保存模式。": "This playback was replaced; the program has returned to save mode.",
    "已加载 {name}": "Loaded {name}",
    "游戏连接已断开": "Game Disconnected",
    "如果游戏仍在运行，请点击按钮重新连接。": "If the game is still running, click the button to reconnect.",
    "连接断开：{detail}": "Disconnected: {detail}",
    "连接或运行失败": "Connection or Runtime Failure",
    "1. 重试连接": "1. Retry Connection",
    "错误：{error}": "Error: {error}",
}


def translate(language: str, text: str, **values: object) -> str:
    template = ENGLISH_TRANSLATIONS.get(text, text) if language == "en" else text
    return template.format(**values)


def settings_path(data_dir: Path) -> Path:
    return data_dir.parent / "settings.json"


def load_language(data_dir: Path) -> str:
    try:
        value = json.loads(settings_path(data_dir).read_text(encoding="utf-8")).get("language")
        return value if value in LANGUAGE_NAMES else DEFAULT_LANGUAGE
    except (OSError, ValueError, TypeError, AttributeError):
        return DEFAULT_LANGUAGE


def save_language(data_dir: Path, language: str) -> None:
    path = settings_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"language": language}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def resource_path(*parts: str) -> Path:
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return root.joinpath(*parts)


def default_data_dir() -> Path:
    """Prefer a portable folder beside the executable, then LocalAppData."""
    root = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
    portable = root / "replays"
    try:
        portable.mkdir(parents=True, exist_ok=True)
        probe = portable / ".write-test"
        probe.write_bytes(b"ok")
        probe.unlink()
        return portable
    except OSError:
        local = Path(os.environ.get("LOCALAPPDATA", Path.home())) / APP_NAME / "replays"
        local.mkdir(parents=True, exist_ok=True)
        return local


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


class ReplayManager:
    def __init__(
        self,
        store: ReplayStore,
        event_sink: Optional[Callable[[str, object], None]] = None,
        translator: Optional[Callable[..., str]] = None,
    ):
        self.store = store
        self.tr = translator or (lambda text, **values: text.format(**values))
        self.event_sink = event_sink or (lambda _kind, _data: None)
        self.session = None
        self.script = None
        self.attached = False
        self.selected: Optional[Path] = None
        self.override_armed = False
        self.saved = 0
        self.game_version: Optional[str] = None
        self._lock = threading.RLock()
        self._ready_event = threading.Event()
        self._startup_error: Optional[str] = None

    def emit(self, kind: str, data: object = None) -> None:
        self.event_sink(kind, data)

    def localize_agent_message(self, data: object, fallback: str) -> str:
        if isinstance(data, dict):
            template = AGENT_MESSAGE_TEMPLATES.get(str(data.get("message")))
            if template:
                return self.tr(template, error=data.get("error", ""))
        return str(data or self.tr(fallback))

    def _reply(self, replay_hex: str) -> None:
        script = self.script
        if script is not None:
            script.post({"type": "replay_reply", "replay": replay_hex})

    def _on_message(self, message, _binary_data) -> None:
        if message.get("type") == "error":
            detail = message.get("stack") or message.get("description") or self.tr("代理发生未知错误")
            with self._lock:
                starting = not self.attached
                if starting:
                    self._startup_error = detail
                    self._ready_event.set()
            if not starting:
                self.emit("error", detail)
            return
        if message.get("type") != "send":
            return

        payload = message.get("payload")
        if not isinstance(payload, dict):
            return
        event_type = payload.get("type")
        data = payload.get("data")

        if event_type == "ready":
            if isinstance(data, dict):
                game_version = data.get("gameVersion")
                self.game_version = str(game_version) if game_version else None
            self._ready_event.set()
            self.emit("ready", data)
            return
        if event_type == "fatal":
            detail = self.localize_agent_message(data, "代理初始化失败")
            with self._lock:
                starting = not self.attached
                if starting:
                    self._startup_error = detail
                    self._ready_event.set()
            if not starting:
                self.emit("error", detail)
            return
        if event_type == "log":
            self.emit("log", self.localize_agent_message(data, "代理发生未知错误"))
            return
        if event_type != "replay_packet" or not isinstance(data, dict):
            return

        original = data.get("hex", "")
        reply = original
        try:
            validate_replay_hex(original, self.tr)
            with self._lock:
                selected = self.selected
                armed = self.override_armed
                if armed:
                    self.override_armed = False

            if armed and selected:
                reply = self.store.read(selected)
                self.emit("loaded", selected)
            else:
                saved = self.store.save(original)
                if saved.created:
                    self.saved += 1
                    self.emit("saved", saved.path)
                else:
                    self.emit("duplicate", saved.path)
        except Exception as exc:
            self.emit("error", self.tr("处理回放失败：{error}", error=exc))
            reply = original
        finally:
            # DeserializeAsync is waiting synchronously; always release it.
            self._reply(reply)

    def _on_detached(self, reason, crash=None) -> None:
        with self._lock:
            if not self.attached and self._startup_error is None:
                self._startup_error = self.tr("代理启动期间连接断开：{reason}", reason=reason)
                self._ready_event.set()
            self.attached = False
            self.session = None
            self.script = None
            self.override_armed = False
        detail = f"{reason}"
        if crash:
            detail += f" ({crash})"
        self.emit("detached", detail)

    def attach(self) -> bool:
        with self._lock:
            if self.attached:
                return True
            self._startup_error = None
            self._ready_event.clear()
        try:
            import frida
        except ImportError:
            self.emit("error", self.tr("缺少 Frida 运行库，请使用 Release 中的完整 EXE"))
            return False

        agent = resource_path("agent", "_.js")
        if not agent.exists():
            self.emit("error", self.tr("未找到已编译代理 agent/_.js"))
            return False

        try:
            device = frida.get_local_device()
            process = next(
                (p for p in device.enumerate_processes() if p.name.lower() in {"masterduel.exe", "masterduel"}),
                None,
            )
            if process is None:
                self.emit("waiting", self.tr("未检测到 Master Duel，请先启动游戏"))
                return False

            session = device.attach(process.pid)
            script = session.create_script(agent.read_text(encoding="utf-8"))
            script.on("message", self._on_message)
            session.on("detached", self._on_detached)
            with self._lock:
                self.session = session
                self.script = script
            script.load()
            if not self._ready_event.wait(READY_TIMEOUT_SECONDS):
                raise RuntimeError(self.tr("代理在 {seconds} 秒内没有就绪", seconds=READY_TIMEOUT_SECONDS))
            with self._lock:
                if self._startup_error:
                    raise RuntimeError(self._startup_error)
                self.attached = True
            self.emit("attached", {"pid": process.pid, "game_version": self.game_version})
            return True
        except Exception as exc:
            self.emit("error", self.tr("连接游戏失败：{error}", error=exc))
            self.detach()
            return False

    def arm_override(self, path: Path) -> None:
        self.store.read(path)
        with self._lock:
            if not self.attached:
                raise RuntimeError(self.tr("请先点击“连接游戏并开始自动保存”"))
            self.selected = path
            self.override_armed = True
        self.emit("armed", path)

    def cancel_override(self, notify: bool = True) -> None:
        with self._lock:
            self.override_armed = False
        if notify:
            self.emit("cancelled")

    def replace_selected_path(self, old_path: Path, new_path: Path) -> None:
        with self._lock:
            if self.selected == old_path:
                self.selected = new_path

    def detach(self) -> None:
        with self._lock:
            script, session = self.script, self.session
            self.script = self.session = None
            self.attached = False
            self.override_armed = False
        try:
            if script:
                script.unload()
        except Exception:
            pass
        try:
            if session:
                session.detach()
        except Exception:
            pass


class ReplayApp:
    BG = "#F6F8FC"
    CARD = "#FFFFFF"
    TEXT = "#202124"
    MUTED = "#5F6368"
    BORDER = "#E1E5EE"
    BLUE = "#1A73E8"
    BLUE_HOVER = "#1765CC"
    GREEN = "#188038"
    RED = "#D93025"
    DANGER_BG = "#FCE8E6"
    DANGER_HOVER = "#F9DEDC"
    DANGER_TEXT = "#B3261E"
    AMBER = "#F9AB00"

    def __init__(self, data_dir: Path):
        import tkinter as tk
        from tkinter import font as tkfont
        from tkinter import ttk

        self.tk = tk
        self.tkfont = tkfont
        self.ttk = ttk
        self.language = load_language(data_dir)
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.store = ReplayStore(data_dir, self.tr)
        self.manager = ReplayManager(
            self.store,
            lambda kind, data=None: self.events.put((kind, data)),
            self.tr,
        )
        self.log_lines: list[str] = []
        self.log_window = None
        self.log_text = None
        self.tutorial_window = None
        self.rename_window = None
        self.delete_window = None

        root = tk.Tk()
        self.root = root
        root.title(f"{APP_NAME} {APP_VERSION}")
        self.app_icon = None
        try:
            self.app_icon = tk.PhotoImage(file=resource_path("assets", "app-icon.png"))
            root.iconphoto(True, self.app_icon)
        except Exception:
            pass
        self.empty_replay_marker = tk.PhotoImage(width=14, height=14)
        self.armed_replay_marker = tk.PhotoImage(width=14, height=14)
        for x in range(3, 11):
            inset = (x - 3) // 2
            for y in range(2 + inset, 12 - inset):
                self.armed_replay_marker.put(self.BLUE, (x, y))
        root.geometry("1000x680")
        root.minsize(880, 600)
        root.configure(bg=self.BG)

        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure(
            "Replay.Treeview",
            background=self.CARD,
            fieldbackground=self.CARD,
            foreground=self.TEXT,
            rowheight=38,
            borderwidth=1,
            bordercolor=self.BORDER,
            lightcolor=self.BORDER,
            darkcolor=self.BORDER,
            focuscolor=self.BORDER,
            relief="flat",
            font=("Microsoft YaHei UI", 9),
        )
        style.map(
            "Replay.Treeview",
            background=[("selected", "#D2E3FC")],
            foreground=[("selected", self.TEXT)],
            bordercolor=[("focus", self.BORDER), ("!focus", self.BORDER)],
            lightcolor=[("focus", self.BORDER), ("!focus", self.BORDER)],
            darkcolor=[("focus", self.BORDER), ("!focus", self.BORDER)],
        )
        style.configure(
            "Replay.Treeview.Heading",
            background="#F8FAFD",
            foreground=self.MUTED,
            relief="flat",
            font=("Microsoft YaHei UI", 9, "bold"),
            padding=(10, 10),
        )
        style.layout(
            "Replay.Vertical.TScrollbar",
            [
                (
                    "Vertical.Scrollbar.trough",
                    {
                        "sticky": "ns",
                        "children": [
                            ("Vertical.Scrollbar.thumb", {"expand": "1", "sticky": "nswe"}),
                        ],
                    },
                )
            ],
        )
        style.configure(
            "Replay.Vertical.TScrollbar",
            background="#C7CDD8",
            troughcolor="#F1F3F4",
            bordercolor="#F1F3F4",
            lightcolor="#C7CDD8",
            darkcolor="#C7CDD8",
            gripcount=0,
            width=10,
        )
        style.map(
            "Replay.Vertical.TScrollbar",
            background=[("active", "#9AA4B2"), ("pressed", "#7B8794")],
        )

        header = tk.Frame(
            root,
            bg=self.CARD,
            highlightbackground=self.BORDER,
            highlightcolor=self.BORDER,
            highlightthickness=1,
        )
        header.pack(fill=tk.X)
        title_area = tk.Frame(header, bg=self.CARD)
        title_area.pack(side=tk.LEFT, padx=26, pady=(13, 15))
        title_line = tk.Frame(title_area, bg=self.CARD)
        title_line.pack(anchor=tk.W)
        self.main_title_label = tk.Label(
            title_line,
            text=self.tr("Master Duel 回放助手"),
            bg=self.CARD,
            fg=self.TEXT,
            font=("Microsoft YaHei UI", 16, "bold"),
        )
        self.main_title_label.pack(side=tk.LEFT)
        tk.Label(
            title_line,
            text=APP_VERSION,
            bg="#E8F0FE",
            fg=self.BLUE,
            padx=9,
            pady=3,
            font=("Segoe UI", 9, "bold"),
        ).pack(side=tk.LEFT, padx=(12, 0))
        self.subtitle_label = tk.Label(
            title_area,
            text=self.tr("自动保存看过的回放，也能把本地回放重新放进游戏播放"),
            bg=self.CARD,
            fg=self.MUTED,
            font=("Microsoft YaHei UI", 9),
        )
        self.subtitle_label.pack(anchor=tk.W, pady=(5, 0))
        header_actions = tk.Frame(header, bg=self.CARD)
        header_actions.pack(side=tk.RIGHT, padx=20, pady=16)
        self.language_button = self._header_button(header_actions, self.language_button_text(), self.change_language)
        self.language_button.configure(width=5)
        self.language_button.pack(side=tk.RIGHT)
        self._header_button(header_actions, "GitHub", self.open_github).pack(side=tk.RIGHT, padx=(0, 8))
        self.log_button = self._header_button(header_actions, self.tr("运行记录"), self.show_log_window)
        self.log_button.pack(side=tk.RIGHT, padx=(0, 8))
        self.tutorial_button = self._header_button(header_actions, self.tr("教程"), self.show_tutorial)
        self.tutorial_button.pack(side=tk.RIGHT, padx=(0, 8))

        content = tk.Frame(root, bg=self.BG, padx=24, pady=18)
        content.pack(fill=tk.BOTH, expand=True)

        status_card = self._card(content)
        status_card.pack(fill=tk.X)
        status_body = tk.Frame(status_card, bg=self.CARD)
        status_body.pack(fill=tk.X, padx=20, pady=(17, 12))
        self.status_dot = tk.Label(status_body, text="●", bg=self.CARD, fg=self.MUTED, font=("Segoe UI", 18))
        self.status_dot.pack(side=tk.LEFT, padx=(0, 12))
        status_text = tk.Frame(status_body, bg=self.CARD)
        status_text.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.status_title = tk.StringVar(value=self.tr("还没有连接游戏"))
        self.status_detail = tk.StringVar(value=self.tr("先打开 Master Duel，再点击下面的蓝色按钮。"))
        self._status_spec = (
            "还没有连接游戏",
            "先打开 Master Duel，再点击下面的蓝色按钮。",
            self.MUTED,
            {},
            {},
        )
        tk.Label(
            status_text,
            textvariable=self.status_title,
            bg=self.CARD,
            fg=self.TEXT,
            anchor=tk.W,
            font=("Microsoft YaHei UI", 12, "bold"),
        ).pack(fill=tk.X)
        self.status_detail_label = tk.Label(
            status_text,
            textvariable=self.status_detail,
            bg=self.CARD,
            fg=self.MUTED,
            anchor=tk.W,
            justify=tk.LEFT,
            font=("Microsoft YaHei UI", 9),
        )
        self.status_detail_label.pack(fill=tk.X, pady=(3, 0))

        action_bar = tk.Frame(status_card, bg=self.CARD)
        action_bar.pack(fill=tk.X, padx=20, pady=(0, 18))
        action_bar.columnconfigure(0, weight=1, uniform="main_actions")
        action_bar.columnconfigure(1, weight=1, uniform="main_actions")
        self.attach_button = self._button(
            action_bar,
            self.tr("1. 连接游戏并开始自动保存"),
            self.start_attach,
            primary=True,
        )
        self.attach_button.grid(row=0, column=0, sticky="ew", padx=(0, 5), ipady=2)
        self.play_button = self._button(
            action_bar,
            self.tr("2. 游戏内回放"),
            self.arm_selected,
            outlined=True,
        )
        self.play_button.grid(row=0, column=1, sticky="ew", padx=(5, 0), ipady=2)
        self.attach_text_key = "1. 连接游戏并开始自动保存"

        library_card = self._card(content)
        library_card.pack(fill=tk.BOTH, expand=True, pady=(14, 0))
        library_card.columnconfigure(0, weight=1)
        library_card.rowconfigure(1, weight=1)
        library_header = tk.Frame(library_card, bg=self.CARD)
        library_header.grid(row=0, column=0, sticky="ew", padx=18, pady=(10, 7))
        self.library_title = tk.StringVar(value=self.tr("已保存的回放"))
        tk.Label(
            library_header,
            textvariable=self.library_title,
            bg=self.CARD,
            fg=self.TEXT,
            font=("Microsoft YaHei UI", 11, "bold"),
        ).pack(side=tk.LEFT)
        self.open_folder_button = self._link_button(library_header, self.tr("打开保存位置"), self.open_folder)
        self.open_folder_button.pack(side=tk.RIGHT)
        self.refresh_button = self._link_button(library_header, self.tr("刷新列表"), self.refresh)
        self.refresh_button.pack(side=tk.RIGHT, padx=(0, 8))

        tree_area = tk.Frame(library_card, bg=self.CARD)
        tree_area.grid(row=1, column=0, sticky="nsew", padx=18)
        columns = ("time", "size")
        self.tree = ttk.Treeview(
            tree_area,
            columns=columns,
            show="tree headings",
            selectmode="browse",
            style="Replay.Treeview",
        )
        scrollbar = ttk.Scrollbar(
            tree_area,
            orient=tk.VERTICAL,
            command=self.tree.yview,
            style="Replay.Vertical.TScrollbar",
        )
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.heading("#0", text=self.tr("文件名"), anchor=tk.CENTER)
        self.tree.heading("time", text=self.tr("保存时间"), anchor=tk.CENTER)
        self.tree.heading("size", text=self.tr("文件大小"), anchor=tk.CENTER)
        self.tree.column("#0", width=500, minwidth=240, anchor=tk.W, stretch=True)
        self.tree.column("time", width=180, minwidth=155, anchor=tk.CENTER, stretch=False)
        self.tree.column("size", width=105, minwidth=90, anchor=tk.CENTER, stretch=False)
        self.replay_list_font = tkfont.Font(root=root, family="Microsoft YaHei UI", size=9)
        self._column_resize_job = None
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.bind("<Configure>", self.schedule_replay_column_resize)
        self.tree.bind("<<TreeviewSelect>>", lambda _event: self.update_action_states())
        self.tree.bind("<Double-1>", lambda _event: self.arm_selected())
        self.tree.bind("<Button-3>", self.show_replay_menu)
        self.tree.bind("<Delete>", lambda _event: self.delete_selected())
        self.tree.bind("<MouseWheel>", self.scroll_replay_list)
        self.replay_menu = tk.Menu(
            root,
            tearoff=False,
            bg=self.CARD,
            fg=self.TEXT,
            activebackground="#E8F0FE",
            activeforeground=self.BLUE,
            relief=tk.FLAT,
            borderwidth=1,
            font=("Microsoft YaHei UI", 9),
        )
        self.replay_menu.add_command(label=self.tr("下一条播放"), command=self.arm_selected)
        self.replay_menu.add_command(label=self.tr("重命名"), command=self.rename_selected)
        self.replay_menu.add_separator()
        self.replay_menu.add_command(label=self.tr("删除"), command=self.delete_selected)
        self.replay_menu.entryconfigure(
            3,
            background=self.DANGER_BG,
            foreground=self.DANGER_TEXT,
            activebackground=self.DANGER_HOVER,
            activeforeground=self.DANGER_TEXT,
        )

        self.tip_label = tk.Label(
            library_card,
            text=self.tr(
                "双击可准备播放；右键可选择“下一条播放”或“删除”。"
                "准备播放后，回到游戏播放任意一条可用的官方回放即可。"
            ),
            bg="#F8FAFD",
            fg=self.MUTED,
            anchor=tk.W,
            justify=tk.LEFT,
            wraplength=850,
            padx=12,
            pady=7,
            font=("Microsoft YaHei UI", 9),
        )
        self.tip_label.grid(row=2, column=0, sticky="ew", padx=18, pady=(6, 10))

        root.protocol("WM_DELETE_WINDOW", self.close)
        root.bind("<Configure>", self.update_responsive_layout, add="+")
        self.refresh()
        self.update_responsive_layout()
        self.update_action_states()
        self.append_log(self.tr("{app} {version} 已启动", app=APP_NAME, version=APP_VERSION))
        self.append_log(self.tr("回放目录：{directory}", directory=self.store.directory))
        root.after(150, self.poll_events)

    def tr(self, text: str, **values: object) -> str:
        return translate(self.language, text, **values)

    def language_button_text(self) -> str:
        return "EN" if self.language == "zh-CN" else "中文"

    def change_language(self) -> None:
        self.language = "en" if self.language == "zh-CN" else "zh-CN"
        try:
            save_language(self.store.directory, self.language)
        except OSError:
            pass
        self.apply_language()

    def apply_language(self) -> None:
        self.main_title_label.configure(text=self.tr("Master Duel 回放助手"))
        self.subtitle_label.configure(text=self.tr("自动保存看过的回放，也能把本地回放重新放进游戏播放"))
        self.log_button.configure(text=self.tr("运行记录"))
        self.tutorial_button.configure(text=self.tr("教程"))
        self.language_button.configure(text=self.language_button_text())
        self.open_folder_button.configure(text=self.tr("打开保存位置"))
        self.refresh_button.configure(text=self.tr("刷新列表"))
        self.tree.heading("#0", text=self.tr("文件名"), anchor=self.tk.CENTER)
        self.tree.heading("time", text=self.tr("保存时间"), anchor=self.tk.CENTER)
        self.tree.heading("size", text=self.tr("文件大小"), anchor=self.tk.CENTER)
        self.replay_menu.entryconfigure(0, label=self.tr("下一条播放"))
        self.replay_menu.entryconfigure(1, label=self.tr("重命名"))
        self.replay_menu.entryconfigure(3, label=self.tr("删除"))
        self.tip_label.configure(
            text=self.tr(
                "双击可准备播放；右键可选择“下一条播放”或“删除”。"
                "准备播放后，回到游戏播放任意一条可用的官方回放即可。"
            )
        )
        self.attach_button.configure(text=self.tr(self.attach_text_key))
        title, detail, color, title_values, detail_values = self._status_spec
        if detail == "{version_detail}现在去游戏里播放回放；播放过的内容会自动出现在下方。":
            detail_values = {
                "version_detail": (
                    self.tr("已确认游戏版本 {version}。", version=self.manager.game_version)
                    if self.manager.game_version
                    else ""
                )
            }
            self._status_spec = (title, detail, color, title_values, detail_values)
        self.status_title.set(self.tr(title, **title_values))
        self.status_detail.set(self.tr(detail, **detail_values))
        self.status_dot.configure(fg=color)
        self.close_tutorial()
        self.close_log_window()
        self.close_delete_dialog()
        self.refresh()
        self.update_action_states()

    def update_responsive_layout(self, event=None) -> None:
        if event is not None and event.widget is not self.root:
            return
        width = self.root.winfo_width()
        self.subtitle_label.configure(wraplength=max(300, min(560, width - 430)), justify=self.tk.LEFT)
        self.status_detail_label.configure(wraplength=max(420, width - 150))
        self.tip_label.configure(wraplength=max(420, width - 100))

    def schedule_replay_column_resize(self, _event=None) -> None:
        if self._column_resize_job is not None:
            self.root.after_cancel(self._column_resize_job)
        self._column_resize_job = self.root.after_idle(self.adjust_replay_columns)

    def adjust_replay_columns(self) -> None:
        self._column_resize_job = None
        available = max(520, self.tree.winfo_width() - 4)
        time_samples = [self.tr("保存时间"), "2000-00-00 00:00:00"]
        size_samples = [self.tr("文件大小"), "0000.0 KB"]
        size_samples.extend(self.tree.set(item, "size") for item in self.tree.get_children())
        time_width = max(155, max(self.replay_list_font.measure(value) for value in time_samples) + 30)
        size_width = max(90, max(self.replay_list_font.measure(value) for value in size_samples) + 30)
        file_width = max(240, available - time_width - size_width)
        self.tree.column("#0", width=file_width, minwidth=240, anchor=self.tk.W, stretch=True)
        self.tree.column("time", width=time_width, minwidth=155, anchor=self.tk.CENTER, stretch=False)
        self.tree.column("size", width=size_width, minwidth=90, anchor=self.tk.CENTER, stretch=False)

    def set_attach_button(self, text: str, state: str) -> None:
        self.attach_text_key = text
        self.attach_button.configure(state=state, text=self.tr(text))

    def _card(self, parent):
        return self.tk.Frame(
            parent,
            bg=self.CARD,
            highlightbackground=self.BORDER,
            highlightcolor=self.BORDER,
            highlightthickness=1,
        )

    def _button(
        self,
        parent,
        text: str,
        command,
        primary: bool = False,
        danger: bool = False,
        outlined: bool = False,
    ):
        bg = self.BLUE if primary else self.CARD
        fg = "#FFFFFF" if primary else self.BLUE
        hover = self.BLUE_HOVER if primary else "#E8F0FE"
        if danger:
            bg, fg, hover = self.DANGER_TEXT, "#FFFFFF", "#8C1D18"
        outline = self.DANGER_TEXT if danger else self.BLUE
        button = self.tk.Button(
            parent,
            text=text,
            command=command,
            bg=bg,
            fg=fg,
            activebackground=hover,
            activeforeground=fg,
            disabledforeground="#A9AFB8",
            relief=self.tk.FLAT,
            borderwidth=0,
            highlightthickness=1 if outlined else 0,
            highlightbackground=outline if outlined else bg,
            highlightcolor=outline if outlined else bg,
            padx=18,
            pady=10,
            cursor="hand2",
            font=("Microsoft YaHei UI", 9, "bold"),
        )
        button._normal_bg = bg
        button._hover_bg = hover
        button._normal_fg = fg
        button._outlined = outlined
        button.bind(
            "<Enter>",
            lambda _event: button.configure(bg=button._hover_bg) if button["state"] == self.tk.NORMAL else None,
        )
        button.bind(
            "<Leave>",
            lambda _event: button.configure(bg=button._normal_bg) if button["state"] == self.tk.NORMAL else None,
        )
        return button

    def _set_button_tone(self, button, danger: bool = False) -> None:
        if danger:
            bg, fg, hover, outline = self.DANGER_BG, self.DANGER_TEXT, self.DANGER_HOVER, self.DANGER_TEXT
        else:
            bg, fg, hover, outline = self.CARD, self.BLUE, "#E8F0FE", self.BLUE
        button._normal_bg = bg
        button._hover_bg = hover
        button._normal_fg = fg
        button.configure(
            bg=bg,
            fg=fg,
            activebackground=hover,
            activeforeground=fg,
            highlightbackground=outline if getattr(button, "_outlined", False) else bg,
            highlightcolor=outline if getattr(button, "_outlined", False) else bg,
        )

    def _link_button(self, parent, text: str, command):
        button = self.tk.Button(
            parent,
            text=text,
            command=command,
            bg=self.CARD,
            fg=self.BLUE,
            activebackground="#E8F0FE",
            activeforeground=self.BLUE,
            relief=self.tk.FLAT,
            borderwidth=0,
            padx=9,
            pady=5,
            cursor="hand2",
            font=("Microsoft YaHei UI", 9, "bold"),
        )
        button.bind("<Enter>", lambda _event: button.configure(bg="#E8F0FE"))
        button.bind("<Leave>", lambda _event: button.configure(bg=self.CARD))
        return button

    def _header_button(self, parent, text: str, command):
        button = self.tk.Button(
            parent,
            text=text,
            command=command,
            bg=self.CARD,
            fg=self.MUTED,
            activebackground="#E8F0FE",
            activeforeground=self.BLUE,
            relief=self.tk.FLAT,
            borderwidth=0,
            padx=12,
            pady=7,
            cursor="hand2",
            font=("Microsoft YaHei UI", 9, "bold"),
        )
        button.bind("<Enter>", lambda _event: button.configure(bg="#E8F0FE", fg=self.BLUE))
        button.bind("<Leave>", lambda _event: button.configure(bg=self.CARD, fg=self.MUTED))
        return button

    def _step(self, parent, number: str, title: str, detail: str):
        frame = self.tk.Frame(
            parent,
            bg="#F8FAFD",
            padx=16,
            pady=14,
            highlightbackground=self.BORDER,
            highlightcolor=self.BORDER,
            highlightthickness=1,
        )
        self.tk.Label(
            frame,
            text=number,
            bg=self.BLUE,
            fg="#FFFFFF",
            width=2,
            font=("Segoe UI", 9, "bold"),
        ).pack(side=self.tk.LEFT, anchor=self.tk.N, padx=(0, 10))
        text = self.tk.Frame(frame, bg="#F8FAFD")
        text.pack(side=self.tk.LEFT, fill=self.tk.X, expand=True)
        self.tk.Label(
            text,
            text=title,
            bg="#F8FAFD",
            fg=self.TEXT,
            anchor=self.tk.W,
            font=("Microsoft YaHei UI", 9, "bold"),
        ).pack(fill=self.tk.X)
        self.tk.Label(
            text,
            text=detail,
            bg="#F8FAFD",
            fg=self.MUTED,
            anchor=self.tk.W,
            justify=self.tk.LEFT,
            wraplength=220 if self.language == "en" else 190,
            font=("Microsoft YaHei UI", 9),
        ).pack(fill=self.tk.X, pady=(2, 0))
        return frame

    def show_tutorial(self) -> None:
        if self.tutorial_window is not None and self.tutorial_window.winfo_exists():
            self.tutorial_window.lift()
            self.tutorial_window.focus_force()
            return

        window = self.tk.Toplevel(self.root)
        window.withdraw()
        self.tutorial_window = window
        window.title(self.tr("使用教程"))
        if self.language == "en":
            window.minsize(840, 440)
        else:
            window.minsize(760, 440)
        window.configure(bg=self.BG)
        window.transient(self.root)
        window.protocol("WM_DELETE_WINDOW", self.close_tutorial)

        body = self.tk.Frame(window, bg=self.BG, padx=24, pady=22)
        body.pack(fill=self.tk.BOTH, expand=True)
        self.tk.Label(
            body,
            text=self.tr("三步开始自动保存回放"),
            bg=self.BG,
            fg=self.TEXT,
            font=("Microsoft YaHei UI", 17, "bold"),
        ).pack(anchor=self.tk.W)
        self.tk.Label(
            body,
            text=self.tr("程序只保存你在游戏里实际播放过的回放，不需要修改游戏文件。"),
            bg=self.BG,
            fg=self.MUTED,
            font=("Microsoft YaHei UI", 9),
        ).pack(anchor=self.tk.W, pady=(5, 16))

        steps = self.tk.Frame(body, bg=self.BG)
        steps.pack(fill=self.tk.X)
        for column in range(3):
            steps.columnconfigure(column, weight=1, uniform="tutorial_steps")
        self._step(
            steps,
            "1",
            self.tr("打开并连接游戏"),
            self.tr("先启动 Master Duel，再点击主界面的蓝色连接按钮。"),
        ).grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        self._step(
            steps,
            "2",
            self.tr("正常播放一条回放"),
            self.tr("回到游戏，打开你想保存的回放并开始播放。"),
        ).grid(row=0, column=1, sticky="nsew", padx=6)
        self._step(
            steps,
            "3",
            self.tr("等待保存成功"),
            self.tr("程序检测到数据后会自动保存，并显示在回放列表中。"),
        ).grid(row=0, column=2, sticky="nsew", padx=(6, 0))

        replay_card = self._card(body)
        replay_card.pack(fill=self.tk.X, pady=(18, 0))
        self.tk.Label(
            replay_card,
            text=self.tr("怎样播放已保存的回放？"),
            bg=self.CARD,
            fg=self.TEXT,
            font=("Microsoft YaHei UI", 11, "bold"),
        ).pack(anchor=self.tk.W, padx=18, pady=(15, 5))
        self.tk.Label(
            replay_card,
            text=self.tr(
                "在主界面选中一条回放，双击它或右键选择“下一条播放”。"
                "随后回到游戏，播放任意一条当前可用的官方回放；程序只替换这一次播放。"
                "如果临时不想播放，点击主界面的“取消回放”即可。"
            ),
            bg=self.CARD,
            fg=self.MUTED,
            justify=self.tk.LEFT,
            anchor=self.tk.W,
            wraplength=800 if self.language == "en" else 620,
            font=("Microsoft YaHei UI", 9),
        ).pack(fill=self.tk.X, padx=18, pady=(0, 15))

        self._button(body, self.tr("知道了"), self.close_tutorial, primary=True).pack(
            anchor=self.tk.E, pady=(16, 0)
        )
        if self.language == "en":
            self.show_centered_dialog(window, 900, 460)
        else:
            self.show_centered_dialog(window, 780, 460)

    def close_tutorial(self) -> None:
        if self.tutorial_window is not None:
            self.tutorial_window.destroy()
            self.tutorial_window = None

    def show_log_window(self) -> None:
        if self.log_window is not None and self.log_window.winfo_exists():
            self.log_window.lift()
            self.log_window.focus_force()
            return

        window = self.tk.Toplevel(self.root)
        window.withdraw()
        self.log_window = window
        window.title(self.tr("运行记录"))
        window.minsize(720, 440)
        window.configure(bg=self.BG)
        window.transient(self.root)
        window.protocol("WM_DELETE_WINDOW", self.close_log_window)

        body = self.tk.Frame(window, bg=self.BG, padx=22, pady=20)
        body.pack(fill=self.tk.BOTH, expand=True)
        self.tk.Label(
            body,
            text=self.tr("运行记录"),
            bg=self.BG,
            fg=self.TEXT,
            font=("Microsoft YaHei UI", 16, "bold"),
        ).pack(anchor=self.tk.W)
        self.tk.Label(
            body,
            text=self.tr("正常使用时不需要查看。提交 Issue 时，请先复制下面的内容。"),
            bg=self.BG,
            fg=self.MUTED,
            font=("Microsoft YaHei UI", 9),
        ).pack(anchor=self.tk.W, pady=(4, 12))

        log_area = self.tk.Frame(
            body,
            bg=self.CARD,
            highlightbackground=self.BORDER,
            highlightcolor=self.BORDER,
            highlightthickness=1,
        )
        log_area.pack(fill=self.tk.BOTH, expand=True)
        text = self.tk.Text(
            log_area,
            state=self.tk.NORMAL,
            bg=self.CARD,
            fg="#3C4043",
            insertbackground=self.TEXT,
            relief=self.tk.FLAT,
            borderwidth=0,
            padx=12,
            pady=10,
            wrap=self.tk.WORD,
            font=("Cascadia Mono", 9),
        )
        log_scrollbar = self.ttk.Scrollbar(
            log_area,
            orient=self.tk.VERTICAL,
            command=text.yview,
            style="Replay.Vertical.TScrollbar",
        )
        text.configure(yscrollcommand=log_scrollbar.set)
        text.pack(side=self.tk.LEFT, fill=self.tk.BOTH, expand=True)
        log_scrollbar.pack(side=self.tk.RIGHT, fill=self.tk.Y)
        text.insert(self.tk.END, self.issue_report_text())
        text.see(self.tk.END)
        text.configure(state=self.tk.DISABLED)
        self.log_text = text

        actions = self.tk.Frame(body, bg=self.BG)
        actions.pack(fill=self.tk.X, pady=(14, 0))
        self._button(actions, self.tr("复制全部"), self.copy_logs, primary=True).pack(side=self.tk.LEFT)
        self._button(actions, self.tr("打开 GitHub Issues"), self.open_issues).pack(
            side=self.tk.LEFT, padx=(10, 0)
        )
        self._link_button(actions, self.tr("关闭"), self.close_log_window).pack(side=self.tk.RIGHT)
        self.show_centered_dialog(window, 820, 540)

    def show_centered_dialog(self, window, width: int, height: int) -> None:
        self.root.update_idletasks()
        window.update_idletasks()
        screen_width = window.winfo_screenwidth()
        screen_height = window.winfo_screenheight()
        max_width = max(480, screen_width - 40)
        max_height = max(360, screen_height - 80)
        width = min(max(width, window.winfo_reqwidth()), max_width)
        height = min(max(height, window.winfo_reqheight()), max_height)
        x = self.root.winfo_rootx() + (self.root.winfo_width() - width) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - height) // 2
        x = max(20, min(x, screen_width - width - 20))
        y = max(20, min(y, screen_height - height - 40))
        window.geometry(f"{width}x{height}+{x}+{y}")
        window.deiconify()
        window.lift()
        window.focus_force()

    def close_log_window(self) -> None:
        if self.log_window is not None:
            self.log_window.destroy()
        self.log_window = None
        self.log_text = None

    def issue_report_text(self) -> str:
        header = [
            self.tr("程序版本：{version}", version=APP_VERSION),
            self.tr("适配游戏版本：{version}", version=SUPPORTED_GAME_VERSION),
            self.tr(
                "检测到的游戏版本：{version}",
                version=self.manager.game_version or self.tr("尚未读取"),
            ),
            self.tr("系统：{system}", system=platform.platform()),
            self.tr("Python：{version}", version=platform.python_version()),
            self.tr("回放目录：{directory}", directory=self.store.directory),
            "",
            self.tr("运行记录："),
        ]
        return "\n".join(header + self.log_lines) + "\n"

    def copy_logs(self) -> None:
        self.root.clipboard_clear()
        self.root.clipboard_append(self.issue_report_text())
        self.root.update_idletasks()
        self.append_log(self.tr("已将运行记录复制到剪贴板"))

    def open_github(self) -> None:
        webbrowser.open(GITHUB_URL)

    def open_issues(self) -> None:
        webbrowser.open(GITHUB_ISSUES_URL)

    def set_status(
        self,
        title: str,
        detail: str,
        color: str,
        *,
        title_values: Optional[dict[str, object]] = None,
        detail_values: Optional[dict[str, object]] = None,
    ) -> None:
        title_values = title_values or {}
        detail_values = detail_values or {}
        self._status_spec = (title, detail, color, title_values, detail_values)
        self.status_title.set(self.tr(title, **title_values))
        self.status_detail.set(self.tr(detail, **detail_values))
        self.status_dot.configure(fg=color)

    def append_log(self, text: str) -> None:
        line = f"[{time.strftime('%H:%M:%S')}] {text}"
        self.log_lines.append(line)
        if len(self.log_lines) > 500:
            self.log_lines = self.log_lines[-450:]
        if self.log_text is not None and self.log_text.winfo_exists():
            self.log_text.configure(state=self.tk.NORMAL)
            self.log_text.delete("1.0", self.tk.END)
            self.log_text.insert(self.tk.END, self.issue_report_text())
            self.log_text.see(self.tk.END)
            self.log_text.configure(state=self.tk.DISABLED)

    def update_replay_markers(self) -> None:
        armed_item = str(self.manager.selected) if self.manager.override_armed and self.manager.selected else None
        for item in self.tree.get_children():
            marker = self.armed_replay_marker if item == armed_item else self.empty_replay_marker
            self.tree.item(item, image=marker)

    def update_action_states(self) -> None:
        self.update_replay_markers()
        if self.manager.override_armed:
            self._set_button_tone(self.play_button, danger=True)
            self.play_button.configure(
                state=self.tk.NORMAL,
                text=self.tr("取消回放"),
                command=self.cancel_playback,
            )
            return

        self._set_button_tone(self.play_button)
        has_selection = self.selected_path() is not None
        self.play_button.configure(
            state=self.tk.NORMAL if has_selection else self.tk.DISABLED,
            text=self.tr("2. 游戏内回放"),
            command=self.arm_selected,
            highlightbackground=self.BLUE if has_selection else self.BORDER,
            highlightcolor=self.BLUE if has_selection else self.BORDER,
        )

    def start_attach(self) -> None:
        if self.manager.attached:
            self.set_status("已经连接游戏", "自动保存正在运行，不需要重复点击。", self.GREEN)
            return
        self.set_status("正在连接游戏…", "通常只需要几秒，请不要关闭游戏。", self.BLUE)
        self.set_attach_button("正在连接，请稍候…", self.tk.DISABLED)
        threading.Thread(target=self.manager.attach, daemon=True).start()

    def selected_path(self) -> Optional[Path]:
        selected = self.tree.selection()
        return Path(selected[0]) if selected else None

    def show_replay_menu(self, event) -> str:
        row = self.tree.identify_row(event.y)
        if not row:
            return "break"
        self.tree.selection_set(row)
        self.tree.focus(row)
        self.update_action_states()
        try:
            self.replay_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.replay_menu.grab_release()
        return "break"

    def scroll_replay_list(self, event) -> str:
        self.tree.yview_scroll(int(-event.delta / 120), "units")
        return "break"

    def arm_selected(self) -> None:
        path = self.selected_path()
        if path is None:
            self.set_status("还没有选择文件", "请先在下方列表中点选一条回放。", self.AMBER)
            return
        if not self.manager.attached:
            self.set_status("请先连接游戏", "点击第 1 个蓝色按钮，连接成功后再播放本地文件。", self.AMBER)
            return
        try:
            self.manager.arm_override(path)
            self.update_action_states()
        except Exception as exc:
            self.set_status("准备本地回放失败", "{error}", self.RED, detail_values={"error": exc})
            self.append_log(str(exc))

    def cancel_playback(self) -> None:
        if not self.manager.override_armed:
            self.update_action_states()
            return
        self.manager.cancel_override()
        self.update_action_states()

    def rename_selected(self) -> None:
        path = self.selected_path()
        if path is None:
            self.set_status("还没有选择文件", "请先在列表中选择要重命名的回放。", self.AMBER)
            return
        self.show_rename_dialog(path)

    def show_rename_dialog(self, path: Path) -> None:
        if self.rename_window is not None and self.rename_window.winfo_exists():
            self.rename_window.lift()
            self.rename_window.focus_force()
            return

        window = self.tk.Toplevel(self.root)
        window.withdraw()
        self.rename_window = window
        window.title(self.tr("重命名回放"))
        window.resizable(False, False)
        window.configure(bg=self.CARD)
        window.transient(self.root)

        body = self.tk.Frame(window, bg=self.CARD, padx=26, pady=22)
        body.pack(fill=self.tk.BOTH, expand=True)

        heading = self.tk.Frame(body, bg=self.CARD)
        heading.pack(fill=self.tk.X)
        self.tk.Label(
            heading,
            text="✎",
            bg="#E8F0FE",
            fg=self.BLUE,
            width=3,
            height=1,
            font=("Segoe UI Symbol", 14, "bold"),
        ).pack(side=self.tk.LEFT, padx=(0, 13))
        heading_text = self.tk.Frame(heading, bg=self.CARD)
        heading_text.pack(side=self.tk.LEFT, fill=self.tk.X, expand=True)
        self.tk.Label(
            heading_text,
            text=self.tr("重命名回放"),
            bg=self.CARD,
            fg=self.TEXT,
            anchor=self.tk.W,
            font=("Microsoft YaHei UI", 15, "bold"),
        ).pack(fill=self.tk.X)
        self.tk.Label(
            heading_text,
            text=self.tr("起一个容易辨认的名称，回放内容不会改变。"),
            bg=self.CARD,
            fg=self.MUTED,
            anchor=self.tk.W,
            font=("Microsoft YaHei UI", 9),
        ).pack(fill=self.tk.X, pady=(3, 0))

        self.tk.Label(
            body,
            text=self.tr("回放名称"),
            bg=self.CARD,
            fg=self.TEXT,
            anchor=self.tk.W,
            font=("Microsoft YaHei UI", 9, "bold"),
        ).pack(fill=self.tk.X, pady=(22, 7))

        input_border = self.tk.Frame(
            body,
            bg=self.CARD,
            highlightbackground=self.BORDER,
            highlightcolor=self.BLUE,
            highlightthickness=1,
        )
        input_border.pack(fill=self.tk.X)
        name_var = self.tk.StringVar(value=path.stem)
        entry = self.tk.Entry(
            input_border,
            textvariable=name_var,
            bg=self.CARD,
            fg=self.TEXT,
            insertbackground=self.BLUE,
            selectbackground="#D2E3FC",
            selectforeground=self.TEXT,
            relief=self.tk.FLAT,
            borderwidth=0,
            font=("Microsoft YaHei UI", 10),
        )
        entry.pack(side=self.tk.LEFT, fill=self.tk.X, expand=True, padx=(12, 6), pady=10)
        self.tk.Label(
            input_border,
            text=".replay",
            bg=self.CARD,
            fg=self.MUTED,
            font=("Segoe UI", 9),
        ).pack(side=self.tk.RIGHT, padx=(0, 12))

        error_var = self.tk.StringVar(value="")
        error_label = self.tk.Label(
            body,
            textvariable=error_var,
            bg=self.CARD,
            fg=self.DANGER_TEXT,
            anchor=self.tk.W,
            justify=self.tk.LEFT,
            wraplength=470,
            font=("Microsoft YaHei UI", 8),
        )
        error_label.pack(fill=self.tk.X, pady=(6, 0))

        def close_dialog() -> None:
            if self.rename_window is not None:
                self.rename_window.destroy()
                self.rename_window = None
        self.delete_window = None

        def submit_rename(_event=None) -> None:
            try:
                new_path = self.store.rename(path, name_var.get())
                self.manager.replace_selected_path(path, new_path)
                close_dialog()
                self.refresh()
                if self.tree.exists(str(new_path)):
                    self.tree.selection_set(str(new_path))
                    self.tree.focus(str(new_path))
                    self.tree.see(str(new_path))
                self.update_action_states()
                self.set_status(
                    "重命名成功",
                    "新的名称是 {name}",
                    self.GREEN,
                    detail_values={"name": new_path.name},
                )
                self.append_log(self.tr("已将 {old} 重命名为 {new}", old=path.name, new=new_path.name))
            except FileNotFoundError:
                close_dialog()
                self.set_status("文件已经不存在", "列表已自动刷新。", self.AMBER)
                self.refresh()
            except Exception as exc:
                error_var.set(str(exc))
                input_border.configure(
                    highlightbackground=self.DANGER_TEXT,
                    highlightcolor=self.DANGER_TEXT,
                    highlightthickness=2,
                )
                entry.focus_set()
                entry.selection_range(0, self.tk.END)

        actions = self.tk.Frame(body, bg=self.CARD)
        actions.pack(fill=self.tk.X, pady=(18, 0))
        self._button(actions, self.tr("重命名"), submit_rename, primary=True).pack(side=self.tk.RIGHT)
        self._button(actions, self.tr("取消"), close_dialog).pack(side=self.tk.RIGHT, padx=(0, 9))

        def show_focus() -> None:
            if not error_var.get():
                input_border.configure(
                    highlightbackground=self.BLUE,
                    highlightcolor=self.BLUE,
                    highlightthickness=2,
                )

        def hide_focus() -> None:
            if not error_var.get():
                input_border.configure(
                    highlightbackground=self.BORDER,
                    highlightcolor=self.BLUE,
                    highlightthickness=1,
                )

        def clear_error(*_args) -> None:
            if error_var.get():
                error_var.set("")
                input_border.configure(
                    highlightbackground=self.BLUE,
                    highlightcolor=self.BLUE,
                    highlightthickness=2,
                )

        name_var.trace_add("write", clear_error)
        entry.bind("<FocusIn>", lambda _event: show_focus())
        entry.bind("<FocusOut>", lambda _event: hide_focus())
        entry.bind("<Return>", submit_rename)
        window.bind("<Escape>", lambda _event: close_dialog())
        window.protocol("WM_DELETE_WINDOW", close_dialog)
        self.show_centered_dialog(window, 540, 340)
        window.grab_set()
        entry.focus_set()
        entry.selection_range(0, self.tk.END)

    def delete_selected(self) -> None:
        path = self.selected_path()
        if path is None:
            self.set_status("还没有选择文件", "请先在列表中选择要删除的回放。", self.AMBER)
            return
        self.show_delete_dialog(path)

    def show_delete_dialog(self, path: Path) -> None:
        if self.delete_window is not None and self.delete_window.winfo_exists():
            self.delete_window.lift()
            self.delete_window.focus_force()
            return

        window = self.tk.Toplevel(self.root)
        window.withdraw()
        self.delete_window = window
        window.title(self.tr("删除回放"))
        window.resizable(False, False)
        window.configure(bg=self.CARD)
        window.transient(self.root)

        body = self.tk.Frame(window, bg=self.CARD, padx=26, pady=24)
        body.pack(fill=self.tk.BOTH, expand=True)
        heading = self.tk.Frame(body, bg=self.CARD)
        heading.pack(fill=self.tk.X)
        self.tk.Label(
            heading,
            text="!",
            bg=self.DANGER_BG,
            fg=self.DANGER_TEXT,
            width=3,
            height=1,
            font=("Segoe UI", 14, "bold"),
        ).pack(side=self.tk.LEFT, anchor=self.tk.N, padx=(0, 14))
        heading_text = self.tk.Frame(heading, bg=self.CARD)
        heading_text.pack(side=self.tk.LEFT, fill=self.tk.X, expand=True)
        self.tk.Label(
            heading_text,
            text=self.tr("删除回放"),
            bg=self.CARD,
            fg=self.TEXT,
            anchor=self.tk.W,
            font=("Microsoft YaHei UI", 15, "bold"),
        ).pack(fill=self.tk.X)
        self.tk.Label(
            heading_text,
            text=self.tr("此操作无法撤销。删除后，这条回放将从本地永久移除。"),
            bg=self.CARD,
            fg=self.MUTED,
            anchor=self.tk.W,
            justify=self.tk.LEFT,
            wraplength=410,
            font=("Microsoft YaHei UI", 9),
        ).pack(fill=self.tk.X, pady=(5, 0))

        self.tk.Label(
            body,
            text=self.tr("要删除的文件"),
            bg=self.CARD,
            fg=self.MUTED,
            anchor=self.tk.W,
            font=("Microsoft YaHei UI", 9, "bold"),
        ).pack(fill=self.tk.X, pady=(20, 7))
        file_surface = self.tk.Frame(
            body,
            bg="#F8FAFD",
            highlightbackground=self.BORDER,
            highlightcolor=self.BORDER,
            highlightthickness=1,
        )
        file_surface.pack(fill=self.tk.X)
        self.tk.Label(
            file_surface,
            text=path.name,
            bg="#F8FAFD",
            fg=self.TEXT,
            anchor=self.tk.W,
            justify=self.tk.LEFT,
            wraplength=440,
            padx=12,
            pady=10,
            font=("Microsoft YaHei UI", 9),
        ).pack(fill=self.tk.X)

        def confirm_delete() -> None:
            self.close_delete_dialog()
            try:
                if self.manager.override_armed and self.manager.selected == path:
                    self.manager.cancel_override(notify=False)
                self.store.delete(path)
                self.set_status(
                    "回放已删除",
                    "{name} 已从本地删除。",
                    self.GREEN,
                    detail_values={"name": path.name},
                )
                self.append_log(self.tr("已删除 {name}", name=path.name))
                self.refresh()
            except FileNotFoundError:
                self.set_status("文件已经不存在", "列表已自动刷新。", self.AMBER)
                self.refresh()
            except Exception as exc:
                self.set_status("删除失败", "{error}", self.RED, detail_values={"error": exc})
                self.append_log(self.tr("删除失败：{error}", error=exc))

        actions = self.tk.Frame(body, bg=self.CARD)
        actions.pack(fill=self.tk.X, pady=(22, 0))
        delete_button = self._button(actions, self.tr("删除"), confirm_delete, danger=True)
        delete_button.pack(side=self.tk.RIGHT)
        self._button(actions, self.tr("取消"), self.close_delete_dialog).pack(side=self.tk.RIGHT, padx=(0, 9))

        window.bind("<Escape>", lambda _event: self.close_delete_dialog())
        window.protocol("WM_DELETE_WINDOW", self.close_delete_dialog)
        self.show_centered_dialog(window, 520, 330)
        window.grab_set()
        delete_button.focus_set()

    def close_delete_dialog(self) -> None:
        if self.delete_window is not None:
            self.delete_window.destroy()
            self.delete_window = None

    def refresh(self) -> None:
        selected = self.selected_path() if hasattr(self, "tree") else None
        self.tree.delete(*self.tree.get_children())
        paths = self.store.list()
        for path in paths:
            stat = path.stat()
            self.tree.insert(
                "",
                self.tk.END,
                iid=str(path),
                text=path.name,
                image=self.empty_replay_marker,
                values=(datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"), f"{stat.st_size / 1024:.1f} KB"),
            )
        self.library_title.set(self.tr("已保存的回放（{count}）", count=len(paths)))
        if selected and self.tree.exists(str(selected)):
            self.tree.selection_set(str(selected))
        self.schedule_replay_column_resize()
        self.update_action_states()

    def open_folder(self) -> None:
        self.store.directory.mkdir(parents=True, exist_ok=True)
        if os.name == "nt":
            os.startfile(self.store.directory)  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", str(self.store.directory)])

    def poll_events(self) -> None:
        try:
            while True:
                kind, data = self.events.get_nowait()
                if kind == "attached":
                    details = data if isinstance(data, dict) else {"pid": data, "game_version": None}
                    pid = details.get("pid")
                    game_version = details.get("game_version")
                    if game_version and game_version != SUPPORTED_GAME_VERSION:
                        self.set_status(
                            "游戏版本可能不兼容",
                            "检测到 Master Duel {game}，本程序适配 {supported}。请前往 GitHub 获取新版。",
                            self.RED,
                            detail_values={"game": game_version, "supported": SUPPORTED_GAME_VERSION},
                        )
                        self.append_log(
                            self.tr(
                                "版本不匹配：游戏 {game}，程序适配 {supported}",
                                game=game_version,
                                supported=SUPPORTED_GAME_VERSION,
                            )
                        )
                    else:
                        version_detail = (
                            self.tr("已确认游戏版本 {version}。", version=game_version) if game_version else ""
                        )
                        self.set_status(
                            "连接成功，自动保存已开启",
                            "{version_detail}现在去游戏里播放回放；播放过的内容会自动出现在下方。",
                            self.GREEN,
                            detail_values={"version_detail": version_detail},
                        )
                    self.set_attach_button("已连接 · 自动保存运行中", self.tk.NORMAL)
                    self.append_log(
                        self.tr(
                            "已连接 Master Duel（PID {pid}，游戏版本 {version}）",
                            pid=pid,
                            version=game_version or self.tr("未读取"),
                        )
                    )
                elif kind == "ready":
                    version = data.get("version", APP_VERSION) if isinstance(data, dict) else APP_VERSION
                    game_version = data.get("gameVersion") if isinstance(data, dict) else None
                    self.append_log(
                        self.tr(
                            "回放组件已就绪（{version}，游戏版本 {game}）",
                            version=version,
                            game=game_version or self.tr("未读取"),
                        )
                    )
                elif kind == "waiting":
                    self.set_status("没有找到 Master Duel", "请先启动游戏并进入主界面，然后重新点击连接。", self.AMBER)
                    self.set_attach_button("1. 重新连接游戏", self.tk.NORMAL)
                elif kind == "saved":
                    self.set_status(
                        "保存成功",
                        "{name} 已加入下方列表。",
                        self.GREEN,
                        detail_values={"name": Path(data).name},
                    )
                    self.append_log(self.tr("已保存 {name}", name=Path(data).name))
                    self.refresh()
                elif kind == "duplicate":
                    self.set_status("这条回放已经保存过", "程序不会重复保存，因此不会浪费磁盘空间。", self.GREEN)
                    self.append_log(self.tr("跳过重复文件 {name}", name=Path(data).name))
                elif kind == "armed":
                    self.set_status("本地回放已经准备好", "现在回到游戏，播放任意一条可用回放。", self.BLUE)
                    self.append_log(self.tr("下一次播放将使用 {name}", name=Path(data).name))
                    self.update_action_states()
                elif kind == "cancelled":
                    self.set_status("已取消回放", "不会再替换下一条游戏回放，自动保存仍在运行。", self.GREEN)
                    self.append_log(self.tr("已取消准备好的本地回放"))
                    self.update_action_states()
                elif kind == "loaded":
                    self.set_status("本地回放已送入游戏", "本次播放已替换；程序现在自动恢复保存模式。", self.GREEN)
                    self.append_log(self.tr("已加载 {name}", name=Path(data).name))
                    self.update_action_states()
                elif kind == "detached":
                    self.set_status("游戏连接已断开", "如果游戏仍在运行，请点击按钮重新连接。", self.AMBER)
                    self.set_attach_button("1. 重新连接游戏", self.tk.NORMAL)
                    self.append_log(self.tr("连接断开：{detail}", detail=data))
                    self.update_action_states()
                elif kind == "error":
                    self.set_status(
                        "连接或运行失败",
                        "{error}",
                        self.RED,
                        detail_values={"error": data},
                    )
                    self.set_attach_button("1. 重试连接", self.tk.NORMAL)
                    self.append_log(self.tr("错误：{error}", error=data))
                elif kind == "log":
                    self.append_log(str(data))
        except queue.Empty:
            pass
        self.root.after(150, self.poll_events)

    def close(self) -> None:
        self.manager.detach()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def run_headless(data_dir: Path) -> int:
    events: queue.Queue[tuple[str, object]] = queue.Queue()
    manager = ReplayManager(ReplayStore(data_dir), lambda kind, data=None: events.put((kind, data)))
    print(f"{APP_NAME} {APP_VERSION} — replay folder: {data_dir}")
    try:
        while not manager.attach():
            try:
                kind, data = events.get_nowait()
                print(f"[{kind}] {data}")
            except queue.Empty:
                pass
            time.sleep(5)
        while True:
            kind, data = events.get()
            print(f"[{kind}] {data}")
    except KeyboardInterrupt:
        return 0
    finally:
        manager.detach()


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Capture and replay Master Duel replay packets")
    parser.add_argument("--headless", action="store_true", help="run without the Tk GUI")
    parser.add_argument("--data-dir", type=Path, help="directory used for .replay files")
    args = parser.parse_args(argv)
    data_dir = (args.data_dir or default_data_dir()).resolve()
    if args.headless:
        return run_headless(data_dir)
    ReplayApp(data_dir).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
