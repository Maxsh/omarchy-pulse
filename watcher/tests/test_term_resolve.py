"""Resolver chain against a fake /proc tree and stub herdr sockets (no real herdr/tmux)."""

import json
import pathlib
import shutil
import socket
import tempfile
import threading

import pytest

from pulse_watcher.term.herdr import focused_app
from pulse_watcher.term.procfs import Proc
from pulse_watcher.term.resolve import Resolution, Resolver, tmux_socket_args


class FakeProc:
    """Builds /proc-like directories: stat, task/<pid>/children and cmdline."""

    def __init__(self, root: pathlib.Path) -> None:
        self.root = root
        self._children: dict[int, list[int]] = {}

    def add(
        self,
        pid: int,
        comm: str,
        ppid: int = 0,
        argv: tuple[str, ...] = (),
        tty_nr: int = 0,
        tpgid: int = -1,
        env: dict[str, str] | None = None,
    ) -> None:
        directory = self.root / str(pid)
        (directory / "task" / str(pid)).mkdir(parents=True, exist_ok=True)
        stat = f"{pid} ({comm}) S {ppid} {pid} {pid} {tty_nr} {tpgid} 0 0 0"
        (directory / "stat").write_text(stat)
        (directory / "cmdline").write_bytes(b"\0".join(a.encode() for a in argv) + b"\0")
        if env is not None:
            (directory / "environ").write_bytes(
                b"\0".join(f"{k}={v}".encode() for k, v in env.items()) + b"\0"
            )
        self._children.setdefault(pid, [])
        if ppid:
            self._children.setdefault(ppid, []).append(pid)
        for parent, kids in self._children.items():
            children_dir = self.root / str(parent) / "task" / str(parent)
            children_dir.mkdir(parents=True, exist_ok=True)
            (children_dir / "children").write_text(" ".join(map(str, kids)))

    def proc(self) -> Proc:
        return Proc(self.root)


@pytest.fixture()
def fake(tmp_path):
    return FakeProc(tmp_path / "proc")


@pytest.fixture()
def herdr_base():
    # AF_UNIX paths are limited to ~108 bytes, so pytest's tmp_path can be too long.
    base = pathlib.Path(tempfile.mkdtemp(prefix="pulse-", dir="/tmp"))
    yield base
    shutil.rmtree(base, ignore_errors=True)


class StubHerdr:
    """A herdr-like newline-JSON server answering canned results per method."""

    def __init__(self, path: pathlib.Path, results: dict[str, dict]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.methods: list[str] = []
        self._results = results
        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._sock.bind(str(path))
        self._sock.listen(4)
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self) -> None:
        while True:
            try:
                conn, _ = self._sock.accept()
            except OSError:
                return
            with conn:
                request = json.loads(conn.makefile().readline())
                self.methods.append(request["method"])
                result = self._results.get(request["method"], {})
                reply = {"id": request["id"], "result": result}
                conn.sendall((json.dumps(reply) + "\n").encode())

    def close(self) -> None:
        self._sock.close()


def _pane(agent=None, pane_id="w1:p1"):
    pane = {
        "pane_id": pane_id,
        "cwd": "/home/user/secret-client-project",
        "terminal_title": "private title",
    }
    if agent:
        pane["agent"] = agent
    return {"type": "pane_current", "pane": pane}


def _process_info(*names):
    return {
        "type": "pane_process_info",
        "process_info": {
            "foreground_processes": [
                {"name": name, "cwd": "/secret", "cmdline": "x --token=abc"} for name in names
            ]
        },
    }


def _terminal_with_herdr(fake, argv=("herdr",)):
    fake.add(100, "foot")
    fake.add(101, "bash", ppid=100, tty_nr=34817, tpgid=102)
    fake.add(102, "herdr", ppid=101, argv=argv)


def test_herdr_agent_label_wins(fake, herdr_base):
    _terminal_with_herdr(fake, ("herdr", "session", "attach", "work"))
    stub = StubHerdr(
        herdr_base / "sessions" / "work" / "herdr.sock",
        {"pane.current": _pane(agent="opencode")},
    )
    try:
        resolver = Resolver(fake.proc(), herdr_base, lambda _socket_args: "")
        assert resolver.resolve(100) == Resolution("opencode", "herdr")
        assert stub.methods == ["pane.current"]  # no process lookup needed
    finally:
        stub.close()


def test_herdr_process_name_when_no_agent(fake, herdr_base):
    _terminal_with_herdr(fake)
    stub = StubHerdr(
        herdr_base / "herdr.sock",
        {"pane.current": _pane(), "pane.process_info": _process_info("nvim")},
    )
    try:
        resolver = Resolver(fake.proc(), herdr_base, lambda _socket_args: "")
        assert resolver.resolve(100) == Resolution("nvim", "herdr")
    finally:
        stub.close()


