"""pulse-term-watcher entry point: heartbeat the program focused inside the terminal."""

from __future__ import annotations

import logging
import signal
import socket
import sys
import threading
import time

from ..awclient import ActivityWatchClient
from .config import TermConfig, build_parser, load_config
from .events import BUCKET_TYPE, build_heartbeat
from .hypr import Hyprland, socket_dir
from .resolve import Resolver

log = logging.getLogger("pulse-term-watcher")


def _tick(cfg: TermConfig, hypr: Hyprland, resolver: Resolver, client: ActivityWatchClient) -> None:
    window = hypr.active_window()
    if window is None:
        return
    window_class, pid = window
    if window_class.lower() not in {name.lower() for name in cfg.terminals}:
        return
    resolution = resolver.resolve(pid)
    if resolution is None:
        log.debug("terminal %s focused, no inner app resolved", window_class)
        return
    event = build_heartbeat(time.time(), resolution.app, window_class, resolution.via)
    # On failure the bucket may have vanished (ActivityWatch restarted with a fresh DB).
    if not client.heartbeat(event, cfg.pulsetime_s) and client.ensure_bucket():
        client.heartbeat(event, cfg.pulsetime_s)
    log.debug("heartbeat %s via %s", resolution.app, resolution.via)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cfg = load_config(args, config_path=args.config)
    logging.basicConfig(
        level=logging.DEBUG if cfg.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )

    directory = socket_dir()
    if directory is None:
        log.error("not inside a Hyprland session (HYPRLAND_INSTANCE_SIGNATURE is unset)")
        return 1

    hostname = cfg.hostname or socket.gethostname()
    bucket_id = f"{cfg.bucket_prefix}_{hostname}"
    client = ActivityWatchClient(cfg.aw_url, bucket_id, hostname, bucket_type=BUCKET_TYPE)
    hypr = Hyprland(directory)
    resolver = Resolver()
    stop = threading.Event()
    wake = threading.Event()

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_args: stop.set())

    threading.Thread(target=hypr.listen, args=(wake, stop), daemon=True).start()

    while not stop.is_set() and not client.ensure_bucket():
        log.warning("ActivityWatch unreachable at %s; retrying", cfg.aw_url)
        if stop.wait(5.0):
            return 0

    log.info("watching terminal focus for bucket %s at %s", bucket_id, cfg.aw_url)
    while not stop.is_set():
        _tick(cfg, hypr, resolver, client)
        wake.wait(cfg.poll_s)
        wake.clear()
    log.info("shutting down")
    return 0


if __name__ == "__main__":
    sys.exit(main())
