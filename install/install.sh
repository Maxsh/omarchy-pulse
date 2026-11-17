#!/usr/bin/env bash
# One-step install/update for omarchy-pulse on this machine:
#   1. the watcher's venv (uv)
#   2. systemd user units, with ExecStart rewritten to this clone's path
#   3. the bar widget (see plugin.sh)
# Safe to re-run — an update is the same command after `git pull`.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SYSTEMD_DIR="${HOME}/.config/systemd/user"

# --- 1. watcher venv ---------------------------------------------------------
if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required to build the watcher (https://docs.astral.sh/uv/)." >&2
  exit 1
fi
echo "==> uv sync (watcher venv)"
(cd "$REPO/watcher" && uv sync)

# --- 2. systemd user units ---------------------------------------------------
mkdir -p "$SYSTEMD_DIR"

unit_active_or_present() {
  systemctl --user is-active --quiet "$1" 2>/dev/null && return 0
  systemctl --user is-enabled --quiet "$1" 2>/dev/null && return 0
  [ -f "$SYSTEMD_DIR/$1" ]
}

# The watcher unit is always (re)written: ExecStart is rewritten to this
# clone's location, so moving the repo needs one more run of this script.
echo "==> installing pulse-watcher.service (ExecStart -> $REPO)"
sed "s|%h/projects/omarchy-pulse|$REPO|" \
  "$REPO/watcher/systemd/pulse-watcher.service" > "$SYSTEMD_DIR/pulse-watcher.service"
ENABLE_UNITS=(pulse-watcher.service)

# ActivityWatch server: only provide our unit when the machine has none yet.
if unit_active_or_present aw-server.service; then
  echo "==> aw-server.service already present — leaving it alone"
else
  echo "==> installing aw-server.service (bundled aw-server-rust)"
  cp "$REPO/install/aw-server.service" "$SYSTEMD_DIR/aw-server.service"
  ENABLE_UNITS+=(aw-server.service)
fi

# Window/AFK watcher: powers the Top apps section; install when missing.
if unit_active_or_present aw-awatcher.service; then
  echo "==> aw-awatcher.service already present — leaving it alone"
else
  echo "==> installing aw-awatcher.service (window focus for Top apps)"
  cp "$REPO/install/aw-awatcher.service" "$SYSTEMD_DIR/aw-awatcher.service"
  ENABLE_UNITS+=(aw-awatcher.service)
fi

systemctl --user daemon-reload
systemctl --user enable --now "${ENABLE_UNITS[@]}"

# --- 3. the bar widget -------------------------------------------------------
echo "==> installing the pulse bar widget"
"$REPO/install/plugin.sh"

# --- 4. device access --------------------------------------------------------
if id -nG | grep -qw input; then
  echo "==> input group: ok"
else
  echo "NOTE: your user is not in the 'input' group — pulse-watcher cannot"
  echo "      read devices yet. Run:  sudo usermod -aG input \$USER"
  echo "      then log out and back in."
fi

echo
echo "Done. If the widget is not on the bar yet, add 'Pulse' (category Stats),"
echo "e.g.:  omarchy bar move maxsh.pulse --section right"
