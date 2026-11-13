"""ActivityWatch REST client (stdlib urllib) + retry queue.

Talks to the local ActivityWatch server only (default http://localhost:5600).
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from collections import deque
from collections.abc import Mapping, Sequence

log = logging.getLogger(__name__)

_USER_AGENT = "omarchy-pulse-watcher"

#: Bucket type matching the stock aw-watcher-input schema.
BUCKET_TYPE = "os.hid.input"

#: HTTP statuses returned by a successful bucket request: created / already exists.
_BUCKET_OK = (200, 304)


class ActivityWatchClient:
    def __init__(
        self,
        base_url: str,
        bucket_id: str,
        hostname: str,
        client_name: str = "omarchy-pulse",
        timeout_s: float = 5.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.bucket_id = bucket_id
        self.hostname = hostname
        self.client_name = client_name
        self.timeout_s = timeout_s

    def _request(self, method: str, path: str, payload: object | None = None) -> tuple[int, str]:
        """Return (http_status, body); status 0 means the server was unreachable."""
        data = None
        headers = {"User-Agent": _USER_AGENT}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            f"{self.base_url}{path}", data=data, headers=headers, method=method
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                return response.status, response.read().decode("utf-8", "replace")[:2000]
        except urllib.error.HTTPError as exc:  # 3xx/4xx/5xx — still a server answer
            return exc.code, exc.read().decode("utf-8", "replace")[:2000]
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            return 0, str(getattr(exc, "reason", exc))

    def ensure_bucket(self) -> bool:
        """Create the bucket if missing; True also when it already exists (HTTP 304)."""
        payload = {"client": self.client_name, "type": BUCKET_TYPE, "hostname": self.hostname}
        status, body = self._request("POST", f"/api/0/buckets/{self.bucket_id}", payload)
        if status in _BUCKET_OK:
            log.debug("bucket %s present (HTTP %d)", self.bucket_id, status)
            return True
        log.error("bucket creation failed (HTTP %d): %s", status, body)
        return False

    def send_events(self, events: Sequence[Mapping]) -> bool:
        if not events:
            return True
        status, body = self._request(
            "POST", f"/api/0/buckets/{self.bucket_id}/events", list(events)
        )
        if status == 200:
            return True
        log.error("sending %d event(s) failed (HTTP %d): %s", len(events), status, body)
        return False


class EventShipper:
    """Ships per-minute events, keeping a bounded queue across ActivityWatch outages."""

    def __init__(self, client: ActivityWatchClient, max_pending: int = 180) -> None:
        self._client = client
        self._max_pending = max_pending
        self._pending: deque[dict] = deque()

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    def ship(self, new_events: Sequence[Mapping]) -> None:
        """Queue new events and try to flush everything (retrying empty keeps the queue moving)."""
        self._pending.extend(new_events)
        overflow = len(self._pending) - self._max_pending
        if overflow > 0:
            for _ in range(overflow):
                self._pending.popleft()
            log.warning("queue overflow: dropped %d oldest minute(s)", overflow)
        if not self._pending:
            return
        if self._client.send_events(list(self._pending)):
            self._pending.clear()
            return
        # The bucket may have vanished (e.g. ActivityWatch restarted with a fresh DB).
        self._client.ensure_bucket()
        if self._client.send_events(list(self._pending)):
            self._pending.clear()
            return
        log.warning("ActivityWatch unreachable; %d minute(s) queued for retry", len(self._pending))
