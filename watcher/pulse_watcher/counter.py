"""Thread-safe per-minute aggregation of input counts."""

from __future__ import annotations

import threading
from typing import Literal

#: Event data keys, matching the stock aw-watcher-input schema (bucket type os.hid.input).
DATA_KEYS: tuple[str, ...] = ("presses", "clicks", "deltaX", "deltaY", "scrollX", "scrollY")

RecordKind = Literal["presses", "clicks", "deltaX", "deltaY", "scrollX", "scrollY"]


def floor_minute(timestamp: float) -> int:
    """Floor a unix timestamp to the start of its minute."""
    return int(timestamp // 60.0) * 60


class MinuteCounter:
    """Accumulates count records into per-minute bins keyed by minute start (unix ts).

    Minutes without any input are never created — absence of an event means no
    activity, which keeps the ActivityWatch database small.
    """

    def __init__(self) -> None:
        self._bins: dict[int, dict[str, int]] = {}
        self._lock = threading.Lock()

    def record(self, kind: str, amount: int, timestamp: float) -> None:
        if amount <= 0:
            return
        minute = floor_minute(timestamp)
        with self._lock:
            data = self._bins.get(minute)
            if data is None:
                data = dict.fromkeys(DATA_KEYS, 0)
                self._bins[minute] = data
            data[kind] += amount

    def take_completed(self, now: float) -> list[tuple[int, dict[str, int]]]:
        """Pop all bins whose minute has fully passed (minute start < floor_minute(now))."""
        cutoff = floor_minute(now)
        with self._lock:
            minutes = sorted(minute for minute in self._bins if minute < cutoff)
            return [(minute, self._bins.pop(minute)) for minute in minutes]
