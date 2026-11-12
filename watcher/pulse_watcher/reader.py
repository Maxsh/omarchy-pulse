"""Per-device reader threads: evdev events -> semantic count records."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

import evdev
from evdev import ecodes

from .counter import MinuteCounter
from .devices import MOUSE_BUTTON_CODES, TOUCH_TOOL_CODES, InputDeviceInfo

log = logging.getLogger(__name__)


class EventTranslator:
    """Turns raw (type, code, value) triples of one device into (kind, amount) count records.

    Counts physical presses only (value == 1; autorepeat is value == 2, releases are 0)
    and never key identity — see the privacy invariant in AGENTS.md.
    """

    def __init__(self) -> None:
        self._touching = False
        self._last_abs: dict[int, int] = {}

    def feed(self, etype: int, code: int, value: int) -> list[tuple[str, int]]:
        if etype == ecodes.EV_KEY:
            if code == ecodes.BTN_TOUCH:
                self._touching = value == 1
                return []
            if value != 1:  # 0 = release, 2 = autorepeat
                return []
            if code in MOUSE_BUTTON_CODES:
                return [("clicks", 1)]
            if code in TOUCH_TOOL_CODES:
                return []
            return [("presses", 1)]
        if etype == ecodes.EV_REL and value != 0:
            if code == ecodes.REL_X:
                return [("deltaX", abs(value))]
            if code == ecodes.REL_Y:
                return [("deltaY", abs(value))]
            if code == ecodes.REL_HWHEEL:
                return [("scrollX", abs(value))]
            if code == ecodes.REL_WHEEL:
                return [("scrollY", abs(value))]
            return []  # e.g. REL_WHEEL_HI_RES: avoid double counting scroll
        if etype == ecodes.EV_ABS:
            return self._feed_abs(code, value)
        return []

    def _feed_abs(self, code: int, value: int) -> list[tuple[str, int]]:
        """Touchpad absolute motion: deltas while a finger is down."""
        if code not in (ecodes.ABS_X, ecodes.ABS_Y):
            return []
        last = self._last_abs.get(code)
        self._last_abs[code] = value
        if last is None or not self._touching:
            return []
        return [("deltaX" if code == ecodes.ABS_X else "deltaY", abs(value - last))]


class DeviceReader(threading.Thread):
    """Reads one input device until it disappears or errors, then reports its own death."""

    def __init__(
        self,
        info: InputDeviceInfo,
        counter: MinuteCounter,
        on_death: Callable[[DeviceReader], None] | None = None,
    ) -> None:
        super().__init__(name=f"pulse-reader:{info.path}", daemon=True)
        self.info = info
        self._counter = counter
        self._translator = EventTranslator()
        self._on_death = on_death

    def run(self) -> None:
        log.info("reading %s [%s] at %s", self.info.name, self.info.kind.value, self.info.path)
        try:
            device = evdev.InputDevice(self.info.path)
        except OSError as exc:
            log.error("cannot open %s: %s", self.info.path, exc)
            self._die()
            return
        try:
            for event in device.read_loop():
                for kind, amount in self._translator.feed(event.type, event.code, event.value):
                    self._counter.record(kind, amount, event.timestamp() or time.time())
        except OSError:
            log.info("device %s (%s) stopped: disconnected or removed", self.info.name, self.info.path)
        except Exception:
            log.exception("unexpected reader failure for %s", self.info.path)
        finally:
            device.close()
            self._die()

    def _die(self) -> None:
        if self._on_death is not None:
            self._on_death(self)
