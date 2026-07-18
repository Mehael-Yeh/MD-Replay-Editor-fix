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
REPLAY_MARKER = b"replaym"
HEX_RE = re.compile(r"^[0-9a-fA-F]+$")


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

    def emit(self, kind: str, data: object = None) -> None:
        self.event_sink(kind, data)

    def _reply(self, replay_hex: str) -> None:
        script = self.script
        if script is not None:
            script.post({"type": "replay_reply", "replay": replay_hex})

    def _on_message(self, message, _binary_data) -> None:
        if message.get("type") == "error":
            self.emit("error", message.get("stack") or message.get("description") or "代理发生未知错误")
            return
        if message.get("type") != "send":
            return

        payload = message.get("payload")
        if not isinstance(payload, dict):
            return
        event_type = payload.get("type")
        data = payload.get("data")

        if event_type == "ready":
            self.emit("ready", data)
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
            with self._lock:
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
                raise RuntimeError("请先点击“获取并监听”")
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
        root.title(APP_NAME)
        root.geometry("760x520")
        root.minsize(680, 440)

        frame = ttk.Frame(root, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)
        self.status = tk.StringVar(value="启动 Master Duel 后，点击“获取并监听”")
        ttk.Label(frame, textvariable=self.status, font=("Microsoft YaHei UI", 11)).pack(fill=tk.X)

        actions = ttk.Frame(frame)
        actions.pack(fill=tk.X, pady=(10, 10))
        self.attach_button = ttk.Button(actions, text="获取并监听", command=self.start_attach)
        self.attach_button.pack(side=tk.LEFT)
        self.play_button = ttk.Button(actions, text="借壳回放所选文件", command=self.arm_selected)
        self.play_button.pack(side=tk.LEFT, padx=8)
        ttk.Button(actions, text="打开回放文件夹", command=self.open_folder).pack(side=tk.LEFT)
        ttk.Button(actions, text="刷新", command=self.refresh).pack(side=tk.RIGHT)

        columns = ("time", "size")
        self.tree = ttk.Treeview(frame, columns=columns, show="tree headings", selectmode="browse")
        self.tree.heading("#0", text="本地回放文件")
        self.tree.heading("time", text="保存时间")
        self.tree.heading("size", text="大小")
        self.tree.column("#0", width=410)
        self.tree.column("time", width=150, anchor=tk.CENTER)
        self.tree.column("size", width=90, anchor=tk.E)
        self.tree.pack(fill=tk.BOTH, expand=True)
        self.tree.bind("<Double-1>", lambda _event: self.arm_selected())

        help_text = (
            "监听后，在游戏中播放任意回放即可自动保存。要播放本地文件：选中它并点击“借壳回放”，"
            "然后回到游戏播放任意一条官方回放；本次响应会被替换，触发一次后自动恢复抓取模式。"
        )
        ttk.Label(frame, text=help_text, wraplength=720, foreground="#555").pack(fill=tk.X, pady=(10, 0))

        self.log = tk.Text(frame, height=6, state=tk.DISABLED, font=("Consolas", 9))
        self.log.pack(fill=tk.X, pady=(8, 0))

        root.protocol("WM_DELETE_WINDOW", self.close)
        self.refresh()
        root.after(150, self.poll_events)

    def append_log(self, text: str) -> None:
        self.log.configure(state=self.tk.NORMAL)
        self.log.insert(self.tk.END, f"[{time.strftime('%H:%M:%S')}] {text}\n")
        self.log.see(self.tk.END)
        self.log.configure(state=self.tk.DISABLED)

    def start_attach(self) -> None:
        if self.manager.attached:
            self.status.set("已经在监听 Master Duel")
            return
        self.attach_button.configure(state=self.tk.DISABLED, text="连接中…")
        threading.Thread(target=self.manager.attach, daemon=True).start()

    def selected_path(self) -> Optional[Path]:
        selected = self.tree.selection()
        return Path(selected[0]) if selected else None

    def arm_selected(self) -> None:
        path = self.selected_path()
        if path is None:
            self.status.set("请先在列表中选择一个回放文件")
            return
        try:
            self.manager.arm_override(path)
        except Exception as exc:
            self.status.set(str(exc))
            self.append_log(str(exc))

    def refresh(self) -> None:
        selected = self.selected_path()
        self.tree.delete(*self.tree.get_children())
        for path in self.store.list():
            stat = path.stat()
            self.tree.insert(
                "",
                self.tk.END,
                iid=str(path),
                text=path.name,
                values=(datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"), f"{stat.st_size / 1024:.1f} KB"),
            )
        if selected and self.tree.exists(str(selected)):
            self.tree.selection_set(str(selected))

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
                    self.status.set(f"监听中（PID {data}）— 在游戏中播放回放即可自动保存")
                    self.attach_button.configure(state=self.tk.NORMAL, text="正在监听")
                    self.append_log(f"已连接 Master Duel，PID {data}")
                elif kind == "ready":
                    self.append_log("注入代理已就绪")
                elif kind == "waiting":
                    self.status.set(str(data))
                    self.attach_button.configure(state=self.tk.NORMAL, text="获取并监听")
                elif kind == "saved":
                    self.status.set(f"已保存：{Path(data).name}")
                    self.append_log(f"已保存 {Path(data).name}")
                    self.refresh()
                elif kind == "duplicate":
                    self.status.set(f"已抓取（文件已存在）：{Path(data).name}")
                    self.append_log(f"跳过重复回放 {Path(data).name}")
                elif kind == "armed":
                    self.status.set("借壳已就绪：回到游戏播放任意一条回放")
                    self.append_log(f"等待替换下一条回放：{Path(data).name}")
                elif kind == "loaded":
                    self.status.set(f"借壳完成：{Path(data).name}")
                    self.append_log(f"已把游戏响应替换为 {Path(data).name}")
                elif kind == "detached":
                    self.status.set("游戏已退出或连接断开，可重新点击“获取并监听”")
                    self.attach_button.configure(state=self.tk.NORMAL, text="获取并监听")
                    self.append_log(f"连接断开：{data}")
                elif kind == "error":
                    self.status.set(str(data))
                    self.attach_button.configure(state=self.tk.NORMAL, text="获取并监听")
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
    print(f"{APP_NAME} — replay folder: {data_dir}")
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
