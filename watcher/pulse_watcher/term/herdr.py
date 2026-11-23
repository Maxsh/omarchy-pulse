"""herdr socket client: the focused pane's agent or foreground process *name*.

herdr serves newline-delimited JSON on a per-session Unix socket. Only two
read-only methods are used (``pane.current``, ``pane.process_info``); pane
contents are never read, and cwd/cmdline/title fields in the answers are
discarded unread.
"""

from __future__ import annotations

import json
import logging
import pathlib
import re
import socket
from collections.abc import Sequence

from .names import normalize
from .procfs import Proc

log = logging.getLogger(__name__)

DEFAULT_BASE = pathlib.Path("~/.config/herdr").expanduser()

_MAX_RESPONSE_BYTES = 1_000_000
_SESSION_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def parse_client_argv(argv: Sequence[str]) -> tuple[str, str | None] | None:
    """Classify a ``herdr`` command line.

    Returns ``("local", session)`` for a client of a local session (session None =
    the default one), ``("remote", None)`` for ``--remote``, or None when the
    process is not a client (``herdr server`` and other subcommands).
    """
    args = list(argv[1:])
    if "--remote" in args or any(arg.startswith("--remote=") for arg in args):
        return ("remote", None)
    session: str | None = None
    for index, arg in enumerate(args):
        if arg == "--session" and index + 1 < len(args):
            session = args[index + 1]
        elif arg.startswith("--session="):
            session = arg.split("=", 1)[1]
    if args[:2] == ["session", "attach"] and len(args) > 2:
        session = args[2]
    elif args and not args[0].startswith("-"):
        return None  # some other subcommand (server, status, pane, ...)
    if session is not None and not _SESSION_NAME.match(session):
        return None
    return ("local", session)


def socket_path(session: str | None, base: pathlib.Path = DEFAULT_BASE) -> pathlib.Path:
    if session is None:
        return base / "herdr.sock"
    return base / "sessions" / session / "herdr.sock"


def socket_for(
    proc: Proc,
    pid: int,
    session: str | None,
    default_base: pathlib.Path = DEFAULT_BASE,
) -> pathlib.Path:
    """Socket path for the client at ``pid``, honoring its own environment.

    herdr resolves its socket from ``HERDR_SOCKET_PATH``, ``HERDR_CONFIG_PATH``
    and ``XDG_CONFIG_HOME``; a client launched with a moved config would
    otherwise be invisible. Only these three variables are read and none of
    their values are ever stored (privacy rule 1).
    """
    env = proc.environ(pid, {"HERDR_SOCKET_PATH", "HERDR_CONFIG_PATH", "XDG_CONFIG_HOME"})
    override = env.get("HERDR_SOCKET_PATH", "")
    if override:
        return pathlib.Path(override)
    base = default_base
    config = env.get("HERDR_CONFIG_PATH", "")
    if config:
        base = pathlib.Path(config).expanduser().parent
    elif default_base == DEFAULT_BASE:
        xdg = env.get("XDG_CONFIG_HOME", "")
        if xdg:
            base = pathlib.Path(xdg) / "herdr"
    return socket_path(session, base)


def _call(path: pathlib.Path, method: str, params: dict, timeout_s: float = 1.0) -> dict | None:
    request = json.dumps({"id": "pulse", "method": method, "params": params}) + "\n"
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout_s)
            sock.connect(str(path))
            sock.sendall(request.encode())
            buf = b""
            while not buf.endswith(b"\n") and len(buf) < _MAX_RESPONSE_BYTES:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                buf += chunk
        reply = json.loads(buf)
    except (OSError, ValueError) as exc:
        log.debug("herdr %s via %s failed: %s", method, path, exc)
        return None
    if not isinstance(reply, dict) or not isinstance(reply.get("result"), dict):
        return None
    return reply["result"]


def focused_app(path: pathlib.Path) -> str | None:
    """Name of what runs in the server's focused pane: agent label first, else process name."""
    current = _call(path, "pane.current", {})
    pane = current.get("pane") if current else None
    if not isinstance(pane, dict):
        return None
    agent = normalize(pane.get("agent"))
    if agent:
        return agent
    pane_id = pane.get("pane_id")
    if not isinstance(pane_id, str):
        return None
    info = _call(path, "pane.process_info", {"pane_id": pane_id})
    process_info = info.get("process_info") if info else None
    if not isinstance(process_info, dict):
        return None
    for proc in process_info.get("foreground_processes") or []:
        name = normalize(proc.get("name")) if isinstance(proc, dict) else None
        if name:
            return name
    return None
