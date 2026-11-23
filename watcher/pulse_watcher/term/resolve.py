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
from collections.abc import Callable, Sequence

from . import herdr
from .names import normalize
from .procfs import Proc

log = logging.getLogger(__name__)

TmuxRunner = Callable[[tuple[str, ...]], str]


@dataclasses.dataclass(frozen=True, slots=True)
class Resolution:
    app: str
    via: str  # "herdr" | "tmux" | "pty"


def run_tmux_list_clients(extra: Sequence[str] = ()) -> str:
    """``client_pid`` + the client's current pane command, one client per line."""
    try:
        done = subprocess.run(
            ["tmux", *extra, "list-clients", "-F", "#{client_pid} #{pane_current_command}"],
            capture_output=True,
            text=True,
            timeout=1.0,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout if done.returncode == 0 else ""


def tmux_socket_args(argv: Sequence[str]) -> tuple[str, ...]:
    """The tmux CLI arguments that select a client's server socket, if any.

    Clients on the default socket return ``()``; ``-L name``/``-S path`` (long
    forms ``--socket-name``/``--socket-path``, attached forms ``-Lname`` too)
    are passed through so ``tmux ... list-clients`` reaches the same server.
    """
    for index, arg in enumerate(argv[1:]):
        if arg in ("-L", "-S", "--socket-name", "--socket-path"):
            if index + 2 < len(argv):  # +2: the value follows in argv itself
                return (arg, argv[index + 2])
            return ()
        for long_name in ("--socket-name=", "--socket-path="):
            if arg.startswith(long_name):
                return (long_name[:-1], arg[len(long_name) :])
        for flag in ("-L", "-S"):
            if arg.startswith(flag) and len(arg) > 2:
                return (flag, arg[2:])
    return ()


class Resolver:
    def __init__(
        self,
        proc: Proc | None = None,
        herdr_base: pathlib.Path = herdr.DEFAULT_BASE,
        tmux_runner: TmuxRunner = run_tmux_list_clients,
        window_pids: Callable[[], list[int]] | None = None,
    ) -> None:
        self.proc = proc or Proc()
        self.herdr_base = herdr_base
        self.tmux_runner = tmux_runner
        # Pids of every open window; several windows on one pid mean a
        # single-instance terminal (Ghostty's desktop default, footclient,
        # kitty --single-instance), where the process tree cannot say which
        # window runs what — resolving then would credit one window with
        # another's app, so it is skipped instead.
        self.window_pids = window_pids

    def resolve(self, terminal_pid: int) -> Resolution | None:
        if self.window_pids is not None and self.window_pids().count(terminal_pid) > 1:
            log.debug("pid %d owns several windows; not resolving", terminal_pid)
            return None
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
            socket = herdr.socket_for(self.proc, pid, session, self.herdr_base)
            app = herdr.focused_app(socket)
            return Resolution(app, "herdr") if app else None
        return None

    def _via_tmux(self, pids: list[int]) -> Resolution | None:
        clients = {
            pid: tmux_socket_args(self.proc.argv(pid))
            for pid in pids
            if (stat := self.proc.stat(pid)) and stat.comm.startswith("tmux")
        }
        if not clients:
            return None
        # Clients may talk to different servers (custom -L/-S sockets): query
        # each distinct socket once and match its client pids.
        by_socket: dict[tuple[str, ...], set[int]] = {}
        for pid, socket_args in clients.items():
            by_socket.setdefault(socket_args, set()).add(pid)
        for socket_args, pids_on_socket in by_socket.items():
            for line in self.tmux_runner(socket_args).splitlines():
                pid_text, _, command = line.partition(" ")
                if pid_text.isdigit() and int(pid_text) in pids_on_socket:
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
