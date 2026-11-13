"""Timeline tests: device-ownership seconds from synthetic input action streams.

The named scenarios mirror the worked examples in docs/PLAN.md (decision D10):
each builds a minute of known activity and asserts the exact keyboard/mouse/
both split. Feeding order is deliberately not sorted — Timeline.drain() must
order by timestamp itself.
"""

from pulse_watcher.counter import MinuteCounter, floor_minute
from pulse_watcher.timeline import KB, MOUSE, RESOLVE_S, Action, Timeline

M = floor_minute(1_700_000_000.0)  # a minute boundary; all ts are M + seconds


def press(t: float) -> Action:
    return Action(KB, "press", 1.0, M + t)


def repeat(t: float) -> Action:
    return Action(KB, "repeat", 1.0, M + t)


def down(t: float) -> Action:
    return Action(MOUSE, "button_down", 1.0, M + t)


def up(t: float) -> Action:
    return Action(MOUSE, "button_up", 1.0, M + t)


def motion(t: float, mm: float = 5.0) -> Action:
    return Action(MOUSE, "motion", mm, M + t)


def wheel(t: float) -> Action:
    return Action(MOUSE, "wheel", 1.0, M + t)


def run(actions, now: float | None = None):
    """Feed actions through a timeline, then close any stale burst."""
    counter = MinuteCounter()
    timeline = Timeline(counter)
    for action in actions:
        timeline.feed(action)
    timeline.drain()
    timeline.close_stale(M + 3600.0 if now is None else now)
    return counter


def seconds(counter, minute: int = M, now: float | None = None) -> dict:
    events = dict(counter.take_completed(minute + 60.0 if now is None else now))
    assert minute in events, f"minute {minute} missing, got {sorted(events)}"
    return events[minute]


# -- Example 1: keyboard -> mouse -> keyboard --------------------------------


def test_typing_click_typing_split():
    # Type two keys, use the mouse 0.9-4.15 s, then keep typing until 10 s.
    # Homing (0.4 s) is credited to the device being switched to.
    actions = [press(0.0), press(0.1)]
    actions += [motion(t) for t in (0.9, 1.4, 1.9, 2.4, 2.9, 3.4, 3.9)]
    actions += [down(4.1), up(4.15)]
    actions += [press(5.0 + 0.2 * i) for i in range(26)]  # 5.0..10.0
    data = seconds(run(actions))
    assert abs(data["kbS"] - 6.9) < 0.05  # [0, 0.5] + [4.6, 11.0]
    assert abs(data["mouseS"] - 4.1) < 0.05  # [0.5, 4.6]
    assert data["bothS"] == 0.0


# -- Example 2: scrolling + shortcut clicks beat a little typing --------------


def test_browsing_counts_mouse_not_keyboard():
    # 30 s of scrolling and three Ctrl+clicks, then a short typed URL.
    actions = [wheel(0.8 * i) for i in range(38)]  # 0..29.6
    actions += [press(30.1), down(30.2), up(30.25)]
    actions += [press(30.4), down(30.5), up(30.55)]
    actions += [press(30.7), down(30.8), up(30.85)]
    actions += [press(31.6 + 0.2 * i) for i in range(6)]  # "github" 31.6..32.6
    data = seconds(run(actions))
    assert abs(data["mouseS"] - 31.2) < 0.05  # [0, 31.2]
    assert abs(data["kbS"] - 2.4) < 0.05  # [31.2, 33.6]: homing + typing + tail


# -- Example 3: Shift+drag is mouse work --------------------------------------


def test_shift_drag_counts_as_mouse():
    actions = [press(0.0), down(0.1)]
    actions += [motion(0.2 + 0.1 * i, mm=2.0) for i in range(14)]  # 0.2..1.5
    actions += [up(1.6)]
    data = seconds(run(actions))
    assert data["kbS"] == 0.0  # the Shift press is part of the drag
    assert abs(data["mouseS"] - 2.6) < 0.05  # [0, 1.6] + tail


def test_modifier_pressed_right_before_a_click_counts_as_mouse():
    actions = [press(1.0), down(1.2), up(1.25)]
    data = seconds(run(actions))
    assert data["kbS"] == 0.0
    assert abs(data["mouseS"] - 1.25) < 0.05  # [1.0, 2.25]


def test_chord_window_is_tight():
    # 0.2 s before a click: mouse. 0.4 s after it: keyboard again.
    actions = [press(0.35), down(0.5), up(0.5), press(0.9)]
    data = seconds(run(actions))
    assert abs(data["mouseS"] - 0.15) < 0.05  # [0.35, 0.5]
    assert abs(data["kbS"] - 1.4) < 0.05  # [0.5, 1.9] incl. homing and tail


def test_chord_applies_across_drain_batches():
    counter = MinuteCounter()
    timeline = Timeline(counter)
    for action in (down(10.0), up(10.1)):
        timeline.feed(action)
    timeline.drain()
    timeline.feed(press(10.3))  # 0.2 s after the click of the previous batch
    timeline.drain()
    timeline.close_stale(M + 120.0)
    data = seconds(counter, now=M + 120.0)
    assert data["kbS"] == 0.0
    assert abs(data["mouseS"] - 1.3) < 0.05  # [10.0, 11.3]


# -- Example 4: hand tremor while reading stays idle --------------------------


