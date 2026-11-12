"""EventTranslator tests: raw evdev triples -> semantic counts (privacy: no key identity)."""

from evdev import ecodes

from pulse_watcher.reader import EventTranslator


def test_key_press_autorepeat_release():
    translator = EventTranslator()
    assert translator.feed(ecodes.EV_KEY, ecodes.KEY_A, 1) == [("presses", 1)]
    assert translator.feed(ecodes.EV_KEY, ecodes.KEY_A, 2) == []  # autorepeat: not a new press
    assert translator.feed(ecodes.EV_KEY, ecodes.KEY_A, 0) == []  # release
    assert translator.feed(ecodes.EV_KEY, ecodes.KEY_A, 1) == [("presses", 1)]  # next press counts


def test_mouse_buttons_count_only_presses():
    translator = EventTranslator()
    assert translator.feed(ecodes.EV_KEY, ecodes.BTN_LEFT, 1) == [("clicks", 1)]
    assert translator.feed(ecodes.EV_KEY, ecodes.BTN_LEFT, 0) == []
    assert translator.feed(ecodes.EV_KEY, ecodes.BTN_RIGHT, 1) == [("clicks", 1)]
    assert translator.feed(ecodes.EV_KEY, ecodes.BTN_MIDDLE, 1) == [("clicks", 1)]


def test_relative_motion_and_scroll():
    translator = EventTranslator()
    assert translator.feed(ecodes.EV_REL, ecodes.REL_X, 7) == [("deltaX", 7)]
    assert translator.feed(ecodes.EV_REL, ecodes.REL_Y, -3) == [("deltaY", 3)]
    assert translator.feed(ecodes.EV_REL, ecodes.REL_WHEEL, -1) == [("scrollY", 1)]
    assert translator.feed(ecodes.EV_REL, ecodes.REL_HWHEEL, 1) == [("scrollX", 1)]
    assert translator.feed(ecodes.EV_REL, ecodes.REL_WHEEL, 0) == []
    # Hi-res wheel fires alongside REL_WHEEL; counting both would double scroll.
    assert translator.feed(ecodes.EV_REL, ecodes.REL_WHEEL_HI_RES, 120) == []


def test_touchpad_absolute_motion():
    translator = EventTranslator()
    assert translator.feed(ecodes.EV_KEY, ecodes.BTN_TOUCH, 1) == []
    assert translator.feed(ecodes.EV_ABS, ecodes.ABS_X, 100) == []  # first sample: no delta
    assert translator.feed(ecodes.EV_ABS, ecodes.ABS_X, 106) == [("deltaX", 6)]
    assert translator.feed(ecodes.EV_ABS, ecodes.ABS_Y, 50) == []  # first sample on Y axis
    assert translator.feed(ecodes.EV_ABS, ecodes.ABS_Y, 54) == [("deltaY", 4)]
    assert translator.feed(ecodes.EV_KEY, ecodes.BTN_TOUCH, 0) == []
    assert translator.feed(ecodes.EV_ABS, ecodes.ABS_X, 120) == []  # finger up: no distance


def test_touch_and_tool_buttons_are_never_counted():
    translator = EventTranslator()
    assert translator.feed(ecodes.EV_KEY, ecodes.BTN_TOUCH, 1) == []
    assert translator.feed(ecodes.EV_KEY, ecodes.BTN_TOOL_FINGER, 1) == []
    assert translator.feed(ecodes.EV_KEY, ecodes.BTN_TOOL_PEN, 1) == []
    assert translator.feed(ecodes.EV_KEY, ecodes.BTN_STYLUS, 1) == []


def test_translator_emits_only_count_kinds():
    translator = EventTranslator()
    known = {"presses", "clicks", "deltaX", "deltaY", "scrollX", "scrollY"}
    samples = [
        (ecodes.EV_KEY, ecodes.KEY_F, 1),
        (ecodes.EV_KEY, ecodes.BTN_LEFT, 1),
        (ecodes.EV_REL, ecodes.REL_X, 5),
        (ecodes.EV_REL, ecodes.REL_Y, 5),
        (ecodes.EV_REL, ecodes.REL_WHEEL, 1),
        (ecodes.EV_REL, ecodes.REL_HWHEEL, 1),
    ]
    for etype, code, value in samples:
        for kind, _amount in translator.feed(etype, code, value):
            assert kind in known
