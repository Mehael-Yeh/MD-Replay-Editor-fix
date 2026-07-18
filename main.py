#!/usr/bin/env python3
import os, sys, json, time, threading
from pathlib import Path

if getattr(sys, "frozen", False):
    BASE = Path(sys._MEIPASS)
else:
    BASE = Path(__file__).parent

REPLAY_DIR = BASE / "replays"
AGENT_JS = BASE / "agent" / "_.js"

class ReplayManager:
    def __init__(self):
        self.session = self.script = None
        self.running = self.limit_bypassed = False
        self.saved = 0
        REPLAY_DIR.mkdir(parents=True, exist_ok=True)

    def _on_msg(self, msg, data):
        if msg.get("type") != "send":
            return
        p = msg.get("payload", {})
        t, d = p.get("type",""), p.get("data",{})
        if t == "save_replay":
            (REPLAY_DIR / d.get("fileName","x.json")).write_text(d.get("content","{}"))
            self.saved += 1
            print(f"  Saved: {d.get('fileName','')}")
        elif t == "limit_bypassed":
            self.limit_bypassed = True
            print("  Limit bypassed!")
        elif t == "ready":
            self.running = True
            print("  Agent ready")
        elif t == "network_request":
            c = d or ""
            if c in ("Duel.begin","Duel.end","User.replay_list"):
                print(f"  >> {c}")

    def attach(self):
        try:
            import frida
        except ImportError:
            print("ERROR: pip install frida-tools"); return False
        if not AGENT_JS.exists():
            print(f"ERROR: build agent first: cd agent && npm run build"); return False
        try:
            dev = frida.get_local_device()
            pid = next((p.pid for p in dev.enumerate_processes() if "masterduel" in p.name.lower()), None)
            if not pid:
                print("ERROR: Master Duel not running"); return False
            print(f"Attached to PID {pid}")
            self.session = dev.attach(pid)
            self.script = self.session.create_script(AGENT_JS.read_text())
            self.script.on("message", self._on_msg)
            self.script.load()
            return True
        except Exception as e:
            print(f"Error: {e}"); return False

    def detach(self):
        for o in (self.script, self.session):
            try:
                o and (o.unload() if hasattr(o,'unload') else o.detach())
            except:
                pass

def gui():
    import tkinter as tk
    from tkinter import ttk
    mgr = ReplayManager()
    log_buf = []
    def log_append(m):
        log_buf.append(m); log_buf[:] = log_buf[-200:]
        t.delete("1.0", tk.END); t.insert("1.0", "\n".join(reversed(log_buf)))
    mgr._on_msg_orig = mgr._on_msg
    def on_msg_wrap(msg, data):
        mgr._on_msg_orig(msg, data)
        if msg.get("type") == "send":
            p = msg.get("payload",{})
            t2 = p.get("type","")
            if t2 in ("save_replay", "network_request", "ready", "limit_bypassed"):
                log_append(f"[{time.strftime('%H:%M:%S')}] {t2}: {p.get('data',{})}")
    mgr._on_msg = on_msg_wrap

    root = tk.Tk()
    root.title("MD-Replay-Editor-fix")
    root.geometry("650x450")
    top = ttk.Frame(root, padding=5)
    top.pack(fill=tk.X)
    sv = tk.StringVar(value="Start Master Duel, then Attach")
    ttk.Label(top, textvariable=sv).pack(side=tk.LEFT, expand=True, fill=tk.X)
    btn = ttk.Button(top, text="Attach", command=lambda: [btn.config(text="...", state="disabled"), root.update(),
        mgr.attach() and (sv.set("Running"), root.after(100, lambda: poll())) or (btn.config(text="Attach", state="normal"))])
    btn.pack(side=tk.RIGHT)
    def poll():
        sv.set(f"Saved: {mgr.saved} | Limit: {'OK' if mgr.limit_bypassed else 'wait'}")

    t = tk.Text(root, font=("Consolas",9), bg="#1e1e1e", fg="#d4d4d4")
    t.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
    root.protocol("WM_DELETE_WINDOW", lambda: [mgr.detach(), root.destroy()])
    root.mainloop()

if __name__ == "__main__":
    if "--headless" in sys.argv:
        m = ReplayManager()
        while not m.attach():
            time.sleep(5)
        try:
            while True:
                print(f"\rSaved: {m.saved} | Limit: {'OK' if m.limit_bypassed else '...'}", end="")
                time.sleep(3)
        except:
            m.detach()
    else:
        gui()
