#!/usr/bin/env bash
# Remove omarchy-pulse from this machine: the watcher service and its venv.
# ActivityWatch itself and everything it recorded are left untouched.
#
# Run this BEFORE `omarchy plugin remove maxsh.pulse` — the plugin folder may
# be the git checkout this script runs from. install.sh also copies this
# script (with lib.sh) to the watcher data dir (~/.local/share/omarchy-pulse),
# so removal still works after `omarchy plugin remove` has deleted the plugin
# folder; that copy unlinks itself together with the data dir.
set -euo pipefail

DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/omarchy-pulse"

VENV="$DATA_DIR/venv"
SYSTEMD_DIR="$HOME/.config/systemd/user"
# shellcheck source=lib.sh
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

# Only stop, disable or delete a unit that positively belongs to omarchy-pulse
# (marker line in the regular file, and the unit systemd actually loads). A
# foreign unit that merely runs our watcher binary must not lose the venv
# under it: in that case nothing is removed and the user decides.
effective=$(systemctl --user show -p FragmentPath --value "$UNIT_NAME" 2>/dev/null || true)

runs_our_binary_anywhere() {
  unit_runs_our_binary "$PULSE_UNIT" && return 0
  if [ -n "$effective" ] && [ "$effective" != "$PULSE_UNIT" ]; then
    unit_runs_our_binary "$effective"
    return
  fi
  return 1
}

keep_venv=0
if reason=$(foreign_unit_reason); then
  echo "==> $reason — leaving the service alone"
  if runs_our_binary_anywhere; then
    keep_venv=1
    echo "    Nothing is removed: that service runs the watcher binary from the"
    echo "    venv below, which this script would delete. For a full uninstall,"
    echo "    remove or repoint that unit yourself, then re-run this script:"
    echo "      systemctl --user disable --now $UNIT_NAME"
    echo "      rm -f $PULSE_UNIT  # and the file it is loaded from, if different"
  fi
elif [ -e "$PULSE_UNIT" ]; then
  echo "==> stopping and removing $UNIT_NAME"
  systemctl --user disable --now "$UNIT_NAME" 2>/dev/null || true
  rm -f "$PULSE_UNIT"
  systemctl --user daemon-reload
else
  echo "==> no $UNIT_NAME installed by omarchy-pulse — nothing to stop"
fi

if [ "$keep_venv" = 1 ]; then
  echo "==> keeping the watcher venv ($DATA_DIR) — the service above runs from it"
elif [ -d "$DATA_DIR" ]; then
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
