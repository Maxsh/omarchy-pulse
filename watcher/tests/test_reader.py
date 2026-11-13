"""EventTranslator tests: raw evdev events -> counts + timeline actions.

Privacy: no key identity anywhere — counts and device-class actions only.
"""

from evdev import ecodes

from pulse_watcher.reader import EventTranslator
from pulse_watcher.timeline import (
    CLICK_DOWN,
    CLICK_UP,
    KB,
    MOTION,
    MOUSE,
    PRESS,
    REPEAT,
    WHEEL,
)

TS = 1_700_000_000.0


def _actions(translation):
    return [(a.dev, a.kind, round(a.amount, 6), a.ts) for a in translation.actions]


def test_key_press_autorepeat_release():
    translator = EventTranslator()
    t = translator.feed(ecodes.EV_KEY, ecodes.KEY_A, 1, TS)
    assert t.counts == [("presses", 1)]
    assert _actions(t) == [(KB, PRESS, 1.0, TS)]
    t = translator.feed(ecodes.EV_KEY, ecodes.KEY_A, 2, TS + 0.1)
    assert t.counts == []  # autorepeat: not a new press…
    assert _actions(t) == [(KB, REPEAT, 1.0, TS + 0.1)]  # …but the hand is still typing
    t = translator.feed(ecodes.EV_KEY, ecodes.KEY_A, 0, TS + 0.2)
    assert t.counts == [] and t.actions == []
    t = translator.feed(ecodes.EV_KEY, ecodes.KEY_A, 1, TS + 0.3)
    assert t.counts == [("presses", 1)]  # next press counts


def test_mouse_buttons_count_only_presses():
    translator = EventTranslator()
    t = translator.feed(ecodes.EV_KEY, ecodes.BTN_LEFT, 1, TS)
    assert t.counts == [("clicks", 1)]
    assert _actions(t) == [(MOUSE, CLICK_DOWN, 1.0, TS)]
    t = translator.feed(ecodes.EV_KEY, ecodes.BTN_LEFT, 0, TS + 0.1)
    assert t.counts == []
    assert _actions(t) == [(MOUSE, CLICK_UP, 1.0, TS + 0.1)]
    t = translator.feed(ecodes.EV_KEY, ecodes.BTN_RIGHT, 1, TS)
    assert t.counts == [("clicks", 1)]
    t = translator.feed(ecodes.EV_KEY, ecodes.BTN_MIDDLE, 1, TS)
    assert t.counts == [("clicks", 1)]


def test_relative_motion_and_scroll():
    translator = EventTranslator(rel_units_per_mm=2.0)  # 2 counts per mm for clean numbers
    t = translator.feed(ecodes.EV_REL, ecodes.REL_X, 7, TS)
    assert t.counts == [("deltaX", 7)]
    assert _actions(t) == [(MOUSE, MOTION, 3.5, TS)]
    t = translator.feed(ecodes.EV_REL, ecodes.REL_Y, -3, TS)
    assert t.counts == [("deltaY", 3)]
    assert _actions(t) == [(MOUSE, MOTION, 1.5, TS)]
    t = translator.feed(ecodes.EV_REL, ecodes.REL_WHEEL, -1, TS)
    assert t.counts == [("scrollY", 1)]
    assert _actions(t) == [(MOUSE, WHEEL, 1.0, TS)]
    t = translator.feed(ecodes.EV_REL, ecodes.REL_HWHEEL, 1, TS)
    assert t.counts == [("scrollX", 1)]
    t = translator.feed(ecodes.EV_REL, ecodes.REL_WHEEL, 0, TS)
    assert t.counts == [] and t.actions == []
    # Hi-res wheel fires alongside REL_WHEEL; counting both would double scroll.
    t = translator.feed(ecodes.EV_REL, ecodes.REL_WHEEL_HI_RES, 120, TS)
    assert t.counts == [] and t.actions == []


def test_touchpad_motion_uses_device_resolution():
    translator = EventTranslator(abs_units_per_mm=2.0)  # 2 units per mm
    assert translator.feed(ecodes.EV_KEY, ecodes.BTN_TOUCH, 1, TS).counts == []
    t = translator.feed(ecodes.EV_ABS, ecodes.ABS_X, 100, TS)
    assert t.counts == [] and t.actions == []  # first sample: no delta
    t = translator.feed(ecodes.EV_ABS, ecodes.ABS_X, 106, TS + 0.1)
    assert t.counts == [("deltaX", 6)]
    assert _actions(t) == [(MOUSE, MOTION, 3.0, TS + 0.1)]  # 6 units = 3 mm
    t = translator.feed(ecodes.EV_ABS, ecodes.ABS_Y, 50, TS + 0.2)
    assert t.counts == []  # first sample on Y axis
    # Contact ends after 0.4 s — too long for a tap.
    t = translator.feed(ecodes.EV_KEY, ecodes.BTN_TOUCH, 0, TS + 0.4)
    assert t.counts == [] and t.actions == []
    t = translator.feed(ecodes.EV_ABS, ecodes.ABS_X, 120, TS + 0.5)
    assert t.counts == [] and t.actions == []  # finger up: no distance


