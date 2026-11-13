"""ActivityWatch event building."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime

from .counter import SECOND_KEYS

EVENT_DURATION_S = 60.0


def build_event(
    minute_ts: int, data: Mapping[str, int | float], duration_s: float = EVENT_DURATION_S
) -> dict:
    """Build one ActivityWatch event covering [minute_ts, minute_ts + duration)."""
    payload = dict(data)
    for key in SECOND_KEYS:
        if key in payload:
            payload[key] = round(float(payload[key]), 2)
    timestamp = datetime.fromtimestamp(minute_ts, tz=UTC).isoformat()
    return {"timestamp": timestamp, "duration": duration_s, "data": payload}
