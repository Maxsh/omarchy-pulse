"""Device classification tests with synthetic capability dicts (no real devices needed)."""

from evdev import ecodes

from pulse_watcher.devices import DeviceKind, classify


def caps(*groups: tuple[int, list]) -> dict[int, list]:
    return dict(groups)


def test_keyboard_by_letters():
    result = classify(caps((ecodes.EV_KEY, [ecodes.KEY_A, ecodes.KEY_Q, ecodes.KEY_SPACE])))
    assert result is DeviceKind.KEYBOARD


def test_keyboard_by_led():
    result = classify(
        caps(
            (ecodes.EV_KEY, [ecodes.KEY_PLAYPAUSE]),
            (ecodes.EV_LED, [ecodes.LED_CAPSL]),
        )
    )
    assert result is DeviceKind.KEYBOARD


def test_mouse():
    result = classify(
        caps(
            (ecodes.EV_KEY, [ecodes.BTN_LEFT, ecodes.BTN_RIGHT]),
            (ecodes.EV_REL, [ecodes.REL_X, ecodes.REL_Y, ecodes.REL_WHEEL]),
        )
    )
    assert result is DeviceKind.POINTER


def test_touchpad():
    result = classify(
        caps(
            (ecodes.EV_KEY, [ecodes.BTN_TOUCH, ecodes.BTN_TOOL_FINGER]),
            (ecodes.EV_ABS, [(ecodes.ABS_X, None), (ecodes.ABS_Y, None)]),
        )
    )
    assert result is DeviceKind.POINTER


def test_gamepad_is_ignored():
    result = classify(
        caps(
            (ecodes.EV_KEY, [ecodes.BTN_SOUTH, ecodes.BTN_EAST, ecodes.BTN_START]),
            (ecodes.EV_ABS, [(ecodes.ABS_X, None), (ecodes.ABS_Y, None)]),
        )
    )
    assert result is DeviceKind.OTHER


def test_power_button_is_ignored():
    assert classify(caps((ecodes.EV_KEY, [ecodes.KEY_POWER]))) is DeviceKind.OTHER
    assert classify(caps((ecodes.EV_KEY, [ecodes.KEY_SLEEP]))) is DeviceKind.OTHER


def test_consumer_control_is_keyboard():
    result = classify(
        caps((ecodes.EV_KEY, [ecodes.KEY_PLAYPAUSE, ecodes.KEY_VOLUMEUP, ecodes.KEY_CALC])),
    )
    assert result is DeviceKind.KEYBOARD


def test_combined_keyboard_with_trackpoint_is_keyboard():
    result = classify(
        caps(
            (ecodes.EV_KEY, [ecodes.KEY_A]),
            (ecodes.EV_REL, [ecodes.REL_X, ecodes.REL_Y]),
            (ecodes.EV_LED, [ecodes.LED_CAPSL]),
        )
    )
    assert result is DeviceKind.KEYBOARD
