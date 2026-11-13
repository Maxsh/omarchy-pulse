"""Per-device reader threads: evdev events -> count records + timeline actions."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

import evdev
from evdev import ecodes

from .counter import MinuteCounter
from .devices import MOUSE_BUTTON_CODES, TOUCH_TOOL_CODES, InputDeviceInfo
from .timeline import (
    CLICK_DOWN,
    CLICK_UP,
    KB,
    MOTION,
    MOUSE,
    PRESS,
    REPEAT,
    WHEEL,
    Action,
    Timeline,
)

log = logging.getLogger(__name__)

#: Assumed mouse resolution when the kernel reports none: 1000 DPI, i.e. the
#: counts-per-mm divisor. Only the timeline's jitter threshold depends on it,
#: and that tolerates a several-fold error, so uncalibrated mice stay sane.
DEFAULT_DPI = 1000.0

#: Fallback for absolute devices (touchpads) that report no resolution,
#: in device units per mm. Same order-of-magnitude tolerance as above.
DEFAULT_ABS_UNITS_PER_MM = 40.0

#: A touch shorter than this, with less travel than the tap threshold, is a tap.
TAP_MAX_S = 0.2
TAP_MAX_MM = 1.0


@dataclass
class Translation:
    """What one raw evdev event means: compat counts plus timeline actions.

    ``counts`` feed the stock-compatible per-minute counters; ``actions`` feed
    the device-ownership timeline, which only cares about device class, kind
    and time — never which key was pressed (privacy invariant, AGENTS.md #1).
    """

    counts: list[tuple[str, int]] = field(default_factory=list)
    actions: list[Action] = field(default_factory=list)


class EventTranslator:
    """Turns raw (type, code, value, ts) triples of one device into counts and actions.

    Counts physical presses only (value == 1; autorepeat is value == 2, releases
    are 0) and never key identity. Autorepeats are still forwarded as keep-alive
    actions so holding a key counts as keyboard time. Touchpad taps are detected
    here because tap-to-click happens inside libinput, below evdev.
    """

    def __init__(
        self,
        abs_units_per_mm: float | None = None,
        rel_units_per_mm: float | None = None,
        tap_max_s: float = TAP_MAX_S,
        tap_max_mm: float = TAP_MAX_MM,
    ) -> None:
        self._abs_per_mm = (
            abs_units_per_mm
            if abs_units_per_mm and abs_units_per_mm > 0
            else DEFAULT_ABS_UNITS_PER_MM
        )
        self._rel_per_mm = (
            rel_units_per_mm if rel_units_per_mm and rel_units_per_mm > 0 else DEFAULT_DPI / 25.4
        )
        self._tap_max_s = tap_max_s
        self._tap_max_mm = tap_max_mm
        self._touching = False
        self._last_abs: dict[int, int] = {}
        self._touch_start: float | None = None
        self._touch_travel_mm = 0.0

    def feed(self, etype: int, code: int, value: int, ts: float) -> Translation:
        result = Translation()
        if etype == ecodes.EV_KEY:
            self._feed_key(code, value, ts, result)
        elif etype == ecodes.EV_REL:
            self._feed_rel(code, value, ts, result)
        elif etype == ecodes.EV_ABS:
            self._feed_abs(code, value, ts, result)
        return result

    def _feed_key(self, code: int, value: int, ts: float, result: Translation) -> None:
        if code == ecodes.BTN_TOUCH:
            if value == 1:
                self._touching = True
                self._last_abs.clear()  # new contact: never diff against the previous one
                self._touch_start = ts
                self._touch_travel_mm = 0.0
            elif value == 0 and self._touching:
                self._touching = False
                self._finish_touch(ts, result)
            return
        if code in MOUSE_BUTTON_CODES:
            if value == 1:
                result.counts.append(("clicks", 1))
                result.actions.append(Action(MOUSE, CLICK_DOWN, 1.0, ts))
            elif value == 0:
                result.actions.append(Action(MOUSE, CLICK_UP, 1.0, ts))
            return
        if value == 2:  # autorepeat: not a new press, but the hand is still on the keys
            result.actions.append(Action(KB, REPEAT, 1.0, ts))
            return
        if value != 1:  # 0 = release
            return
        if code in TOUCH_TOOL_CODES:
            return
        result.counts.append(("presses", 1))
        result.actions.append(Action(KB, PRESS, 1.0, ts))

    def _finish_touch(self, ts: float, result: Translation) -> None:
        start = self._touch_start
        self._touch_start = None
        if start is None:
            return
        if ts - start <= self._tap_max_s and self._touch_travel_mm <= self._tap_max_mm:
            # Tap-to-click is synthesized by libinput; the kernel only shows contact.
            result.counts.append(("clicks", 1))
            result.actions.append(Action(MOUSE, CLICK_DOWN, 1.0, ts))
            result.actions.append(Action(MOUSE, CLICK_UP, 1.0, ts))

    def _feed_rel(self, code: int, value: int, ts: float, result: Translation) -> None:
        if value == 0:
            return
        if code == ecodes.REL_X:
            result.counts.append(("deltaX", abs(value)))
            result.actions.append(Action(MOUSE, MOTION, abs(value) / self._rel_per_mm, ts))
        elif code == ecodes.REL_Y:
            result.counts.append(("deltaY", abs(value)))
            result.actions.append(Action(MOUSE, MOTION, abs(value) / self._rel_per_mm, ts))
        elif code == ecodes.REL_WHEEL:
            result.counts.append(("scrollY", abs(value)))
            result.actions.append(Action(MOUSE, WHEEL, 1.0, ts))
        elif code == ecodes.REL_HWHEEL:
            result.counts.append(("scrollX", abs(value)))
            result.actions.append(Action(MOUSE, WHEEL, 1.0, ts))
        # e.g. REL_WHEEL_HI_RES fires alongside REL_WHEEL; counting both would
        # double the scroll.

    def _feed_abs(self, code: int, value: int, ts: float, result: Translation) -> None:
        """Touchpad absolute motion: deltas in mm while a finger is down."""
        if code not in (ecodes.ABS_X, ecodes.ABS_Y):
            return
        last = self._last_abs.get(code)
        self._last_abs[code] = value
        if last is None or not self._touching:
            return
        delta = abs(value - last)
        mm = delta / self._abs_per_mm
        if mm <= 0:
            return
        self._touch_travel_mm += mm
        result.counts.append(("deltaX" if code == ecodes.ABS_X else "deltaY", delta))
        result.actions.append(Action(MOUSE, MOTION, mm, ts))


class DeviceReader(threading.Thread):
    """Reads one input device until it disappears or errors, then reports its own death."""

    def __init__(
        self,
        info: InputDeviceInfo,
        counter: MinuteCounter,
        timeline: Timeline,
        on_death: Callable[[DeviceReader], None] | None = None,
    ) -> None:
        super().__init__(name=f"pulse-reader:{info.path}", daemon=True)
        self.info = info
        self._counter = counter
        self._timeline = timeline
        self._on_death = on_death

    def run(self) -> None:
        log.info("reading %s [%s] at %s", self.info.name, self.info.kind.value, self.info.path)
        try:
            device = evdev.InputDevice(self.info.path)
        except OSError as exc:
            log.error("cannot open %s: %s", self.info.path, exc)
            self._die()
            return
        translator = self._make_translator(device)
        try:
            for event in device.read_loop():
                ts = event.timestamp() or time.time()
                translation = translator.feed(event.type, event.code, event.value, ts)
                for kind, amount in translation.counts:
                    self._counter.record(kind, amount, ts)
                for action in translation.actions:
                    self._timeline.feed(action)
        except OSError:
            log.info(
                "device %s (%s) stopped: disconnected or removed", self.info.name, self.info.path
            )
        except Exception:
            log.exception("unexpected reader failure for %s", self.info.path)
        finally:
            device.close()
            self._die()

    @staticmethod
    def _make_translator(device: evdev.InputDevice) -> EventTranslator:
        """Touchpad resolution comes from the kernel; mice are assumed 1000 DPI."""
        resolution = 0.0
        try:
            for code, absinfo in device.capabilities(absinfo=True).get(ecodes.EV_ABS, []):
                if code == ecodes.ABS_X and absinfo.resolution > 0:
                    resolution = float(absinfo.resolution)
                    break
        except (KeyError, ValueError, OSError):
            resolution = 0.0
        return EventTranslator(abs_units_per_mm=resolution or None)

    def _die(self) -> None:
        if self._on_death is not None:
            self._on_death(self)
