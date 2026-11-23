"""Hyprland IPC: the focused window's class and pid, plus focus-change wake-ups.

Only the class and pid are read; window titles in the answers are ignored.
"""

from __future__ import annotations

import json
import logging
import os
import pathlib
import socket
import threading

log = logging.getLogger(__name__)

_MAX_REPLY_BYTES = 65536

#: Hyprland events after which the focused window may have changed.
_WAKE_EVENTS = ("activewindowv2>>", "closewindow>>", "workspacev2>>", "fullscreen>>")


def socket_dir() -> pathlib.Path | None:
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    signature = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")
    if not runtime or not signature:
        return None
    return pathlib.Path(runtime) / "hypr" / signature


class Hyprland:
    def __init__(self, directory: pathlib.Path) -> None:
        self.directory = directory

    def active_window(self) -> tuple[str, int] | None:
        """(window class, pid) of the focused window, or None when nothing has focus."""
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                sock.settimeout(1.0)
                sock.connect(str(self.directory / ".socket.sock"))
                sock.sendall(b"j/activewindow")
                buf = b""
                while len(buf) < _MAX_REPLY_BYTES:
                    chunk = sock.recv(65536)
                    if not chunk:
                        break
                    buf += chunk
            data = json.loads(buf)
        except (OSError, ValueError) as exc:
            log.debug("hyprland activewindow failed: %s", exc)
            return None
        if not isinstance(data, dict):
            return None
        window_class, pid = data.get("class"), data.get("pid")
        if not isinstance(window_class, str) or not window_class or not isinstance(pid, int):
            return None
        return window_class, pid

    def listen(self, wake: threading.Event, stop: threading.Event) -> None:
        """Set ``wake`` on focus-relevant events until ``stop``; reconnects on errors."""
        while not stop.is_set():
            try:
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                    sock.settimeout(1.0)
                    sock.connect(str(self.directory / ".socket2.sock"))
                    buf = b""
                    while not stop.is_set():
                        try:
                            chunk = sock.recv(4096)
                        except TimeoutError:
                            continue
                        if not chunk:
                            break
                        buf = (buf + chunk)[-8192:]
                        *lines, buf = buf.split(b"\n")
                        if any(
                            line.decode("utf-8", "replace").startswith(_WAKE_EVENTS)
                            for line in lines
                        ):
                            wake.set()
            except OSError as exc:
                log.debug("hyprland event socket: %s", exc)
            stop.wait(2.0)
