#!/usr/bin/env bash
# Install (or refresh) the pulse bar widget into the Omarchy shell plugins dir.
# Copies rather than symlinks: the shell hot-reloads plugins via inotify on
# ~/.config/omarchy/plugins, and inotify does not follow symlinked directories.
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/../widget/pulse" && pwd)"
DEST="${HOME}/.config/omarchy/plugins/maxsh.pulse"

mkdir -p "$(dirname "$DEST")"
rm -rf "$DEST"
cp -r "$SRC" "$DEST"

echo "Installed: $SRC -> $DEST"
echo "If the widget does not appear, run: omarchy-shell shell rescanPlugins"
