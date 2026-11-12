"""Configuration: defaults < TOML file < CLI flags."""

from __future__ import annotations

import argparse
import dataclasses
import pathlib
import tomllib

DEFAULT_CONFIG_PATH = pathlib.Path("~/.config/omarchy-pulse/config.toml").expanduser()


@dataclasses.dataclass(slots=True)
class Config:
    aw_url: str = "http://localhost:5600"
    bucket_prefix: str = "aw-watcher-input"
    hostname: str = ""  # empty -> socket.gethostname()
    exclude: tuple[str, ...] = ()
    verbose: bool = False
    poll_offset_s: float = 2.0  # seconds after a minute boundary to flush


def _load_toml_overrides(path: pathlib.Path) -> dict:
    try:
        with path.open("rb") as fh:
            return tomllib.load(fh)
    except FileNotFoundError:
        return {}
    except tomllib.TOMLDecodeError as exc:
        raise SystemExit(f"Invalid config file {path}: {exc}") from exc


def load_config(
    cli_args: argparse.Namespace | None = None, config_path: str | None = None
) -> Config:
    cfg = Config()
    path = pathlib.Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    overrides = _load_toml_overrides(path)
    known = {field.name for field in dataclasses.fields(Config)}
    for key, value in overrides.items():
        if key not in known:
            raise SystemExit(f"Unknown config key {key!r} in {path}")
        if isinstance(getattr(cfg, key), tuple):
            value = tuple(value)
        setattr(cfg, key, value)
    if cli_args is not None:
        for key in known:
            cli_value = getattr(cli_args, key, None)
            if cli_value is None:
                continue
            if isinstance(getattr(cfg, key), tuple):
                cli_value = tuple(cli_value)
            setattr(cfg, key, cli_value)
    return cfg


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pulse-watcher",
        description="Count keyboard/mouse input per minute and ship it to ActivityWatch.",
    )
    parser.add_argument("--config", help=f"Config file path (default: {DEFAULT_CONFIG_PATH})")
    parser.add_argument("--aw-url", help="ActivityWatch base URL (default: http://localhost:5600)")
    parser.add_argument("--bucket-prefix", help="Bucket id prefix (default: aw-watcher-input)")
    parser.add_argument("--hostname", help="Hostname for the bucket id (default: system hostname)")
    parser.add_argument(
        "--exclude",
        action="append",
        help="Skip devices whose name contains this substring (repeatable)",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Debug logging")
    return parser
