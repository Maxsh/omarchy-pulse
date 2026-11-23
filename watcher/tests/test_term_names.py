"""Name normalization, herdr argv parsing and the heartbeat schema (privacy rule 1)."""

import pathlib

import pytest

from pulse_watcher.term.events import DATA_KEYS, build_heartbeat
from pulse_watcher.term.herdr import DEFAULT_BASE, parse_client_argv, socket_for, socket_path
from pulse_watcher.term.names import normalize


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("opencode", "opencode"),
        ("opencode.exe", "opencode"),
        ("/usr/bin/nvim", "nvim"),
        ("vim", "nvim"),
        ("-bash", "shell"),
        ("zsh", "shell"),
        ("LazyGit", "lazygit"),
        ("python3.14", "python3.14"),
    ],
)
def test_normalize_accepts_plain_command_names(raw, expected):
    assert normalize(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [None, 42, "", "   ", "has space", "semi;colon", "x" * 33, "../", "/", "é"],
)
def test_normalize_rejects_anything_that_is_not_a_command_name(raw):
    assert normalize(raw) is None


def test_parse_client_argv_variants():
    assert parse_client_argv(["herdr"]) == ("local", None)
    assert parse_client_argv(["herdr", "session", "attach", "work"]) == ("local", "work")
    assert parse_client_argv(["herdr", "--session", "second"]) == ("local", "second")
    assert parse_client_argv(["herdr", "--session=second"]) == ("local", "second")
    assert parse_client_argv(["herdr", "--remote", "workbox"]) == ("remote", None)
    assert parse_client_argv(["herdr", "server"]) is None
    assert parse_client_argv(["herdr", "pane", "list"]) is None


def test_parse_client_argv_rejects_path_like_session_names():
    assert parse_client_argv(["herdr", "--session", "../evil"]) is None
    assert parse_client_argv(["herdr", "session", "attach", "a/b"]) is None


def test_socket_path_per_session(tmp_path):
    assert socket_path(None, tmp_path) == tmp_path / "herdr.sock"
    assert socket_path("work", tmp_path) == tmp_path / "sessions" / "work" / "herdr.sock"


def test_socket_for_prefers_the_client_socket_override(tmp_path):
    class _P:
        def environ(self, pid, wanted):
            return {"HERDR_SOCKET_PATH": "/custom/herdr.sock"} if pid == 7 else {}

    assert socket_for(_P(), 7, "work", tmp_path) == pathlib.Path("/custom/herdr.sock")


def test_socket_for_xdg_config_home(tmp_path):
    class _P:
        def environ(self, pid, wanted):
            return {"XDG_CONFIG_HOME": "/xdg"} if pid == 7 else {}

    assert socket_for(_P(), 7, None, DEFAULT_BASE) == pathlib.Path("/xdg/herdr/herdr.sock")
    # An explicit base (tests, deployments) is kept when only XDG differs.
    assert socket_for(_P(), 7, None, tmp_path) == tmp_path / "herdr.sock"


def test_heartbeat_data_has_only_name_fields():
    event = build_heartbeat(1_700_000_000, "opencode", "foot", "herdr")
    assert set(event) == {"timestamp", "duration", "data"}
    assert set(event["data"]) == DATA_KEYS == {"app", "terminal", "via"}
    assert all(isinstance(value, str) for value in event["data"].values())
    assert event["duration"] == 0
    assert event["timestamp"].endswith("+00:00")
