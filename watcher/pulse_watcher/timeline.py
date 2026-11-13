"""Time attribution: rebuild which input device the user's hands were on.

Raw per-minute counts say *what* happened but not *how long* it took — one key
press and one second of scrolling are both "1". This module reconstructs a
device-ownership timeline (keyboard vs mouse) from the ordered stream of input
actions and bins **seconds** per device class per minute, so keyboard time,
mouse time and idle time are measured in the same unit.

The model follows motor-behavior results from HCI research — the Keystroke-Level
Model (Card, Moran & Newell 1980; operator times per Kieras 2001,
https://web.eecs.umich.edu/~kieras/docs/GOMS/KLM.pdf) and typing-burst studies
(pauses of ~2 s between words end a burst):

- Input comes in bursts. A pause above ``gap_kb`` (typing) or ``gap_mouse``
  (pointing) ends a burst; the last ``tail`` seconds of a burst still count
  as that device's time.
- Switching devices costs a "homing" step H = 0.4 s (KLM operator H), credited
  to the device switched *to*; hand-overs within ``switch_max`` are direct.
- A key event within ``chord`` of a mouse click — or while a button is held
  (Shift+drag, Ctrl+click) — belongs to the mouse action, not keyboard time.
- Rapid alternation between devices (flips faster than H, e.g. gaming with
  WASD + mouse) means both devices are in use; those seconds are binned as
  ``bothS`` and split evenly for display.

Privacy: timing and counts only — which key was pressed is never seen here.
"""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass, field
from typing import NamedTuple, Protocol

#: Device classes an action can belong to.
KB = "kb"
MOUSE = "mouse"

#: Action kinds emitted by the translator. Every kind is activity; ``repeat``
#: is a keep-alive (autorepeat) that extends keyboard time without a new press.
PRESS = "press"
REPEAT = "repeat"
CLICK_DOWN = "button_down"
CLICK_UP = "button_up"
MOTION = "motion"
WHEEL = "wheel"

#: Per-minute sink fields, matching the additive event schema keys.
KB_FIELD = "kbS"
MOUSE_FIELD = "mouseS"
BOTH_FIELD = "bothS"
_FIELD = {KB: KB_FIELD, MOUSE: MOUSE_FIELD}

#: How long after a minute ends before its data is final: the longest pause
#: that can still merge two bursts (gap) plus the tail of the last burst.
RESOLVE_S = 3.0


class Action(NamedTuple):
    """One input action: which device, what happened, when (unix seconds)."""

    dev: str  # KB or MOUSE
    kind: str  # PRESS / REPEAT / CLICK_DOWN / CLICK_UP / MOTION / WHEEL
    amount: float  # mm of travel for MOTION, 1 for discrete actions
    ts: float  # unix seconds (kernel event timestamp)


class MinuteSink(Protocol):
    """Receives per-minute device-ownership seconds (implemented by MinuteCounter)."""

    def add_seconds(self, minute_ts: float, field: str, seconds: float) -> None: ...

    def reattribute_seconds(
        self, minute_ts: float, from_field: str, to_field: str, seconds: float
    ) -> None: ...


@dataclass(frozen=True)
class TimelineParams:
    """Motor-behavior constants; see the module docstring for their sources."""

    gap_kb: float = 2.0  # s of silence that ends a typing burst (word pause)
    gap_mouse: float = 1.0  # s of silence that ends a pointing burst (aim pause)
    tail: float = 1.0  # s after a burst's last event still counted
    homing: float = 0.4  # KLM H: moving the hand between keyboard and mouse
    switch_max: float = 1.5  # s between devices that still counts as a hand-over
    chord: float = 0.3  # s around a click where key events belong to the click
    motion_mm: float = 1.0  # travel within the window that counts as real motion
    motion_window_s: float = 0.25

    def gap(self, dev: str) -> float:
        return self.gap_kb if dev == KB else self.gap_mouse


@dataclass
class _ChordState:
    """Button-held intervals and click times of the batch being processed."""

    held: list[tuple[float, float]] = field(default_factory=list)
    clicks: list[float] = field(default_factory=list)


