"""MinuteCounter tests: binning, ordering, skipping empty minutes, completion cutoff."""

from pulse_watcher.counter import SECOND_KEYS, MinuteCounter, floor_minute

T0 = 1_700_000_000.0  # arbitrary, not minute-aligned
M0 = floor_minute(T0)
ZERO = {
    "presses": 0,
    "clicks": 0,
    "deltaX": 0,
    "deltaY": 0,
    "scrollX": 0,
    "scrollY": 0,
    "kbS": 0.0,
    "mouseS": 0.0,
    "bothS": 0.0,
}


def test_floor_minute():
    assert floor_minute(M0 + 0.5) == M0
    assert floor_minute(M0 + 59.9) == M0
    assert floor_minute(M0 + 60.0) == M0 + 60


def test_records_aggregate_within_one_minute():
    counter = MinuteCounter()
    counter.record("presses", 3, T0)
    counter.record("presses", 2, T0 + 10)
    counter.record("clicks", 1, T0 + 20)
    counter.record("deltaX", 40, T0 + 30)
    counter.record("deltaY", 7, T0 + 31)
    counter.record("scrollY", 2, T0 + 32)

    events = counter.take_completed(M0 + 120)
    assert len(events) == 1
    minute, data = events[0]
    assert minute == M0
    assert data["presses"] == 5
    assert data["clicks"] == 1
    assert data["deltaX"] == 40
    assert data["deltaY"] == 7
    assert data["scrollY"] == 2
    assert set(data) == set(ZERO)


def test_minutes_are_ordered_and_popped():
    counter = MinuteCounter()
    counter.record("presses", 1, T0 + 5)
    counter.record("presses", 1, M0 + 65)  # next minute
    events = counter.take_completed(M0 + 180)
    assert [minute for minute, _ in events] == [M0, M0 + 60]
    assert counter.take_completed(M0 + 300) == []


def test_empty_minutes_are_skipped():
    counter = MinuteCounter()
    counter.record("presses", 1, T0)  # minute M0
    counter.record("presses", 1, M0 + 180)  # minutes M0+60 and M0+120 stay empty
    events = counter.take_completed(M0 + 240)
    assert [minute for minute, _ in events] == [M0, M0 + 180]


def test_current_minute_is_not_completed():
    counter = MinuteCounter()
    counter.record("presses", 1, M0 + 10)
    assert counter.take_completed(M0 + 30) == []
    assert counter.take_completed(M0 + 70) == [(M0, {**ZERO, "presses": 1})]


def test_zero_and_negative_amounts_are_ignored():
    counter = MinuteCounter()
    counter.record("presses", 0, T0)
    counter.record("presses", -1, T0)
    counter.record("clicks", 1, T0)
    events = counter.take_completed(M0 + 60)
    assert events == [(M0, {**ZERO, "clicks": 1})]


def test_records_from_many_devices_sum_up():
    counter = MinuteCounter()
    counter.record("presses", 1, T0)  # "device A"
    counter.record("presses", 1, T0 + 1)  # "device B"
    counter.record("clicks", 1, T0 + 2)  # "device C"
    events = counter.take_completed(M0 + 60)
    assert events == [(M0, {**ZERO, "presses": 2, "clicks": 1})]


def test_add_seconds_accumulates_and_caps_at_a_minute():
    counter = MinuteCounter()
    counter.record("presses", 1, T0)
    counter.add_seconds(T0, "kbS", 40.0)
    counter.add_seconds(T0, "mouseS", 30.0)  # would overflow: capped to keep the sum ≤ 60
    events = counter.take_completed(M0 + 60)
    assert events == [(M0, {**ZERO, "presses": 1, "kbS": 40.0, "mouseS": 20.0})]


def test_add_seconds_ignores_empty_and_creates_bins():
    counter = MinuteCounter()
    counter.add_seconds(T0, "bothS", 0.0)  # nothing to add
    counter.add_seconds(T0, "mouseS", 7.5)
    counter.add_seconds(T0 + 150, "kbS", 1.0)  # minute M0+120 gets its own bin
    events = counter.take_completed(M0 + 180)
    assert [minute for minute, _ in events] == [M0, M0 + 120]
    assert events[0][1]["mouseS"] == 7.5
    assert events[1][1]["kbS"] == 1.0


def test_reattribute_moves_seconds_between_fields():
    counter = MinuteCounter()
    counter.add_seconds(T0, "kbS", 10.0)
    counter.reattribute_seconds(T0, "kbS", "bothS", 4.0)
    counter.reattribute_seconds(T0, "kbS", "bothS", 100.0)  # clamped to what is there
    events = counter.take_completed(M0 + 60)
    assert events == [(M0, {**ZERO, "kbS": 0.0, "bothS": 10.0})]


def test_reattribute_ignores_unseen_minutes():
    counter = MinuteCounter()
    counter.reattribute_seconds(T0, "kbS", "bothS", 5.0)  # no bin: no-op, no crash
    assert counter.take_completed(M0 + 60) == []


def test_resolve_margin_holds_minutes_until_bursts_resolve():
    counter = MinuteCounter(resolve_s=3.0)
    counter.record("presses", 1, M0 + 10)
    assert counter.take_completed(M0 + 62.9) == []
    assert [minute for minute, _ in counter.take_completed(M0 + 63.0)] == [M0]


def test_emitted_schema_contains_only_counts_and_seconds():
    # Privacy rule #1 (AGENTS.md): the event schema carries counts and derived
    # idle/seconds fields only — never anything that identifies a key.
    counter = MinuteCounter()
    counter.record("presses", 1, T0)
    counter.add_seconds(T0, "bothS", 5.0)
    ((_, data),) = counter.take_completed(M0 + 60)
    assert set(data) == set(ZERO)  # counts + seconds, and nothing else
    assert SECOND_KEYS == ("kbS", "mouseS", "bothS")
