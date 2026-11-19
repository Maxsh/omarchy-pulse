#!/usr/bin/env bash
# Remove omarchy-pulse from this machine: the watcher service and its venv.
# ActivityWatch itself and everything it recorded are left untouched.
#
# Run this BEFORE `omarchy plugin remove maxsh.pulse` — the plugin folder may
# be the git checkout this script runs from.
set -euo pipefail

DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/omarchy-pulse"

VENV="$DATA_DIR/venv"
SYSTEMD_DIR="$HOME/.config/systemd/user"
# shellcheck source=lib.sh
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

# Only stop, disable or delete a unit that positively belongs to omarchy-pulse:
# both the file at our path and the unit systemd actually loads must be ours.
if reason=$(foreign_unit_reason); then
  echo "==> $reason — leaving the service alone"
elif [ -e "$PULSE_UNIT" ]; then
  echo "==> stopping and removing $UNIT_NAME"
  systemctl --user disable --now "$UNIT_NAME" 2>/dev/null || true
  rm -f "$PULSE_UNIT"
  systemctl --user daemon-reload
else
  echo "==> no $UNIT_NAME installed by omarchy-pulse — nothing to stop"
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
