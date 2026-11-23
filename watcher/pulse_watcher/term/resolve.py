"""Resolver chain: terminal window pid -> the program with focus inside it.

Order: herdr client (its socket knows the focused pane and agent) -> tmux client
(``pane_current_command``) -> plain pty (foreground process group of the tty).
A resolver that cannot answer falls through to the next one, so an unreachable
herdr socket still degrades to the pty foreground name.
"""

from __future__ import annotations

import dataclasses
import logging
import pathlib
import subprocess
from collections.abc import Callable

from . import herdr
from .names import normalize
from .procfs import Proc

log = logging.getLogger(__name__)

TmuxRunner = Callable[[], str]


@dataclasses.dataclass(frozen=True, slots=True)
class Resolution:
    app: str
    via: str  # "herdr" | "tmux" | "pty"


def run_tmux_list_clients() -> str:
    """``client_pid`` + the client's current pane command, one client per line."""
    try:
        done = subprocess.run(
            ["tmux", "list-clients", "-F", "#{client_pid} #{pane_current_command}"],
            capture_output=True,
            text=True,
            timeout=1.0,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout if done.returncode == 0 else ""


class Resolver:
    def __init__(
        self,
        proc: Proc | None = None,
        herdr_base: pathlib.Path = herdr.DEFAULT_BASE,
        tmux_runner: TmuxRunner = run_tmux_list_clients,
    ) -> None:
        self.proc = proc or Proc()
        self.herdr_base = herdr_base
        self.tmux_runner = tmux_runner

    def resolve(self, terminal_pid: int) -> Resolution | None:
        pids = self.proc.descendants(terminal_pid)
        return self._via_herdr(pids) or self._via_tmux(pids) or self._via_pty(pids)

    def _via_herdr(self, pids: list[int]) -> Resolution | None:
        for pid in pids:
            stat = self.proc.stat(pid)
            if stat is None or stat.comm != "herdr":
                continue
            kind = herdr.parse_client_argv(self.proc.argv(pid))
            if kind is None:
                continue
            mode, session = kind
            if mode == "remote":
                # The panes run on another machine; only the client is local.
                return Resolution("herdr", "herdr")
            app = herdr.focused_app(herdr.socket_path(session, self.herdr_base))
            return Resolution(app, "herdr") if app else None
        return None

    def _via_tmux(self, pids: list[int]) -> Resolution | None:
        clients = {
            pid for pid in pids if (stat := self.proc.stat(pid)) and stat.comm.startswith("tmux")
        }
        if not clients:
            return None
        for line in self.tmux_runner().splitlines():
            pid_text, _, command = line.partition(" ")
            if pid_text.isdigit() and int(pid_text) in clients:
                app = normalize(command)
                return Resolution(app, "tmux") if app else None
        return None

    def _via_pty(self, pids: list[int]) -> Resolution | None:
        for pid in pids:
            stat = self.proc.stat(pid)
            if stat is None or stat.tty_nr == 0 or stat.tpgid <= 0:
                continue
            leader = self.proc.stat(stat.tpgid)
            app = normalize(leader.comm if leader else stat.comm)
            return Resolution(app, "pty") if app else None
        return None
