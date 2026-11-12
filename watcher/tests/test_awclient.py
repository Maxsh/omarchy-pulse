"""ActivityWatchClient + EventShipper tests against a stub HTTP server (no real AW needed)."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import ClassVar

import pytest

from pulse_watcher.awclient import ActivityWatchClient, EventShipper
from pulse_watcher.events import build_event

BUCKET = "aw-watcher-input_testhost"
ZERO = {"presses": 0, "clicks": 0, "deltaX": 0, "deltaY": 0, "scrollX": 0, "scrollY": 0}


class _Recorder(BaseHTTPRequestHandler):
    requests: ClassVar[list[tuple[str, str, object]]] = []
    status_by_path: ClassVar[dict[str, int]] = {}

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"null")
        _Recorder.requests.append(("POST", self.path, body))
        status = _Recorder.status_by_path.get(self.path, 200)
        payload = b'{"ok": true}' if status == 200 else b'{"status": "nok"}'
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args: object) -> None:  # silence request logging
        pass


@pytest.fixture()
def server():
    _Recorder.requests.clear()
    _Recorder.status_by_path.clear()
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Recorder)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield httpd
    httpd.shutdown()
    httpd.server_close()


def _client(httpd) -> ActivityWatchClient:
    port = httpd.server_address[1]
    return ActivityWatchClient(f"http://127.0.0.1:{port}", BUCKET, "testhost")


def test_bucket_created_with_stock_schema(server):
    assert _client(server).ensure_bucket() is True
    method, path, body = _Recorder.requests[-1]
    assert (method, path) == ("POST", f"/api/0/buckets/{BUCKET}")
    assert body == {"client": "omarchy-pulse", "type": "os.hid.input", "hostname": "testhost"}


def test_existing_bucket_counts_as_success(server):
    _Recorder.status_by_path[f"/api/0/buckets/{BUCKET}"] = 304
    assert _client(server).ensure_bucket() is True


def test_send_events_posts_bulk_list(server):
    client = _client(server)
    events = [build_event(1_700_000_400, {**ZERO, "presses": 5})]
    assert client.send_events(events) is True
    method, path, body = _Recorder.requests[-1]
    assert (method, path) == ("POST", f"/api/0/buckets/{BUCKET}/events")
    assert body == events
    assert body[0]["duration"] == 60.0
    assert body[0]["timestamp"].endswith("+00:00")
    assert body[0]["data"]["presses"] == 5


def test_unreachable_server_is_handled():
    # Port 1 on localhost: nothing listens there.
    client = ActivityWatchClient("http://127.0.0.1:1", BUCKET, "testhost", timeout_s=1.0)
    assert client.ensure_bucket() is False
    assert client.send_events([build_event(0, ZERO)]) is False


def test_shipper_retries_queue_until_success(server):
    events_path = f"/api/0/buckets/{BUCKET}/events"
    _Recorder.status_by_path[events_path] = 500
    shipper = EventShipper(_client(server))
    event = build_event(1_700_000_400, {**ZERO, "clicks": 2})

    shipper.ship([event])
    assert shipper.pending_count == 1

    _Recorder.status_by_path[events_path] = 200
    shipper.ship([])  # an empty flush must still retry the queue
    assert shipper.pending_count == 0
    sent_bodies = [body for _m, path, body in _Recorder.requests if path == events_path and isinstance(body, list)]
    assert sent_bodies[-1] == [event]


def test_shipper_drops_oldest_on_overflow(server):
    events_path = f"/api/0/buckets/{BUCKET}/events"
    _Recorder.status_by_path[events_path] = 500
    shipper = EventShipper(_client(server), max_pending=3)
    for minute in range(5):
        shipper.ship([build_event(minute * 60, ZERO)])
    assert shipper.pending_count == 3

    _Recorder.status_by_path[events_path] = 200
    shipper.ship([])
    sent_bodies = [body for _m, path, body in _Recorder.requests if path == events_path and isinstance(body, list)]
    shipped_minutes = [event["timestamp"] for event in sent_bodies[-1]]
    # minutes 0 and 60 were dropped as oldest
    assert len(shipped_minutes) == 3
    assert shipped_minutes[0] != build_event(0, ZERO)["timestamp"]
