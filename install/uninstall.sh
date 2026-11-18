#!/usr/bin/env bash
# Remove omarchy-pulse from this machine: the watcher service and its venv.
# ActivityWatch itself and everything it recorded are left untouched.
#
# Run this BEFORE `omarchy plugin remove maxsh.pulse` — the plugin folder may
# be the git checkout this script runs from.
set -euo pipefail

DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/omarchy-pulse"

VENV="$DATA_DIR/venv"
PULSE_UNIT="$HOME/.config/systemd/user/pulse-watcher.service"
UNIT_MARKER="# Managed by omarchy-pulse install.sh"

# True when the unit file at $1 was written by install.sh: it has our marker,
# or (installs from before the marker existed) it runs our venv binary.
unit_is_ours() {
  [ -f "$1" ] || return 1
  grep -qF "$UNIT_MARKER" "$1" || grep -qxF "ExecStart=$VENV/bin/pulse-watcher" "$1"
}

if [ -e "$PULSE_UNIT" ] && ! unit_is_ours "$PULSE_UNIT"; then
  echo "==> $PULSE_UNIT was not installed by omarchy-pulse — leaving the service alone"
else
  echo "==> stopping and removing pulse-watcher.service"
  systemctl --user disable --now pulse-watcher.service 2>/dev/null || true
  rm -f "$PULSE_UNIT"
  systemctl --user daemon-reload
fi

if [ -d "$DATA_DIR" ]; then
  echo "==> removing the watcher venv ($DATA_DIR)"
  rm -rf "$DATA_DIR"
fi

echo
echo "ActivityWatch and its recorded history were left untouched — they are"
echo "yours, and independent of this project."
PLUGIN_DIR="${HOME}/.config/omarchy/plugins/maxsh.pulse"
if [ -d "$PLUGIN_DIR" ]; then
  echo "Remove the bar widget with: omarchy plugin remove maxsh.pulse"
fi
