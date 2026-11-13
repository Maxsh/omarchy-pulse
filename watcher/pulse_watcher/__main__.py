"""pulse-watcher entry point: read input devices, flush per-minute counts to ActivityWatch."""

from __future__ import annotations

import logging
import signal
import socket
import sys
import threading
import time

from .awclient import ActivityWatchClient, EventShipper
from .config import build_parser, load_config
from .counter import MinuteCounter
from .devices import InputDeviceInfo, discover
from .events import build_event
from .reader import DeviceReader
from .timeline import RESOLVE_S, Timeline

log = logging.getLogger("pulse-watcher")

_STARTUP_RETRIES = 3
_STARTUP_RETRY_DELAY_S = 2.0
_MIN_SLEEP_S = 0.5
_MAX_SLEEP_S = 65.0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cfg = load_config(args, config_path=args.config)
    logging.basicConfig(
        level=logging.DEBUG if cfg.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )

    hostname = cfg.hostname or socket.gethostname()
    bucket_id = f"{cfg.bucket_prefix}_{hostname}"
    counter = MinuteCounter(resolve_s=RESOLVE_S)
    timeline = Timeline(counter)
    client = ActivityWatchClient(cfg.aw_url, bucket_id, hostname)
    shipper = EventShipper(client)
    stop = threading.Event()
    readers: dict[str, DeviceReader] = {}
    readers_lock = threading.Lock()

    def on_death(reader: DeviceReader) -> None:
        with readers_lock:
            readers.pop(reader.info.path, None)

    def spawn(info: InputDeviceInfo) -> None:
        reader = DeviceReader(info, counter, timeline, on_death=on_death)
        with readers_lock:
            readers[info.path] = reader
        reader.start()

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_args: stop.set())

    for info in discover(cfg.exclude):
        spawn(info)
    if not readers:
        log.warning("no readable input devices yet; rescanning every minute")

    for attempt in range(1, _STARTUP_RETRIES + 1):
        if client.ensure_bucket():
            break
        if stop.wait(_STARTUP_RETRY_DELAY_S):
            return 0
        log.debug("bucket creation retry %d/%d", attempt, _STARTUP_RETRIES)

    log.info("watching input for bucket %s at %s", bucket_id, cfg.aw_url)

    # A minute flushes only once its bursts are fully resolved: an input pause
    # of up to gap + tail can still extend a burst into the finished minute,
    # so the effective offset is at least RESOLVE_S plus a small margin.
    flush_offset = max(cfg.poll_offset_s, RESOLVE_S + 0.5)

    while not stop.is_set():
        now = time.time()
        delay = 60.0 - (now % 60.0) + flush_offset
        delay = min(max(delay, _MIN_SLEEP_S), _MAX_SLEEP_S)
        if stop.wait(delay):
            break

        now = time.time()
        timeline.drain()  # process queued actions in timestamp order
        timeline.close_stale(now)  # end bursts that simply stopped
        completed = counter.take_completed(now)
        shipper.ship([build_event(minute_ts, data) for minute_ts, data in completed])
        if shipper.pending_count:
            log.debug("%d minute(s) still queued", shipper.pending_count)

        for info in discover(cfg.exclude):
            with readers_lock:
                known = info.path in readers
            if not known:
                log.info("new device: %s [%s] at %s", info.name, info.kind.value, info.path)
                spawn(info)

    log.info("shutting down")
    timeline.drain()
    timeline.close_stale(time.time())
    shipper.ship(
        [build_event(minute_ts, data) for minute_ts, data in counter.take_completed(time.time())]
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