def test_hand_tremor_stays_idle():
    actions = [motion(10.0 * i, mm=0.1) for i in range(6)]  # every 10 s, < 1 mm
    counter = run(actions)
    assert counter.take_completed(M + 120.0) == []


def test_slow_continuous_motion_counts():
    # 0.6 mm every 200 ms crosses the 1 mm / 250 ms window on every second event.
    actions = [motion(0.2 * i, mm=0.6) for i in range(100)]  # 0..19.8
    data = seconds(run(actions))
    assert abs(data["mouseS"] - 20.2) < 0.05  # [0.2, 20.4]


# -- Example 5: holding a key is keyboard time --------------------------------


def test_held_key_autorepeat_counts_keyboard_time():
    actions = [press(0.0)] + [repeat(0.05 * i) for i in range(1, 61)]  # to 3.0
    data = seconds(run(actions))
    assert abs(data["kbS"] - 4.0) < 0.05  # [0, 4.0] with tail
    assert data["mouseS"] == 0.0


# -- Example 6: gaming — keyboard and mouse at the same time ------------------


def test_gaming_simultaneous_keyboard_and_mouse():
    # WASD and aiming alternate faster than the homing time: both at once.
    actions = []
    for i in range(600):
        actions.append(press(0.1 * i))
        actions.append(motion(0.1 * i + 0.05, mm=3.0))
    data = seconds(run(actions))
    assert data["bothS"] > 50.0
    assert data["kbS"] < 2.0
    assert data["mouseS"] < 2.0
    assert data["kbS"] + data["mouseS"] + data["bothS"] <= 60.0


def test_both_spans_minute_boundaries():
    actions = []
    for i in range(100):  # 55.0..64.95, alternating every 50 ms
        actions.append(press(55.0 + 0.1 * i))
        actions.append(motion(55.0 + 0.1 * i + 0.05, mm=3.0))
    counter = run(actions)
    events = dict(counter.take_completed(M + 180.0))
    assert events[M]["bothS"] > 4.0
    assert events[M + 60]["bothS"] > 4.0
    assert events[M]["kbS"] + events[M]["mouseS"] < 1.0


def test_slow_device_switching_stays_separate():
    # Alternation at 1 s is slower than rapid flipping: normal hand-overs.
    actions = [press(0.0), motion(1.0), press(2.0), motion(3.0)]
    data = seconds(run(actions))
    assert data["bothS"] == 0.0
    assert abs(data["kbS"] - 1.6) < 0.05
    assert abs(data["mouseS"] - 2.4) < 0.05


# -- Example 7: thinking pauses split typing into bursts ----------------------


def test_thinking_pauses_split_typing_bursts():
    # Burst 0..1 s, 2.6 s think, burst 3.6..4.6 s: only short pauses stay keyboard.
    actions = [press(0.2 * i) for i in range(6)]
    actions += [press(3.6 + 0.2 * i) for i in range(6)]
    data = seconds(run(actions))
    assert abs(data["kbS"] - 4.0) < 0.05  # [0, 2] + [3.6, 5.6]


def test_short_pause_stays_one_keyboard_burst():
    actions = [press(0.2 * i) for i in range(6)]  # 0..1.0
    actions += [press(2.5 + 0.2 * i) for i in range(6)]  # 1.5 s pause: still typing
    data = seconds(run(actions))
    assert abs(data["kbS"] - 4.5) < 0.05  # one burst [0, 3.5] + tail


# -- Edge cases ---------------------------------------------------------------


def test_segments_split_at_minute_boundaries():
    actions = [press(59.0), press(59.5), press(61.0)]
    counter = run(actions)
    events = dict(counter.take_completed(M + 180.0))
    assert abs(events[M]["kbS"] - 1.0) < 1e-9  # [59, 60)
    assert abs(events[M + 60]["kbS"] - 2.0) < 1e-9  # [60, 62] incl. tail


def test_minute_flushes_only_after_burst_resolution():
    counter = MinuteCounter(resolve_s=RESOLVE_S)
    timeline = Timeline(counter)
    timeline.feed(press(10.0))
    timeline.drain()
    timeline.close_stale(M + 111.0)  # burst ends at 11.0 with its tail
    assert counter.take_completed(M + 62.9) == []
    events = counter.take_completed(M + 63.0)
    assert abs(events[0][1]["kbS"] - 1.0) < 1e-9


def test_held_button_stays_mouse_without_events():
    counter = MinuteCounter()
    timeline = Timeline(counter)
    timeline.feed(down(1.0))
    timeline.drain()
    timeline.close_stale(M + 30.0)  # a held button is continuous mouse activity
    assert counter.take_completed(M + 30.0) == []
    timeline.feed(up(35.0))
    timeline.drain()
    timeline.close_stale(M + 36.5)
    data = seconds(counter, now=M + 60.0)
    assert abs(data["mouseS"] - 35.0) < 0.05  # the whole hold [1, 36]
    assert data["kbS"] == 0.0


def test_batch_is_sorted_by_timestamp_before_processing():
    # Two presses 4 s apart are two bursts; processing them out of order
    # would misattribute the gap.
    actions = [press(5.0), press(1.0)]
    data = seconds(run(actions))
    assert abs(data["kbS"] - 2.0) < 0.05  # [1, 2] + [5, 6]


def test_empty_minute_produces_no_event():
    counter = run([])
    assert counter.take_completed(M + 120.0) == []
