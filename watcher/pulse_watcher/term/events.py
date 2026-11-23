"""ActivityWatch heartbeat building for the terminal-focus bucket."""

from __future__ import annotations

from datetime import UTC, datetime

#: Bucket type; the widget discovers the bucket by it.
BUCKET_TYPE = "app.terminal.focus"

#: The complete set of keys an event may carry (privacy rule 1, asserted by tests).
DATA_KEYS = frozenset({"app", "terminal", "via"})


def build_heartbeat(now: float, app: str, terminal: str, via: str) -> dict:
    """One zero-duration heartbeat; ActivityWatch merges equal data within pulsetime."""
    return {
        "timestamp": datetime.fromtimestamp(now, tz=UTC).isoformat(),
        "duration": 0,
        "data": {"app": app, "terminal": terminal, "via": via},
    }