def test_new_touch_does_not_diff_against_the_previous_contact():
    translator = EventTranslator(abs_units_per_mm=1.0)
    translator.feed(ecodes.EV_KEY, ecodes.BTN_TOUCH, 1, 0.0)
    translator.feed(ecodes.EV_ABS, ecodes.ABS_X, 100, 0.1)
    t = translator.feed(ecodes.EV_ABS, ecodes.ABS_X, 110, 0.2)
    assert t.counts == [("deltaX", 10)]
    translator.feed(ecodes.EV_KEY, ecodes.BTN_TOUCH, 0, 0.3)  # long touch: no tap
    # New contact far away from the old one: must not produce a phantom delta.
    translator.feed(ecodes.EV_KEY, ecodes.BTN_TOUCH, 1, 5.0)
    t = translator.feed(ecodes.EV_ABS, ecodes.ABS_X, 40, 5.1)
    assert t.counts == [] and t.actions == []
    t = translator.feed(ecodes.EV_ABS, ecodes.ABS_X, 42, 5.2)
    assert t.counts == [("deltaX", 2)]


def test_short_still_touch_counts_as_a_tap_click():
    translator = EventTranslator(abs_units_per_mm=1.0)
    translator.feed(ecodes.EV_KEY, ecodes.BTN_TOUCH, 1, 10.0)
    translator.feed(ecodes.EV_ABS, ecodes.ABS_X, 100, 10.05)  # first sample
    translator.feed(ecodes.EV_ABS, ecodes.ABS_X, 101, 10.1)  # 1 mm of travel
    t = translator.feed(ecodes.EV_KEY, ecodes.BTN_TOUCH, 0, 10.15)
    assert t.counts == [("clicks", 1)]  # tap-to-click happens in libinput, not the kernel
    assert _actions(t) == [(MOUSE, CLICK_DOWN, 1.0, 10.15), (MOUSE, CLICK_UP, 1.0, 10.15)]


def test_traveling_or_long_touch_is_not_a_tap():
    translator = EventTranslator(abs_units_per_mm=1.0)
    translator.feed(ecodes.EV_KEY, ecodes.BTN_TOUCH, 1, 10.0)
    translator.feed(ecodes.EV_ABS, ecodes.ABS_X, 100, 10.05)
    translator.feed(ecodes.EV_ABS, ecodes.ABS_X, 110, 10.1)  # 10 mm: a swipe, not a tap
    t = translator.feed(ecodes.EV_KEY, ecodes.BTN_TOUCH, 0, 10.15)
    assert t.counts == [] and t.actions == []
    translator.feed(ecodes.EV_KEY, ecodes.BTN_TOUCH, 1, 20.0)
    translator.feed(ecodes.EV_ABS, ecodes.ABS_X, 110, 20.05)
    t = translator.feed(ecodes.EV_KEY, ecodes.BTN_TOUCH, 0, 20.9)  # 0.9 s: too long
    assert t.counts == [] and t.actions == []


def test_touch_and_tool_buttons_are_never_counted():
    translator = EventTranslator()
    for code in (
        ecodes.BTN_TOUCH,
        ecodes.BTN_TOOL_FINGER,
        ecodes.BTN_TOOL_PEN,
        ecodes.BTN_STYLUS,
    ):
        t = translator.feed(ecodes.EV_KEY, code, 1, TS)
        assert t.counts == [] and t.actions == []


def test_translator_emits_only_known_kinds():
    # Privacy rule #1 (AGENTS.md): counts and device-class actions only.
    translator = EventTranslator()
    count_kinds = {"presses", "clicks", "deltaX", "deltaY", "scrollX", "scrollY"}
    action_kinds = {PRESS, REPEAT, CLICK_DOWN, CLICK_UP, MOTION, WHEEL}
    samples = [
        (ecodes.EV_KEY, ecodes.KEY_F, 1),
        (ecodes.EV_KEY, ecodes.KEY_F, 2),
        (ecodes.EV_KEY, ecodes.BTN_LEFT, 1),
        (ecodes.EV_KEY, ecodes.BTN_LEFT, 0),
        (ecodes.EV_REL, ecodes.REL_X, 5),
        (ecodes.EV_REL, ecodes.REL_Y, 5),
        (ecodes.EV_REL, ecodes.REL_WHEEL, 1),
        (ecodes.EV_REL, ecodes.REL_HWHEEL, 1),
    ]
    for etype, code, value in samples:
        t = translator.feed(etype, code, value, TS)
        assert {kind for kind, _ in t.counts} <= count_kinds
        assert {a.kind for a in t.actions} <= action_kinds
        assert {a.dev for a in t.actions} <= {KB, MOUSE}
