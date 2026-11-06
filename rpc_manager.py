"""
Threaded Discord IPC/RPC manager.

pypresence operations run on a worker thread so Discord connection attempts do
not freeze the Tkinter event loop. The manager retries when Discord is closed
and reconnects when Discord becomes available again.
"""
from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Callable, Optional

from pypresence import Presence
from pypresence.exceptions import DiscordNotFound, PipeClosed, InvalidID


class RPCManager:
    def __init__(self, status_callback: Optional[Callable[[str], None]] = None,
                 retry_seconds: float = 5.0):
        self.status_callback = status_callback or (lambda _status: None)
        self.retry_seconds = retry_seconds
        self._commands: queue.Queue = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._client_id: Optional[str] = None
        self._payload: dict = {}
        self._rpc: Optional[Presence] = None
        self._connected = False
        self._running = False
        self._lock = threading.Lock()

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._running

    def _status(self, value: str):
        try:
            self.status_callback(value)
        except Exception:
            logging.exception("Status callback failed")

    def start(self, client_id: str, payload: dict):
        self.stop()
        self._stop_event = threading.Event()
        self._client_id = str(client_id)
        self._payload = dict(payload)
        with self._lock:
            self._running = True
        self._thread = threading.Thread(target=self._worker, name="DiscordRPCWorker", daemon=True)
        self._thread.start()

    def update(self, payload: dict):
        """Queue a new presence payload without blocking the GUI."""
        self._commands.put(("update", dict(payload)))

    def stop(self):
        with self._lock:
            was_running = self._running
            self._running = False
        if not was_running and not self._thread:
            return
        self._stop_event.set()
        self._commands.put(("stop", None))
        if self._thread and self._thread.is_alive() and threading.current_thread() is not self._thread:
            self._thread.join(timeout=3.0)
        self._thread = None
        self._disconnect()
        self._status("Stopped")

    def _disconnect(self):
        rpc, self._rpc = self._rpc, None
        self._connected = False
        if rpc:
            try:
                rpc.close()
            except Exception:
                logging.debug("RPC close raised", exc_info=True)

    def _connect(self) -> bool:
        try:
            self._status("Connecting to Discord…")
            self._rpc = Presence(self._client_id)
            self._rpc.connect()
            self._connected = True
            self._status("Connected — broadcasting")
            return True
        except (DiscordNotFound, FileNotFoundError, ConnectionError, OSError) as exc:
            logging.info("Discord IPC unavailable: %s", exc)
            self._disconnect()
            self._status("Discord not detected — retrying")
            return False
        except InvalidID as exc:
            logging.error("Invalid Discord application ID: %s", exc)
            self._disconnect()
            self._status("Invalid Client ID")
            self._stop_event.set()
            return False
        except Exception as exc:
            logging.warning("RPC connection failed: %s", exc, exc_info=True)
            self._disconnect()
            self._status("Connection failed — retrying")
            return False

    def _send_presence(self):
        if not self._connected or not self._rpc:
            return
        try:
            self._rpc.update(**self._payload)
            self._status("Connected — broadcasting")
        except (PipeClosed, BrokenPipeError, ConnectionError, OSError) as exc:
            logging.info("Discord IPC closed: %s", exc)
            self._disconnect()
            self._status("Discord disconnected — reconnecting")
        except Exception as exc:
            logging.error("Presence update failed: %s", exc, exc_info=True)
            self._status(f"Presence update error: {type(exc).__name__}")

    def _worker(self):
        next_retry = 0.0
        try:
            while not self._stop_event.is_set():
                # Process pending GUI commands.
                try:
                    command, value = self._commands.get(timeout=0.25)
                    if command == "stop":
                        break
                    if command == "update":
                        self._payload = value
                        if self._connected:
                            self._send_presence()
                except queue.Empty:
                    pass

                if self._stop_event.is_set():
                    break
                if not self._connected and time.monotonic() >= next_retry:
                    if self._connect():
                        self._send_presence()
                    next_retry = time.monotonic() + self.retry_seconds
        finally:
            self._disconnect()
            with self._lock:
                self._running = False
            self._status("Stopped")
