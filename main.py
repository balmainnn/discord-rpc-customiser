"""
Discord RPC Customizer
A Tkinter desktop utility for editing and broadcasting Discord Rich Presence.

Closing the window hides it to the system tray. Use the tray menu's Exit command
(or the GUI's Exit button) to quit completely.
"""
from __future__ import annotations

import json
import logging
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image, ImageDraw
import pystray

from rpc_manager import RPCManager

APP_NAME = "Discord RPC Customizer"
BASE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
CONFIG_PATH = (Path(sys.executable).resolve().with_name("config.json")
               if getattr(sys, "frozen", False)
               else Path(__file__).resolve().with_name("config.json"))
LOG_PATH = Path.home() / ".discord_rpc_customizer.log"

logging.basicConfig(
    filename=LOG_PATH,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)


def default_config() -> dict:
    return {
        "client_id": "",
        "presence": {
            "state": "In a match",
            "details": "Playing solo",
            "large_image": "",
            "large_text": "",
            "small_image": "",
            "small_text": "",
            "use_start_timestamp": True,
            "buttons": []
        }
    }


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        return default_config()
    try:
        with CONFIG_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
        base = default_config()
        base["client_id"] = str(data.get("client_id", ""))
        base["presence"].update(data.get("presence", {}))
        buttons = base["presence"].get("buttons", [])
        base["presence"]["buttons"] = buttons[:2] if isinstance(buttons, list) else []
        return base
    except (OSError, json.JSONDecodeError, TypeError) as exc:
        logging.exception("Could not load configuration: %s", exc)
        return default_config()


class DiscordRPCApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(APP_NAME)
        self.root.geometry("640x760")
        self.root.minsize(560, 650)
        self.root.protocol("WM_DELETE_WINDOW", self.hide_to_tray)

        self.config = load_config()
        self.manager = RPCManager(self._on_rpc_status)
        self.ui_queue: queue.Queue = queue.Queue()
        self.tray_icon = None
        self.tray_thread = None
        self.quitting = False
        self.started_at = int(time.time())

        self._build_ui()
        self._load_fields()
        self._start_queue_poller()
        self._start_tray()

    def _build_ui(self):
        outer = ttk.Frame(self.root, padding=14)
        outer.pack(fill="both", expand=True)

        heading = ttk.Frame(outer)
        heading.pack(fill="x", pady=(0, 10))
        ttk.Label(heading, text="Discord RPC Customizer", font=("Segoe UI", 17, "bold")).pack(anchor="w")
        ttk.Label(
            heading,
            text="Configure your Rich Presence, then start broadcasting.",
            foreground="#666666"
        ).pack(anchor="w", pady=(3, 0))

        canvas = tk.Canvas(outer, highlightthickness=0)
        scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        self.form = ttk.Frame(canvas)
        self.form.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.form, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.vars = {}
        self._section("Discord application")
        self._entry("client_id", "Application Client ID")

        self._section("Presence text")
        self._entry("state", "State")
        self._entry("details", "Details")

        self._section("Large image")
        self._entry("large_image", "Large Image Key")
        self._entry("large_text", "Large Image Hover Text")

        self._section("Small image")
        self._entry("small_image", "Small Image Key")
        self._entry("small_text", "Small Image Hover Text")

        self._section("Timer")
        self.vars["use_start_timestamp"] = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            self.form, text="Show elapsed timer (count up)", variable=self.vars["use_start_timestamp"]
        ).pack(anchor="w", pady=(0, 8))

        self._section("Buttons (maximum 2)")
        self._entry("button1_label", "Button 1 label")
        self._entry("button1_url", "Button 1 URL")
        self._entry("button2_label", "Button 2 label")
        self._entry("button2_url", "Button 2 URL")

        controls = ttk.Frame(outer)
        controls.pack(fill="x", pady=(12, 6))
        self.broadcast_button = ttk.Button(controls, text="Start Broadcasting", command=self.toggle_broadcast)
        self.broadcast_button.pack(side="left")
        ttk.Button(controls, text="Apply to Live Presence", command=self.apply_live).pack(side="left", padx=8)
        ttk.Button(controls, text="Save Configuration", command=self.save_config).pack(side="left", padx=8)
        ttk.Button(controls, text="Exit", command=self.exit_app).pack(side="right")

        self.status_var = tk.StringVar(value="Status: Stopped")
        ttk.Label(outer, textvariable=self.status_var, foreground="#555555").pack(anchor="w", pady=(4, 0))

        self.form.bind_all("<MouseWheel>", self._on_mousewheel)

    def _section(self, title):
        ttk.Label(self.form, text=title, font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(12, 5))

    def _entry(self, key, label):
        ttk.Label(self.form, text=label).pack(anchor="w")
        var = tk.StringVar()
        self.vars[key] = var
        ttk.Entry(self.form, textvariable=var).pack(fill="x", pady=(2, 6))

    def _on_mousewheel(self, event):
        try:
            self.root.focus_get()
            # Scroll only when pointer is over the form.
            self.root.winfo_containing(event.x_root, event.y_root)
        except tk.TclError:
            pass

    def _load_fields(self):
        p = self.config["presence"]
        self.vars["client_id"].set(self.config.get("client_id", ""))
        for key in ("state", "details", "large_image", "large_text", "small_image", "small_text"):
            self.vars[key].set(p.get(key, ""))
        self.vars["use_start_timestamp"].set(bool(p.get("use_start_timestamp", True)))
        buttons = p.get("buttons", [])
        for i in range(2):
            button = buttons[i] if i < len(buttons) and isinstance(buttons[i], dict) else {}
            self.vars[f"button{i+1}_label"].set(button.get("label", ""))
            self.vars[f"button{i+1}_url"].set(button.get("url", ""))

    def _collect(self) -> dict:
        client_id = self.vars["client_id"].get().strip()
        if client_id and not client_id.isdigit():
            raise ValueError("Application Client ID must contain digits only.")
        presence = {
            "state": self.vars["state"].get().strip(),
            "details": self.vars["details"].get().strip(),
            "large_image": self.vars["large_image"].get().strip(),
            "large_text": self.vars["large_text"].get().strip(),
            "small_image": self.vars["small_image"].get().strip(),
            "small_text": self.vars["small_text"].get().strip(),
            "use_start_timestamp": bool(self.vars["use_start_timestamp"].get()),
            "buttons": []
        }
        for i in range(1, 3):
            label = self.vars[f"button{i}_label"].get().strip()
            url = self.vars[f"button{i}_url"].get().strip()
            if bool(label) != bool(url):
                raise ValueError(f"Button {i}: enter both a label and a URL, or leave both blank.")
            if label:
                parsed = urlparse(url)
                if parsed.scheme not in ("http", "https") or not parsed.netloc:
                    raise ValueError(f"Button {i}: URL must start with http:// or https://.")
                if len(label) > 32:
                    raise ValueError(f"Button {i}: Discord button labels must be 32 characters or fewer.")
                presence["buttons"].append({"label": label, "url": url})
        if len(presence["buttons"]) > 2:
            raise ValueError("Discord supports a maximum of two presence buttons.")
        return {"client_id": client_id, "presence": presence}

    def save_config(self, show_message=True):
        try:
            self.config = self._collect()
            with CONFIG_PATH.open("w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
            if show_message:
                messagebox.showinfo(APP_NAME, "Configuration saved.")
            return True
        except (ValueError, OSError) as exc:
            if show_message:
                messagebox.showerror(APP_NAME, str(exc))
            return False

    def toggle_broadcast(self):
        if self.manager.is_running:
            self.manager.stop()
            self.broadcast_button.configure(text="Start Broadcasting")
            self.status_var.set("Status: Stopping…")
            return
        if not self.save_config(show_message=False):
            return
        if not self.config["client_id"]:
            messagebox.showerror(APP_NAME, "Enter your Discord Application Client ID first.")
            return
        self.started_at = int(time.time())
        payload = self._build_payload()
        self.manager.start(self.config["client_id"], payload)
        self.broadcast_button.configure(text="Stop Broadcasting")
        self.status_var.set("Status: Connecting to Discord…")

    def _build_payload(self):
        p = self.config["presence"].copy()
        payload = {}
        for key in ("state", "details", "large_image", "large_text", "small_image", "small_text"):
            if p.get(key):
                payload[key] = p[key]
        if p.get("use_start_timestamp"):
            payload["start"] = self.started_at
        if p.get("buttons"):
            payload["buttons"] = p["buttons"][:2]
        return payload

    def _on_rpc_status(self, status):
        self.ui_queue.put(status)

    def _start_queue_poller(self):
        def poll():
            try:
                while True:
                    status = self.ui_queue.get_nowait()
                    self.status_var.set(f"Status: {status}")
                    if status in ("Stopped", "Disconnected"):
                        self.broadcast_button.configure(text="Start Broadcasting")
            except queue.Empty:
                pass
            if not self.quitting:
                self.root.after(200, poll)
        self.root.after(200, poll)

    def _make_tray_image(self):
        image = Image.new("RGBA", (64, 64), (35, 39, 42, 255))
        draw = ImageDraw.Draw(image)
        draw.ellipse((8, 8, 56, 56), fill=(88, 101, 242, 255))
        draw.text((19, 20), "RPC", fill="white")
        return image

    def _start_tray(self):
        menu = pystray.Menu(
            pystray.MenuItem("Open", lambda _icon, _item: self.root.after(0, self.show_window), default=True),
            pystray.MenuItem("Start / Stop", lambda _icon, _item: self.root.after(0, self.toggle_broadcast)),
            pystray.MenuItem("Exit", lambda _icon, _item: self.root.after(0, self.exit_app))
        )
        self.tray_icon = pystray.Icon(APP_NAME, self._make_tray_image(), APP_NAME, menu)
        self.tray_thread = threading.Thread(target=self.tray_icon.run, daemon=True)
        self.tray_thread.start()

    def hide_to_tray(self):
        if self.tray_icon:
            self.root.withdraw()
            self.status_var.set("Status: Running in system tray")
        else:
            self.root.iconify()

    def show_window(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def exit_app(self):
        if self.quitting:
            return
        self.quitting = True
        self.manager.stop()
        if self.tray_icon:
            try:
                self.tray_icon.stop()
            except Exception:
                logging.exception("Could not stop tray icon")
        self.root.after(250, self.root.destroy)


def main():
    root = tk.Tk()
    try:
        app = DiscordRPCApp(root)
        root.mainloop()
    except Exception:
        logging.exception("Fatal application error")
        messagebox.showerror(APP_NAME, f"The application encountered an error.\nSee log: {LOG_PATH}")


if __name__ == "__main__":
    main()
