"""Normalize a process/agent name into the label stored in the bucket.

Only a short, plain command name survives: the basename of argv[0] (or comm),
lower-cased, with a tiny alias map. Anything that does not look like a command
name is rejected rather than stored.
"""

from __future__ import annotations

import re

MAX_NAME_LEN = 32

_SAFE = re.compile(r"^[a-z0-9][a-z0-9._+-]*$")

ALIASES = {
    "vim": "nvim",
    "vi": "nvim",
    "view": "nvim",
    "bash": "shell",
    "zsh": "shell",
    "fish": "shell",
    "sh": "shell",
    "dash": "shell",
    "nu": "shell",
}


def normalize(raw: object) -> str | None:
    """Return the stored label for a process or agent name, or None if unusable."""
    if not isinstance(raw, str):
        return None
    name = raw.strip().rsplit("/", 1)[-1].lower().removesuffix(".exe")
    name = name.lstrip("-")  # login shells are spelled "-bash"
    if not name or len(name) > MAX_NAME_LEN or not _SAFE.match(name):
        return None
    return ALIASES.get(name, name)