def test_each_herdr_client_uses_its_own_session_socket(fake, herdr_base):
    _terminal_with_herdr(fake, ("herdr", "session", "attach", "work"))
    default = StubHerdr(herdr_base / "herdr.sock", {"pane.current": _pane(agent="claude")})
    work = StubHerdr(
        herdr_base / "sessions" / "work" / "herdr.sock", {"pane.current": _pane(agent="opencode")}
    )
    try:
        resolver = Resolver(fake.proc(), herdr_base, lambda _socket_args: "")
        assert resolver.resolve(100).app == "opencode"
        assert default.methods == []
    finally:
        default.close()
        work.close()


def test_remote_herdr_reports_herdr_itself(fake, herdr_base):
    _terminal_with_herdr(fake, ("herdr", "--remote", "workbox"))
    resolver = Resolver(fake.proc(), herdr_base, lambda _socket_args: "")
    assert resolver.resolve(100) == Resolution("herdr", "herdr")


def test_unreachable_herdr_socket_falls_back_to_the_pty_foreground(fake, herdr_base):
    _terminal_with_herdr(fake)
    # bash's foreground group is the herdr client (pid 102): its comm is "herdr".
    resolver = Resolver(fake.proc(), herdr_base, lambda _socket_args: "")
    assert resolver.resolve(100) == Resolution("herdr", "pty")


def test_herdr_server_process_is_not_a_client(fake, herdr_base):
    fake.add(100, "foot")
    fake.add(101, "herdr", ppid=100, argv=("herdr", "server"))
    resolver = Resolver(fake.proc(), herdr_base, lambda _socket_args: "")
    assert resolver.resolve(100) is None


def test_tmux_client_uses_its_pane_command(fake, herdr_base):
    fake.add(100, "foot")
    fake.add(101, "tmux: client", ppid=100)
    listing = "999 zsh\n101 nvim\n"
    queries = []

    def runner(socket_args):
        queries.append(socket_args)
        return listing

    assert Resolver(fake.proc(), herdr_base, runner).resolve(100) == Resolution("nvim", "tmux")
    assert queries == [()]  # default socket


def test_tmux_client_not_in_listing_falls_through_to_the_pty(fake, herdr_base):
    fake.add(100, "foot")
    fake.add(101, "tmux: client", ppid=100)
    fake.add(102, "zsh", ppid=101, tty_nr=34817, tpgid=102)
    resolver = Resolver(fake.proc(), herdr_base, lambda _socket_args: "999 zsh\n")
    assert resolver.resolve(100) == Resolution("shell", "pty")


def test_tmux_client_on_a_custom_socket_is_queried_there(fake, herdr_base):
    fake.add(100, "foot")
    fake.add(101, "tmux: client", ppid=100, argv=("tmux", "-L", "work", "attach"))
    queries = []

    def runner(socket_args):
        queries.append(socket_args)
        return "999 zsh\n101 nvim\n" if socket_args == ("-L", "work") else ""

    resolver = Resolver(fake.proc(), herdr_base, runner)
    assert resolver.resolve(100) == Resolution("nvim", "tmux")
    assert queries == [("-L", "work")]  # the default socket is never queried


def test_each_custom_tmux_socket_is_queried_separately(fake, herdr_base):
    fake.add(100, "foot")
    fake.add(101, "tmux: client", ppid=100, argv=("tmux", "-S", "/tmp/s1", "attach"))
    fake.add(102, "tmux: client", ppid=100, argv=("tmux", "--socket-name=work"))
    queries = []

    def runner(socket_args):
        queries.append(socket_args)
        return {("-S", "/tmp/s1"): "999 zsh\n", ("--socket-name", "work"): "102 lazygit\n"}.get(
            socket_args, ""
        )

    # Both sockets are consulted in client order; the second one answers.
    assert Resolver(fake.proc(), herdr_base, runner).resolve(100) == Resolution("lazygit", "tmux")
    assert queries == [("-S", "/tmp/s1"), ("--socket-name", "work")]


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        (("tmux", "attach"), ()),
        (("tmux", "-L", "work", "attach"), ("-L", "work")),
        (("tmux", "-Lwork", "attach"), ("-L", "work")),
        (("tmux", "-S", "/tmp/s.sock"), ("-S", "/tmp/s.sock")),
        (("tmux", "-S/tmp/s.sock"), ("-S", "/tmp/s.sock")),
        (("tmux", "--socket-name", "work"), ("--socket-name", "work")),
        (("tmux", "--socket-name=work"), ("--socket-name", "work")),
        (("tmux", "-u", "attach"), ()),
        (("tmux", "-L"), ()),  # dangling flag without a value
    ],
)
def test_tmux_socket_args(argv, expected):
    assert tmux_socket_args(argv) == expected


def test_plain_pty_uses_the_foreground_process_group(fake, herdr_base):
    fake.add(100, "foot")
    fake.add(101, "zsh", ppid=100, tty_nr=34817, tpgid=150)
    fake.add(150, "lazygit", ppid=101, tty_nr=34817, tpgid=150)
    resolver = Resolver(fake.proc(), herdr_base, lambda _socket_args: "")
    assert resolver.resolve(100) == Resolution("lazygit", "pty")


