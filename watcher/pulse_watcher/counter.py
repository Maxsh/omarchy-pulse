"""Thread-safe per-minute aggregation of input counts and device seconds."""

from __future__ import annotations

import threading
from typing import Literal

#: Event data keys, matching the stock aw-watcher-input schema (bucket type os.hid.input).
DATA_KEYS: tuple[str, ...] = ("presses", "clicks", "deltaX", "deltaY", "scrollX", "scrollY")

#: Additive seconds keys written by the device-ownership timeline
#: (timeline.py). Never renamed or removed — see AGENTS.md for the schema rule.
SECOND_KEYS: tuple[str, ...] = ("kbS", "mouseS", "bothS")

RecordKind = Literal["presses", "clicks", "deltaX", "deltaY", "scrollX", "scrollY"]


def floor_minute(timestamp: float) -> int:
    """Floor a unix timestamp to the start of its minute."""
    return int(timestamp // 60.0) * 60


class MinuteCounter:
    """Accumulates count records and device seconds into per-minute bins.

    Minutes without any input are never created — absence of an event means no
    activity, which keeps the ActivityWatch database small.

    ``resolve_s`` delays completion: a minute is only flushed once that much
    time has passed after its end, so the timeline can still credit bursts
    that overlap the minute boundary (gap + tail of the last burst).
    """

    def __init__(self, resolve_s: float = 0.0) -> None:
        self._bins: dict[int, dict[str, int | float]] = {}
        self._lock = threading.Lock()
        self._resolve_s = resolve_s

    def _new_bin(self) -> dict[str, int | float]:
        return {**dict.fromkeys(DATA_KEYS, 0), **dict.fromkeys(SECOND_KEYS, 0.0)}

    def record(self, kind: str, amount: int, timestamp: float) -> None:
        if amount <= 0:
            return
        minute = floor_minute(timestamp)
        with self._lock:
            data = self._bins.get(minute)
            if data is None:
                data = self._bins[minute] = self._new_bin()
            data[kind] += amount

    def add_seconds(self, minute_ts: float, field: str, seconds: float) -> None:
        """Add device-ownership seconds to a minute, capped at one minute's worth."""
        if seconds <= 0:
            return
        minute = floor_minute(minute_ts)
        with self._lock:
            data = self._bins.get(minute)
            if data is None:
                data = self._bins[minute] = self._new_bin()
            used = sum(float(data[key]) for key in SECOND_KEYS)
            data[field] = float(data[field]) + min(seconds, max(0.0, 60.0 - used))

    def reattribute_seconds(
        self, minute_ts: float, from_field: str, to_field: str, seconds: float
    ) -> None:
        """Move already-binned seconds between device fields (keyboard/mouse -> both).

        Rapid device alternation is first credited to the device that produced
        each event; once the alternation is recognized the segment's seconds
        move to ``bothS``. No-op for minutes that are already flushed.
        """
        if seconds <= 0:
            return
        minute = floor_minute(minute_ts)
        with self._lock:
            data = self._bins.get(minute)
            if data is None:
                return
            move = min(seconds, float(data[from_field]))
            data[from_field] = float(data[from_field]) - move
            data[to_field] = float(data[to_field]) + move

    def take_completed(self, now: float) -> list[tuple[int, dict[str, int | float]]]:
        """Pop all bins whose minute has fully passed and resolved."""
        with self._lock:
            minutes = sorted(m for m in self._bins if m + 60.0 + self._resolve_s <= now)
            return [(minute, self._bins.pop(minute)) for minute in minutes]