class Timeline:
    """Consumes input actions from all device threads and bins seconds per minute.

    Reader threads call :meth:`feed` (thread-safe enqueue). The main loop calls
    :meth:`drain` each minute to process the queued actions in timestamp order,
    and :meth:`close_stale` to end bursts that simply stopped.
    """

    def __init__(self, sink: MinuteSink, params: TimelineParams | None = None) -> None:
        self._sink = sink
        self._params = params or TimelineParams()
        self._queue: deque[Action] = deque()
        self._lock = threading.Lock()
        self._owner: str | None = None  # device owning the open segment
        self._binned_up_to = 0.0  # segment time already credited to the sink
        self._seg_rapid_open = False  # open segment started from a rapid switch
        self._seg_binned: dict[int, float] = {}  # per-minute seconds of the open segment
        self._prev_end: float | None = None  # end of the most recently closed segment
        self._last: dict[str, float | None] = {KB: None, MOUSE: None}
        self._last_switch: float | None = None
        self._button_down = False
        self._last_click: float | None = None
        self._motion_acc_mm = 0.0
        self._motion_window_end: float | None = None

    def feed(self, action: Action) -> None:
        """Queue one action (any reader thread)."""
        with self._lock:
            self._queue.append(action)

    def drain(self) -> None:
        """Process all queued actions in timestamp order (main loop only)."""
        with self._lock:
            batch = list(self._queue)
            self._queue.clear()
        if not batch:
            return
        batch.sort(key=lambda action: action.ts)
        chords = self._chord_marks(batch)
        for action, chorded in zip(batch, chords):
            self._process(action, chorded)

    def close_stale(self, now: float) -> None:
        """End the open burst if it has been silent longer than its gap allows."""
        if self._owner is None:
            return
        if self._owner == MOUSE and self._button_down:
            return  # a held button is continuous mouse activity
        last = self._last[self._owner]
        if last is not None and now - last > self._params.gap(self._owner):
            self._close(last + self._params.tail, both=False)

    # -- processing ---------------------------------------------------------

    def _process(self, action: Action, chorded: bool) -> None:
        if action.kind == CLICK_DOWN:
            self._button_down = True
            self._last_click = action.ts
        elif action.kind == CLICK_UP:
            self._button_down = False
            self._last_click = action.ts
        dev = action.dev
        if dev == KB and chorded:
            dev = MOUSE  # Shift+drag, Ctrl+click: the key belongs to the mouse action
        if (
            dev == MOUSE
            and action.kind == MOTION
            and not self._motion_crosses(action.amount, action.ts)
        ):
            return  # jitter below the travel threshold: not activity at all
        self._activity(dev, action.ts, hold_end=action.kind == CLICK_UP)

    def _activity(self, dev: str, ts: float, hold_end: bool = False) -> None:
        if self._owner == dev:
            held = dev == MOUSE and (self._button_down or hold_end)
            last = self._last[dev]
            if last is not None and ts - last > self._params.gap(dev) and not held:
                end = last + self._params.tail
                self._close(end, both=False)
                self._start(dev, ts, prev_end=end)
        elif self._owner is None:
            self._start(dev, ts, prev_end=self._prev_end)
        else:
            self._switch_to(dev, ts)
        self._extend(dev, ts)
        last = self._last[dev]
        if last is None or ts > last:
            self._last[dev] = ts

    def _switch_to(self, dev: str, ts: float) -> None:
        """Hand-over from the device currently owning the hands to ``dev``."""
        old = self._owner
        last_old = self._last[old] if old else None
        rapid = self._last_switch is not None and ts - self._last_switch < self._params.homing
        if last_old is not None and ts - last_old <= self._params.switch_max:
            # Direct hand-over: the new device starts homing before its first event.
            boundary = max(last_old, ts - self._params.homing)
            self._close(boundary, both=self._seg_rapid_open and rapid)
            self._open(dev, boundary, rapid)
        else:
            end = (last_old or ts) + self._params.tail
            self._close(end, both=False)  # a long gap breaks any rapid-alternation run
            self._start(dev, ts, prev_end=end)
        self._last_switch = ts

    def _start(self, dev: str, ts: float, prev_end: float | None, rapid: bool = False) -> None:
        start = ts
        if prev_end is not None and ts - prev_end <= self._params.switch_max:
            start = max(prev_end, ts - self._params.homing)
        self._open(dev, start, rapid)

    def _open(self, dev: str, start: float, rapid: bool) -> None:
        self._owner = dev
        self._binned_up_to = start
        self._seg_rapid_open = rapid
        self._seg_binned = {}

    def _close(self, end: float, *, both: bool) -> None:
        owner = self._owner
        if owner is None:
            return
        end = max(end, self._binned_up_to)
        target = BOTH_FIELD if both else _FIELD[owner]
        if end > self._binned_up_to:
            for minute, overlap in self._splits(self._binned_up_to, end):
                self._sink.add_seconds(minute, target, overlap)
        if both:
            # The segment's earlier seconds were binned as keyboard/mouse while it
            # was open; rapid alternation means they were really simultaneous use.
            for minute, seconds in self._seg_binned.items():
                self._sink.reattribute_seconds(minute, _FIELD[owner], BOTH_FIELD, seconds)
        self._prev_end = end
        self._owner = None
        self._seg_binned = {}

    def _extend(self, dev: str, ts: float) -> None:
        """Credit [binned_up_to, ts) to the open segment's device."""
        if ts <= self._binned_up_to:
            return
        for minute, overlap in self._splits(self._binned_up_to, ts):
            self._sink.add_seconds(minute, _FIELD[dev], overlap)
            self._seg_binned[minute] = self._seg_binned.get(minute, 0.0) + overlap
        self._binned_up_to = ts

    @staticmethod
    def _splits(start: float, end: float) -> list[tuple[int, float]]:
        """[start, end) split at minute boundaries into (minute_start, seconds)."""
        out: list[tuple[int, float]] = []
        minute = int(start // 60.0) * 60
        while minute < end:
            overlap = min(end, minute + 60.0) - max(start, float(minute))
            if overlap > 0.0:
                out.append((minute, overlap))
            minute += 60.0
        return out

    def _motion_crosses(self, mm: float, ts: float) -> bool:
        """Jitter filter: motion counts once travel reaches motion_mm within the window.

        Hand tremor while reading produces well under a millimetre per quarter
        second and never crosses; any real pointer movement does.
        """
        if self._motion_window_end is None or ts > self._motion_window_end:
            self._motion_acc_mm = 0.0
            self._motion_window_end = ts + self._params.motion_window_s
        self._motion_acc_mm += mm
        if self._motion_acc_mm >= self._params.motion_mm:
            self._motion_acc_mm = 0.0
            self._motion_window_end = ts + self._params.motion_window_s
            return True
        return False

    def _chord_marks(self, batch: list[Action]) -> list[bool]:
        """Mark key events that belong to a mouse action in this batch.

        A key event within ``chord`` of a click — before or after it — or while
        a button is held is part of the mouse work (modifiers for clicks and
        drags). Clicks from earlier batches are covered by ``_last_click``.
        """
        state = _ChordState(clicks=[a.ts for a in batch if a.kind in (CLICK_DOWN, CLICK_UP)])
        down_ts: float | None = None
        for action in batch:
            if action.kind == CLICK_DOWN and down_ts is None:
                down_ts = action.ts
            elif action.kind == CLICK_UP and down_ts is not None:
                state.held.append((down_ts, action.ts))
                down_ts = None
        if down_ts is not None:
            state.held.append((down_ts, float("inf")))
        if self._button_down:  # button was already held when this batch started
            first_up = min((a.ts for a in batch if a.kind == CLICK_UP), default=float("inf"))
            state.held.append((float("-inf"), first_up))
        chord = self._params.chord
        marks = []
        for action in batch:
            near_last_click = (
                self._last_click is not None and abs(action.ts - self._last_click) <= chord
            )
            chorded = (
                action.dev == KB
                and action.kind in (PRESS, REPEAT)
                and (
                    any(lo <= action.ts <= hi for lo, hi in state.held)
                    or near_last_click
                    or any(abs(action.ts - click) <= chord for click in state.clicks)
                )
            )
            marks.append(chorded)
        return marks
