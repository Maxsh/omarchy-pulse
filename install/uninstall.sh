#!/usr/bin/env bash
# Remove omarchy-pulse from this machine: the watcher service and its venv.
# ActivityWatch itself and everything it recorded are left untouched.
#
# Run this BEFORE `omarchy plugin remove maxsh.pulse` — the plugin folder may
# be the git checkout this script runs from.
set -euo pipefail

DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/omarchy-pulse"

echo "==> stopping and removing pulse-watcher.service"
systemctl --user disable --now pulse-watcher.service 2>/dev/null || true
rm -f "$HOME/.config/systemd/user/pulse-watcher.service"
systemctl --user daemon-reload

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
