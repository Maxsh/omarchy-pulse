"""Configuration for pulse-term-watcher: defaults < TOML file < CLI flags."""

from __future__ import annotations

import argparse
import dataclasses
import pathlib

from ..config import _load_toml_overrides

DEFAULT_CONFIG_PATH = pathlib.Path("~/.config/omarchy-pulse/term.toml").expanduser()

#: Window classes treated as terminal emulators (matched case-insensitively).
DEFAULT_TERMINALS = (
    "foot",
    "footclient",
    "kitty",
    "alacritty",
    "com.mitchellh.ghostty",
    "org.wezfurlong.wezterm",
    "xterm",
)


@dataclasses.dataclass(slots=True)
class TermConfig:
    aw_url: str = "http://localhost:5600"
    bucket_prefix: str = "aw-watcher-term"
    hostname: str = ""  # empty -> socket.gethostname()
    terminals: tuple[str, ...] = DEFAULT_TERMINALS
    poll_s: float = 2.0  # re-check interval; focus events wake the loop sooner
    pulsetime_s: float = 6.0  # heartbeats closer than this merge into one event
    verbose: bool = False


def load_config(
    cli_args: argparse.Namespace | None = None, config_path: str | None = None
) -> TermConfig:
    cfg = TermConfig()
    path = pathlib.Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    overrides = _load_toml_overrides(path)
    known = {field.name for field in dataclasses.fields(TermConfig)}
    for key, value in overrides.items():
        if key not in known:
            raise SystemExit(f"Unknown config key {key!r} in {path}")
        if isinstance(getattr(cfg, key), tuple):
            value = tuple(value)
        setattr(cfg, key, value)
    if cli_args is not None:
        for key in known:
            cli_value = getattr(cli_args, key, None)
            if cli_value is not None:
                setattr(cfg, key, cli_value)
    return cfg


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pulse-term-watcher",
        description="Report which program has focus inside the focused terminal to ActivityWatch.",
    )
    parser.add_argument("--config", help=f"Config file path (default: {DEFAULT_CONFIG_PATH})")
    parser.add_argument("--aw-url", help="ActivityWatch base URL (default: http://localhost:5600)")
    parser.add_argument("--hostname", help="Hostname for the bucket id (default: system hostname)")
    parser.add_argument("-v", "--verbose", action="store_true", default=None, help="Debug logging")
    return parser
