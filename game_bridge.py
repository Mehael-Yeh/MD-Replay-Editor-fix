"""Master Duel process lifecycle and Frida replay bridge."""

from __future__ import annotations

import math
import os
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Optional

from app_i18n import AGENT_MESSAGE_TEMPLATES
from replay_store import ReplayStore, validate_replay_hex


READY_TIMEOUT_SECONDS = 20
GAME_LAUNCH_TIMEOUT_SECONDS = 180
GAME_PROCESS_NAMES = frozenset({"masterduel.exe", "masterduel"})
MASTER_DUEL_STEAM_URI = "steam://rungameid/1449850"


def resource_path(*parts: str) -> Path:
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return root.joinpath(*parts)


def find_master_duel_process(device):
    return next(
        (process for process in device.enumerate_processes() if process.name.lower() in GAME_PROCESS_NAMES),
        None,
    )


def launch_master_duel() -> None:
    if os.name != "nt" or not hasattr(os, "startfile"):
        raise RuntimeError("自动启动游戏目前只支持 Windows")
    os.startfile(MASTER_DUEL_STEAM_URI)  # type: ignore[attr-defined]


def wait_for_master_duel_process(
    device,
    timeout: float = GAME_LAUNCH_TIMEOUT_SECONDS,
    poll_interval: float = 1.0,
):
    attempts = max(1, math.ceil(timeout / poll_interval))
    for attempt in range(attempts):
        process = find_master_duel_process(device)
        if process is not None:
            return process
        if attempt + 1 < attempts:
            time.sleep(poll_interval)
    return None


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
        self.direct_pending = False
        self.direct_fallback = False
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
        if event_type in {
            "direct_play_queued",
            "direct_play_started",
            "direct_play_progress",
            "direct_play_triggered",
            "direct_play_carrier_received",
        }:
            event_names = {
                "direct_play_queued": "direct_queued",
                "direct_play_started": "direct_started",
                "direct_play_progress": "direct_progress",
                "direct_play_triggered": "direct_triggered",
                "direct_play_carrier_received": "direct_carrier_received",
            }
            self.emit(event_names[event_type], data)
            return
        if event_type in {"direct_play_blocked", "direct_play_failed"}:
            details = data if isinstance(data, dict) else {}
            fallback = bool(details.get("fallback")) and event_type == "direct_play_blocked"
            with self._lock:
                selected = self.selected
                self.direct_pending = False
                self.direct_fallback = False
                if not fallback:
                    self.override_armed = False
            if fallback and selected:
                self.emit("direct_fallback", {"path": selected, "top_class": details.get("topClass")})
            elif event_type == "direct_play_blocked":
                self.emit("direct_blocked", details.get("topClass"))
            else:
                self.emit("direct_failed", str(details.get("reason") or self.tr("直接播放失败")))
            return
        if event_type == "direct_play_cancelled":
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
                    self.direct_pending = False
                    self.direct_fallback = False

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
            self.direct_pending = False
            self.direct_fallback = False
        detail = f"{reason}"
        if crash:
            detail += f" ({crash})"
        self.emit("detached", detail)

    def attach(self, launch_if_missing: bool = False) -> bool:
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
            process = find_master_duel_process(device)
            if process is None and launch_if_missing:
                self.emit("launching", self.tr("正在通过 Steam 启动 Master Duel"))
                launch_master_duel()
                process = wait_for_master_duel_process(device)
            if process is None:
                detail = (
                    self.tr(
                        "启动后 {seconds} 秒内未检测到 Master Duel",
                        seconds=GAME_LAUNCH_TIMEOUT_SECONDS,
                    )
                    if launch_if_missing
                    else self.tr("未检测到 Master Duel，请先启动游戏")
                )
                self.emit("waiting", detail)
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
                raise RuntimeError(self.tr("请先点击“启动/连接游戏并自动保存”"))
            if self.direct_pending:
                raise RuntimeError(self.tr("直接播放请求正在处理中"))
            self.selected = path
            self.override_armed = True
        self.emit("armed", path)

    def request_direct_play(self, path: Path, fallback_to_next: bool) -> None:
        self.store.read(path)
        with self._lock:
            if not self.attached or self.script is None:
                raise RuntimeError(self.tr("请先点击“启动/连接游戏并自动保存”"))
            if self.direct_pending:
                raise RuntimeError(self.tr("直接播放请求正在处理中"))
            script = self.script
            self.selected = path
            self.override_armed = True
            self.direct_pending = True
            self.direct_fallback = fallback_to_next
        try:
            script.post({"type": "direct_play", "fallback": fallback_to_next})
        except Exception:
            with self._lock:
                self.override_armed = False
                self.direct_pending = False
                self.direct_fallback = False
            raise
        self.emit("direct_requested", {"path": path, "fallback": fallback_to_next})

    def cancel_override(self, notify: bool = True) -> None:
        with self._lock:
            script = self.script
            was_direct = self.direct_pending
            self.override_armed = False
            self.direct_pending = False
            self.direct_fallback = False
        if was_direct and script is not None:
            try:
                script.post({"type": "cancel_direct_play"})
            except Exception:
                pass
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
            self.direct_pending = False
            self.direct_fallback = False
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
