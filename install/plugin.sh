#!/usr/bin/env bash
# Install (or refresh) the pulse bar widget into the Omarchy shell plugins dir.
# Copies rather than symlinks: the shell hot-reloads plugins via inotify on
# ~/.config/omarchy/plugins, and inotify does not follow symlinked directories.
# Only the plugin's own files are copied — the repo's watcher/, install/, docs/
# and tests/ stay out of the plugins directory. (The marketplace install path,
# `omarchy plugin add`, clones the whole repo instead; install.sh detects that
# and skips this script.)
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="${HOME}/.config/omarchy/plugins/maxsh.pulse"

if [[ "$REPO" == "$DEST" || "$REPO" == "$DEST/"* ]]; then
  echo "Running from the installed plugin folder — nothing to copy." >&2
  exit 0
fi

mkdir -p "$(dirname "$DEST")"
rm -rf "$DEST"
mkdir -p "$DEST"
cp "$REPO/manifest.json" "$REPO/BarWidget.qml" "$REPO/Panel.qml" "$REPO/PulseModel.js" "$DEST/"
cp -r "$REPO/i18n" "$DEST/i18n"

echo "Installed: $REPO -> $DEST"
echo "If the widget does not appear, run: omarchy-shell shell rescanPlugins"
