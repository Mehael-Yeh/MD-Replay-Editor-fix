#!/usr/bin/env python3
"""Portable GUI for capturing and replaying Master Duel replay packets."""

from __future__ import annotations

import argparse
import hashlib
import os
import queue
import re
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional


APP_NAME = "MD-Replay-Editor-fix"
APP_VERSION = "v2.7.0_R1"
REPLAY_MARKER = b"replaym"
HEX_RE = re.compile(r"^[0-9a-fA-F]+$")
READY_TIMEOUT_SECONDS = 20


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


def validate_replay_hex(value: str) -> str:
    value = "".join(value.split()).lower()
    if not value or len(value) % 2 or not HEX_RE.fullmatch(value):
        raise ValueError("文件不是有效的十六进制回放数据")
    raw = bytes.fromhex(value)
    if REPLAY_MARKER not in raw:
        raise ValueError("文件中未找到 Master Duel 回放标记")
    return value


@dataclass(frozen=True)
class SavedReplay:
    path: Path
    created: bool


class ReplayStore:
    def __init__(self, directory: Path):
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)

    def list(self) -> list[Path]:
        return sorted(self.directory.glob("*.replay"), key=lambda p: p.stat().st_mtime, reverse=True)

    def read(self, path: Path) -> str:
        return validate_replay_hex(path.read_text(encoding="ascii"))

    def save(self, replay_hex: str) -> SavedReplay:
        replay_hex = validate_replay_hex(replay_hex)
        digest = hashlib.sha256(bytes.fromhex(replay_hex)).hexdigest()[:12]
        existing = next(self.directory.glob(f"*_{digest}.replay"), None)
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
    def __init__(self, store: ReplayStore, event_sink: Optional[Callable[[str, object], None]] = None):
        self.store = store
        self.event_sink = event_sink or (lambda _kind, _data: None)
        self.session = None
        self.script = None
        self.attached = False
        self.selected: Optional[Path] = None
        self.override_armed = False
        self.saved = 0
        self._lock = threading.RLock()
        self._ready_event = threading.Event()
        self._startup_error: Optional[str] = None

    def emit(self, kind: str, data: object = None) -> None:
        self.event_sink(kind, data)

    def _reply(self, replay_hex: str) -> None:
        script = self.script
        if script is not None:
            script.post({"type": "replay_reply", "replay": replay_hex})

    def _on_message(self, message, _binary_data) -> None:
        if message.get("type") == "error":
            detail = message.get("stack") or message.get("description") or "代理发生未知错误"
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
            self._ready_event.set()
            self.emit("ready", data)
            return
        if event_type == "fatal":
            detail = str(data or "代理初始化失败")
            with self._lock:
                starting = not self.attached
                if starting:
                    self._startup_error = detail
                    self._ready_event.set()
            if not starting:
                self.emit("error", detail)
            return
        if event_type == "log":
            self.emit("log", data)
            return
        if event_type != "replay_packet" or not isinstance(data, dict):
            return

        original = data.get("hex", "")
        reply = original
        try:
            validate_replay_hex(original)
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
            self.emit("error", f"处理回放失败：{exc}")
            reply = original
        finally:
            # DeserializeAsync is waiting synchronously; always release it.
            self._reply(reply)

    def _on_detached(self, reason, crash=None) -> None:
        with self._lock:
            if not self.attached and self._startup_error is None:
                self._startup_error = f"代理启动期间连接断开：{reason}"
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
            self.emit("error", "缺少 Frida 运行库，请使用 Release 中的完整 EXE")
            return False

        agent = resource_path("agent", "_.js")
        if not agent.exists():
            self.emit("error", "未找到已编译代理 agent/_.js")
            return False

        try:
            device = frida.get_local_device()
            process = next(
                (p for p in device.enumerate_processes() if p.name.lower() in {"masterduel.exe", "masterduel"}),
                None,
            )
            if process is None:
                self.emit("waiting", "未检测到 Master Duel，请先启动游戏")
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
                raise RuntimeError(f"代理在 {READY_TIMEOUT_SECONDS} 秒内没有就绪")
            with self._lock:
                if self._startup_error:
                    raise RuntimeError(self._startup_error)
                self.attached = True
            self.emit("attached", process.pid)
            return True
        except Exception as exc:
            self.emit("error", f"连接游戏失败：{exc}")
            self.detach()
            return False

    def arm_override(self, path: Path) -> None:
        self.store.read(path)
        with self._lock:
            if not self.attached:
                raise RuntimeError("请先点击“连接游戏并开始自动保存”")
            self.selected = path
            self.override_armed = True
        self.emit("armed", path)

    def cancel_override(self) -> None:
        with self._lock:
            self.override_armed = False
        self.emit("cancelled")

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
    AMBER = "#F9AB00"

    def __init__(self, data_dir: Path):
        import tkinter as tk
        from tkinter import ttk

        self.tk = tk
        self.ttk = ttk
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.store = ReplayStore(data_dir)
        self.manager = ReplayManager(self.store, lambda kind, data=None: self.events.put((kind, data)))

        root = tk.Tk()
        self.root = root
        root.title(f"{APP_NAME} {APP_VERSION}")
        root.geometry("960x760")
        root.minsize(840, 680)
        root.configure(bg=self.BG)

        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure(
            "Replay.Treeview",
            background=self.CARD,
            fieldbackground=self.CARD,
            foreground=self.TEXT,
            rowheight=34,
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
            padding=(8, 8),
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
        tk.Label(
            title_line,
            text="Master Duel 回放助手",
            bg=self.CARD,
            fg=self.TEXT,
            font=("Microsoft YaHei UI", 16, "bold"),
        ).pack(side=tk.LEFT)
        tk.Label(
            title_line,
            text=APP_VERSION,
            bg="#E8F0FE",
            fg=self.BLUE,
            padx=9,
            pady=3,
            font=("Segoe UI", 9, "bold"),
        ).pack(side=tk.LEFT, padx=(12, 0))
        tk.Label(
            title_area,
            text="自动保存看过的回放，也能把本地回放重新放进游戏播放",
            bg=self.CARD,
            fg=self.MUTED,
            font=("Microsoft YaHei UI", 9),
        ).pack(anchor=tk.W, pady=(5, 0))

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
        self.status_title = tk.StringVar(value="还没有连接游戏")
        self.status_detail = tk.StringVar(value="先打开 Master Duel，再点击下面的蓝色按钮。")
        tk.Label(
            status_text,
            textvariable=self.status_title,
            bg=self.CARD,
            fg=self.TEXT,
            anchor=tk.W,
            font=("Microsoft YaHei UI", 12, "bold"),
        ).pack(fill=tk.X)
        tk.Label(
            status_text,
            textvariable=self.status_detail,
            bg=self.CARD,
            fg=self.MUTED,
            anchor=tk.W,
            font=("Microsoft YaHei UI", 9),
        ).pack(fill=tk.X, pady=(3, 0))

        action_bar = tk.Frame(status_card, bg=self.CARD)
        action_bar.pack(fill=tk.X, padx=20, pady=(0, 18))
        self.attach_button = self._button(
            action_bar,
            "1. 连接游戏并开始自动保存",
            self.start_attach,
            primary=True,
        )
        self.attach_button.pack(side=tk.LEFT)
        self.play_button = self._button(
            action_bar,
            "2. 用所选文件在游戏里回放",
            self.arm_selected,
        )
        self.play_button.pack(side=tk.LEFT, padx=(10, 0))

        guide_card = self._card(content)
        guide_card.pack(fill=tk.X, pady=(14, 0))
        tk.Label(
            guide_card,
            text="第一次使用？照着这 3 步做",
            bg=self.CARD,
            fg=self.TEXT,
            font=("Microsoft YaHei UI", 11, "bold"),
        ).pack(anchor=tk.W, padx=20, pady=(15, 8))
        steps = tk.Frame(guide_card, bg=self.CARD)
        steps.pack(fill=tk.X, padx=14, pady=(0, 15))
        self._step(steps, "1", "连接游戏", "打开游戏，再点上方蓝色按钮。").pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)
        self._step(steps, "2", "播放想保存的回放", "回到游戏，正常播放一条回放。").pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)
        self._step(steps, "3", "保存完成", "看到“保存成功”，就完成了。").pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)

        library_card = self._card(content)
        library_card.pack(fill=tk.BOTH, expand=True, pady=(14, 0))
        library_card.columnconfigure(0, weight=1)
        library_card.rowconfigure(1, weight=1)
        library_header = tk.Frame(library_card, bg=self.CARD)
        library_header.grid(row=0, column=0, sticky="ew", padx=18, pady=(10, 7))
        self.library_title = tk.StringVar(value="已保存的回放")
        tk.Label(
            library_header,
            textvariable=self.library_title,
            bg=self.CARD,
            fg=self.TEXT,
            font=("Microsoft YaHei UI", 11, "bold"),
        ).pack(side=tk.LEFT)
        self._link_button(library_header, "打开保存位置", self.open_folder).pack(side=tk.RIGHT)
        self._link_button(library_header, "刷新列表", self.refresh).pack(side=tk.RIGHT, padx=(0, 8))

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
        scrollbar = ttk.Scrollbar(tree_area, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.heading("#0", text="文件名")
        self.tree.heading("time", text="保存时间")
        self.tree.heading("size", text="文件大小")
        self.tree.column("#0", width=520, minwidth=260)
        self.tree.column("time", width=165, minwidth=145, anchor=tk.CENTER)
        self.tree.column("size", width=95, minwidth=80, anchor=tk.E)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.bind("<<TreeviewSelect>>", lambda _event: self.update_action_states())
        self.tree.bind("<Double-1>", lambda _event: self.arm_selected())

        tip = tk.Label(
            library_card,
            text=(
                "播放本地文件：先选中一行并点击第 2 个按钮，再回到游戏播放任意一条可用回放。"
                "程序只替换这一次播放，之后会自动恢复保存模式。"
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
        tip.grid(row=2, column=0, sticky="ew", padx=18, pady=(6, 5))

        log_header = tk.Frame(library_card, bg=self.CARD)
        log_header.grid(row=3, column=0, sticky="ew", padx=18)
        tk.Label(
            log_header,
            text="运行记录（遇到问题时查看）",
            bg=self.CARD,
            fg=self.MUTED,
            font=("Microsoft YaHei UI", 9, "bold"),
        ).pack(side=tk.LEFT)
        self.log = tk.Text(
            library_card,
            height=2,
            state=tk.DISABLED,
            bg="#F8FAFD",
            fg="#3C4043",
            relief=tk.FLAT,
            padx=10,
            pady=7,
            font=("Cascadia Mono", 8),
        )
        self.log.grid(row=4, column=0, sticky="ew", padx=18, pady=(4, 10))

        root.protocol("WM_DELETE_WINDOW", self.close)
        self.refresh()
        self.update_action_states()
        root.after(150, self.poll_events)

    def _card(self, parent):
        return self.tk.Frame(
            parent,
            bg=self.CARD,
            highlightbackground=self.BORDER,
            highlightcolor=self.BORDER,
            highlightthickness=1,
        )

    def _button(self, parent, text: str, command, primary: bool = False):
        bg = self.BLUE if primary else self.CARD
        fg = "#FFFFFF" if primary else self.BLUE
        hover = self.BLUE_HOVER if primary else "#E8F0FE"
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
            padx=18,
            pady=10,
            cursor="hand2",
            font=("Microsoft YaHei UI", 9, "bold"),
        )
        button.bind("<Enter>", lambda _event: button.configure(bg=hover) if button["state"] == self.tk.NORMAL else None)
        button.bind("<Leave>", lambda _event: button.configure(bg=bg) if button["state"] == self.tk.NORMAL else None)
        return button

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

    def _step(self, parent, number: str, title: str, detail: str):
        frame = self.tk.Frame(parent, bg="#F8FAFD", padx=12, pady=10)
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
            wraplength=210,
            font=("Microsoft YaHei UI", 8),
        ).pack(fill=self.tk.X, pady=(2, 0))
        return frame

    def set_status(self, title: str, detail: str, color: str) -> None:
        self.status_title.set(title)
        self.status_detail.set(detail)
        self.status_dot.configure(fg=color)

    def append_log(self, text: str) -> None:
        self.log.configure(state=self.tk.NORMAL)
        self.log.insert(self.tk.END, f"[{time.strftime('%H:%M:%S')}] {text}\n")
        if int(self.log.index("end-1c").split(".")[0]) > 200:
            self.log.delete("1.0", "50.0")
        self.log.see(self.tk.END)
        self.log.configure(state=self.tk.DISABLED)

    def update_action_states(self) -> None:
        has_selection = self.selected_path() is not None
        self.play_button.configure(state=self.tk.NORMAL if has_selection else self.tk.DISABLED)

    def start_attach(self) -> None:
        if self.manager.attached:
            self.set_status("已经连接游戏", "自动保存正在运行，不需要重复点击。", self.GREEN)
            return
        self.set_status("正在连接游戏…", "通常只需要几秒，请不要关闭游戏。", self.BLUE)
        self.attach_button.configure(state=self.tk.DISABLED, text="正在连接，请稍候…")
        threading.Thread(target=self.manager.attach, daemon=True).start()

    def selected_path(self) -> Optional[Path]:
        selected = self.tree.selection()
        return Path(selected[0]) if selected else None

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
        except Exception as exc:
            self.set_status("准备本地回放失败", str(exc), self.RED)
            self.append_log(str(exc))

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
                values=(datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"), f"{stat.st_size / 1024:.1f} KB"),
            )
        self.library_title.set(f"已保存的回放（{len(paths)}）")
        if selected and self.tree.exists(str(selected)):
            self.tree.selection_set(str(selected))
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
                    self.set_status("连接成功，自动保存已开启", "现在去游戏里播放回放；播放过的内容会自动出现在下方。", self.GREEN)
                    self.attach_button.configure(state=self.tk.NORMAL, text="已连接 · 自动保存运行中")
                    self.append_log(f"已连接 Master Duel（PID {data}）")
                elif kind == "ready":
                    version = data.get("version", APP_VERSION) if isinstance(data, dict) else APP_VERSION
                    self.append_log(f"回放组件已就绪（{version}）")
                elif kind == "waiting":
                    self.set_status("没有找到 Master Duel", "请先启动游戏并进入主界面，然后重新点击连接。", self.AMBER)
                    self.attach_button.configure(state=self.tk.NORMAL, text="1. 重新连接游戏")
                elif kind == "saved":
                    self.set_status("保存成功", f"{Path(data).name} 已加入下方列表。", self.GREEN)
                    self.append_log(f"已保存 {Path(data).name}")
                    self.refresh()
                elif kind == "duplicate":
                    self.set_status("这条回放已经保存过", "程序不会重复保存，因此不会浪费磁盘空间。", self.GREEN)
                    self.append_log(f"跳过重复文件 {Path(data).name}")
                elif kind == "armed":
                    self.set_status("本地回放已经准备好", "现在回到游戏，播放任意一条可用回放。", self.BLUE)
                    self.append_log(f"下一次播放将使用 {Path(data).name}")
                elif kind == "loaded":
                    self.set_status("本地回放已送入游戏", "本次播放已替换；程序现在自动恢复保存模式。", self.GREEN)
                    self.append_log(f"已加载 {Path(data).name}")
                elif kind == "detached":
                    self.set_status("游戏连接已断开", "如果游戏仍在运行，请点击按钮重新连接。", self.AMBER)
                    self.attach_button.configure(state=self.tk.NORMAL, text="1. 重新连接游戏")
                    self.append_log(f"连接断开：{data}")
                elif kind == "error":
                    self.set_status("连接或运行失败", str(data), self.RED)
                    self.attach_button.configure(state=self.tk.NORMAL, text="1. 重试连接")
                    self.append_log(f"错误：{data}")
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
