"""Hyprland IPC parsing against a stub socket (no real Hyprland needed)."""

import json
import pathlib
import shutil
import socket
import tempfile
import threading

import pytest

from pulse_watcher.term.hypr import Hyprland


class StubHyprland:
    """Answers .socket.sock requests with canned JSON per request line."""

    def __init__(self, directory: pathlib.Path, responses: dict[str, object]) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        self.requests: list[str] = []
        self._responses = responses
        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._sock.bind(str(directory / ".socket.sock"))
        self._sock.listen(4)
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self) -> None:
        while True:
            try:
                conn, _ = self._sock.accept()
            except OSError:
                return
            with conn:
                request = conn.recv(1024).decode()
                self.requests.append(request)
                conn.sendall(json.dumps(self._responses.get(request, [])).encode())

    def close(self) -> None:
        self._sock.close()


@pytest.fixture()
def hypr_dir():
    base = pathlib.Path(tempfile.mkdtemp(prefix="pulse-hypr-", dir="/tmp"))
    yield base
    shutil.rmtree(base, ignore_errors=True)


def test_client_pids_keep_duplicates_and_drop_junk(hypr_dir):
    stub = StubHyprland(
        hypr_dir,
        {
            "j/clients": [
                {"pid": 100, "class": "foot", "title": "private"},
                {"pid": 100, "class": "foot", "title": "private too"},
                {"pid": 7, "class": "kitty"},
                {"pid": 0, "class": "xway"},
                {"pid": -1, "class": "special"},
                {"class": "no pid"},
                "not a dict",
            ]
        },
    )
    try:
        assert Hyprland(hypr_dir).client_pids() == [100, 100, 7]
        assert stub.requests == ["j/clients"]
    finally:
        stub.close()


def test_client_pids_on_error_is_empty(hypr_dir):
    # No stub listening: the socket connect fails and the list stays empty,
    # which the caller treats as "not shared" (fail-open).
    assert Hyprland(hypr_dir).client_pids() == []


def test_active_window_parses_class_and_pid(hypr_dir):
    stub = StubHyprland(hypr_dir, {"j/activewindow": {"class": "foot", "pid": 174696}})
    try:
        assert Hyprland(hypr_dir).active_window() == ("foot", 174696)
    finally:
        stub.close()


def test_active_window_rejects_shapeless_answers(hypr_dir):
    stub = StubHyprland(hypr_dir, {"j/activewindow": {"pid": 1}})
    try:
        assert Hyprland(hypr_dir).active_window() is None
    finally:
        stub.close()