def test_single_instance_terminal_is_not_resolved(fake, herdr_base):
    # Ghostty's desktop default (gtk-single-instance=detect -> true), footclient
    # and kitty --single-instance keep all windows in one process: the tree
    # cannot say which window runs what, so resolving would misattribute.
    fake.add(100, "foot")
    fake.add(101, "zsh", ppid=100, tty_nr=34817, tpgid=101)
    shared = Resolver(
        fake.proc(), herdr_base, lambda _socket_args: "", window_pids=lambda: [100, 100, 555]
    )
    assert shared.resolve(100) is None
    # A unique pid still resolves, and so does one without peer information.
    unique = Resolver(
        fake.proc(), herdr_base, lambda _socket_args: "", window_pids=lambda: [100, 555]
    )
    assert unique.resolve(100) == Resolution("shell", "pty")
    assert Resolver(fake.proc(), herdr_base, lambda _socket_args: "").resolve(100) == Resolution(
        "shell", "pty"
    )


def test_herdr_socket_override_from_the_client_environment(fake, herdr_base):
    fake.add(100, "foot")
    fake.add(
        101,
        "herdr",
        ppid=100,
        argv=("herdr", "--session", "moved"),
        env={"HERDR_SOCKET_PATH": str(herdr_base / "moved.sock"), "SECRET_TOKEN": "x"},
    )
    stub = StubHerdr(herdr_base / "moved.sock", {"pane.current": _pane(agent="claude")})
    try:
        # HERDR_SOCKET_PATH on the client process wins over the default layout.
        resolver = Resolver(fake.proc(), herdr_base, lambda _socket_args: "")
        assert resolver.resolve(100) == Resolution("claude", "herdr")
    finally:
        stub.close()


def test_herdr_config_path_redirects_the_socket_base(fake, herdr_base):
    fake.add(100, "foot")
    fake.add(
        101,
        "herdr",
        ppid=100,
        argv=("herdr",),
        env={"HERDR_CONFIG_PATH": str(herdr_base / "elsewhere" / "config.toml")},
    )
    stub = StubHerdr(
        herdr_base / "elsewhere" / "herdr.sock", {"pane.current": _pane(agent="opencode")}
    )
    try:
        resolver = Resolver(fake.proc(), herdr_base, lambda _socket_args: "")
        assert resolver.resolve(100) == Resolution("opencode", "herdr")
    finally:
        stub.close()


def test_herdr_client_environment_values_are_not_leaked(fake, herdr_base):
    # The env is read only to find the socket; the resolver result must not
    # carry any of it, and unrequested variables are dropped unread.
    fake.add(100, "foot")
    fake.add(
        101,
        "herdr",
        ppid=100,
        argv=("herdr",),
        env={"HERDR_CONFIG_PATH": "/tmp/x", "HERDR_TOKEN": "supersecret"},
    )
    fake.add(102, "bash", ppid=100, tty_nr=9, tpgid=102)
    resolver = Resolver(fake.proc(), herdr_base, lambda _socket_args: "")
    result = resolver.resolve(100)
    assert result is None or "supersecret" not in result.app
    assert fake.proc().environ(101, {"UNRELATED"}) == {}  # only requested keys are returned
    assert fake.proc().environ(99999, {"A"}) == {}  # unknown pid -> empty, no error


def test_idle_shell_is_reported_as_shell(fake, herdr_base):
    fake.add(100, "foot")
    fake.add(101, "bash", ppid=100, tty_nr=34817, tpgid=101)
    resolver = Resolver(fake.proc(), herdr_base, lambda _socket_args: "")
    assert resolver.resolve(100) == Resolution("shell", "pty")


def test_missing_terminal_process_resolves_nothing(fake, herdr_base):
    resolver = Resolver(fake.proc(), herdr_base, lambda _socket_args: "")
    assert resolver.resolve(424242) is None


def test_comm_with_spaces_and_parentheses_parses(fake):
    fake.add(7, "we ird) (name", ppid=1, tty_nr=5, tpgid=7)
    stat = fake.proc().stat(7)
    assert stat is not None
    assert (stat.comm, stat.ppid, stat.tty_nr, stat.tpgid) == ("we ird) (name", 1, 5, 7)


def test_descendants_are_bounded(fake):
    fake.add(1, "root")
    for pid in range(2, 40):
        fake.add(pid, "kid", ppid=1)
    assert len(fake.proc().descendants(1, max_nodes=10)) == 10


def test_herdr_answer_fields_beyond_names_are_never_returned(herdr_base):
    path = herdr_base / "herdr.sock"
    stub = StubHerdr(
        path, {"pane.current": _pane(), "pane.process_info": _process_info("opencode.exe")}
    )
    try:
        app = focused_app(path)
    finally:
        stub.close()
    assert app == "opencode"
    assert "secret" not in app
    assert "pane.read" not in stub.methods
