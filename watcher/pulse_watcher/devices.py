"""Input device discovery and classification (knowledge of Linux input codes lives here)."""

from __future__ import annotations

import dataclasses
import enum
import getpass
import glob
import logging
from collections.abc import Iterable, Sequence

import evdev
from evdev import ecodes

log = logging.getLogger(__name__)

_HINT_LOGGED = False


class DeviceKind(enum.Enum):
    KEYBOARD = "keyboard"
    POINTER = "pointer"
    OTHER = "other"


#: Presence of any of these marks a real keyboard.
LETTER_CODES: frozenset[int] = frozenset(
    [
        *range(ecodes.KEY_A, ecodes.KEY_Z + 1),
        *range(ecodes.KEY_1, ecodes.KEY_0 + 1),
        ecodes.KEY_SPACE,
        ecodes.KEY_ENTER,
        ecodes.KEY_TAB,
        ecodes.KEY_BACKSPACE,
        ecodes.KEY_ESC,
        ecodes.KEY_COMMA,
        ecodes.KEY_DOT,
        ecodes.KEY_SLASH,
    ]
)

#: Devices whose only keys are these never carry user activity.
POWER_CODES: frozenset[int] = frozenset(
    {
        ecodes.KEY_POWER,
        ecodes.KEY_POWER2,
        ecodes.KEY_SLEEP,
        ecodes.KEY_SUSPEND,
        ecodes.KEY_WAKEUP,
    }
)

#: Presence of any of these marks a gamepad/joystick (ignored — no user typing activity).
GAMEPAD_MARKERS: frozenset[int] = frozenset(
    {
        ecodes.BTN_SOUTH,
        ecodes.BTN_EAST,
        ecodes.BTN_NORTH,
        ecodes.BTN_WEST,
        ecodes.BTN_TRIGGER,
        ecodes.BTN_JOYSTICK,
    }
)

#: Buttons counted as mouse clicks.
MOUSE_BUTTON_CODES: frozenset[int] = frozenset(
    {
        ecodes.BTN_LEFT,
        ecodes.BTN_RIGHT,
        ecodes.BTN_MIDDLE,
        ecodes.BTN_SIDE,
        ecodes.BTN_EXTRA,
        ecodes.BTN_FORWARD,
        ecodes.BTN_BACK,
        ecodes.BTN_TASK,
    }
)

#: Buttons belonging to touch/pen state — never counted.
TOUCH_TOOL_CODES: frozenset[int] = frozenset(
    {
        ecodes.BTN_TOUCH,
        ecodes.BTN_TOOL_FINGER,
        ecodes.BTN_TOOL_RUBBER,
        ecodes.BTN_TOOL_PEN,
        ecodes.BTN_TOOL_MOUSE,
        ecodes.BTN_TOOL_LENS,
        ecodes.BTN_TOOL_DOUBLETAP,
        ecodes.BTN_TOOL_TRIPLETAP,
        ecodes.BTN_TOOL_QUADTAP,
        ecodes.BTN_TOOL_QUINTTAP,
        ecodes.BTN_STYLUS,
        ecodes.BTN_STYLUS2,
    }
)


def _codes(values: Iterable) -> set[int]:
    """Normalize a capability list to plain codes (EV_ABS entries may be (code, AbsInfo) tuples)."""
    return {item if isinstance(item, int) else item[0] for item in values}


def classify(caps: dict[int, list]) -> DeviceKind:
    """Classify a device from its evdev capabilities dict."""
    keys = _codes(caps.get(ecodes.EV_KEY, []))
    rels = _codes(caps.get(ecodes.EV_REL, []))
    abss = _codes(caps.get(ecodes.EV_ABS, []))

    if keys & LETTER_CODES or ecodes.EV_LED in caps:
        return DeviceKind.KEYBOARD
    if keys & GAMEPAD_MARKERS:
        return DeviceKind.OTHER
    if ecodes.REL_X in rels or ecodes.REL_Y in rels:
        return DeviceKind.POINTER
    if {ecodes.ABS_X, ecodes.ABS_Y} <= abss and ecodes.BTN_TOUCH in keys:
        return DeviceKind.POINTER
    if keys and not keys <= POWER_CODES:
        return DeviceKind.KEYBOARD
    return DeviceKind.OTHER


@dataclasses.dataclass(frozen=True)
class InputDeviceInfo:
    path: str
    name: str
    kind: DeviceKind


def discover(exclude: Sequence[str] = ()) -> list[InputDeviceInfo]:
    """Scan /dev/input and return readable keyboard/pointer devices, sorted by path.

    Globs /dev/input/event* directly instead of evdev.list_devices(), which silently
    drops unreadable devices — we want to see them and tell the user how to fix access.
    """
    global _HINT_LOGGED
    found: list[InputDeviceInfo] = []
    some_unreadable = False
    for path in sorted(glob.glob("/dev/input/event*")):
        try:
            dev = evdev.InputDevice(path)
        except OSError:
            some_unreadable = True
            continue
        try:
            name = dev.name or path
            if any(part.lower() in name.lower() for part in exclude):
                continue
            kind = classify(dev.capabilities())
            if kind is not DeviceKind.OTHER:
                found.append(InputDeviceInfo(path=path, name=name, kind=kind))
        finally:
            dev.close()
    if some_unreadable and not _HINT_LOGGED:
        _HINT_LOGGED = True
        log.warning(
            "Some /dev/input devices are not readable. For full coverage add your user to the"
            " 'input' group: sudo usermod -aG input %s (then log out and back in).",
            getpass.getuser(),
        )
    found.sort(key=lambda info: info.path)
    return found
