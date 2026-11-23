"""Minimal /proc reader: process names and ids only.

The root is injectable so tests can build fake process trees in a temp dir.
"""

from __future__ import annotations

import dataclasses
import pathlib
from collections import deque

_MAX_ARGV_BYTES = 4096


@dataclasses.dataclass(frozen=True, slots=True)
class ProcStat:
    pid: int
    comm: str
    ppid: int
    pgrp: int
    tty_nr: int
    tpgid: int


class Proc:
    def __init__(self, root: str | pathlib.Path = "/proc") -> None:
        self.root = pathlib.Path(root)

    def stat(self, pid: int) -> ProcStat | None:
        try:
            raw = (self.root / str(pid) / "stat").read_text(errors="replace")
        except OSError:
            return None
        # comm is parenthesised and may itself contain spaces or parentheses.
        start, end = raw.find("("), raw.rfind(")")
        if start < 0 or end < start:
            return None
        fields = raw[end + 2 :].split()
        # fields: state ppid pgrp session tty_nr tpgid ...
        try:
            return ProcStat(
                pid=pid,
                comm=raw[start + 1 : end],
                ppid=int(fields[1]),
                pgrp=int(fields[2]),
                tty_nr=int(fields[4]),
                tpgid=int(fields[5]),
            )
        except (IndexError, ValueError):
            return None

    def children(self, pid: int) -> list[int]:
        try:
            raw = (self.root / str(pid) / "task" / str(pid) / "children").read_text()
        except OSError:
            return []
        return [int(token) for token in raw.split() if token.isdigit()]

    def argv(self, pid: int) -> list[str]:
        """Command line words (capped). Callers extract only what they need."""
        try:
            with (self.root / str(pid) / "cmdline").open("rb") as fh:
                raw = fh.read(_MAX_ARGV_BYTES)
        except OSError:
            return []
        return [part.decode("utf-8", "replace") for part in raw.split(b"\0") if part]

    def descendants(self, pid: int, max_nodes: int = 256) -> list[int]:
        """Breadth-first descendants of ``pid`` (excluding it), bounded."""
        found: list[int] = []
        queue: deque[int] = deque([pid])
        while queue and len(found) < max_nodes:
            for child in self.children(queue.popleft()):
                if len(found) >= max_nodes:
                    break
                found.append(child)
                queue.append(child)
        return found
