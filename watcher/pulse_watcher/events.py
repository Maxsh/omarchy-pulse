"""ActivityWatch event building."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime

EVENT_DURATION_S = 60.0


def build_event(minute_ts: int, data: Mapping[str, int], duration_s: float = EVENT_DURATION_S) -> dict:
    """Build one ActivityWatch event covering [minute_ts, minute_ts + duration)."""
    timestamp = datetime.fromtimestamp(minute_ts, tz=UTC).isoformat()
    return {"timestamp": timestamp, "duration": duration_s, "data": dict(data)}
