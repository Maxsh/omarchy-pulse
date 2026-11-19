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

# Ownership record lives outside the plugins dir (the shell hot-reloads on any
# change in there). It is written only after a successful copy, and holds the
# destination path, so an existing DEST is replaced only when this script put
# it there. Anything else (a hand-made or modified plugin, a copy from an older
# install that predates the record) is moved to a backup, never deleted.
STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/omarchy-pulse"
RECORD="$STATE_DIR/plugin-install"

owned_by_us() {
  [ -d "$DEST" ] && [ ! -L "$DEST" ] && [ -f "$RECORD" ] && [ "$(cat "$RECORD")" = "$DEST" ]
}

mkdir -p "$(dirname "$DEST")" "$STATE_DIR/backups"
if [ -e "$DEST" ] || [ -L "$DEST" ]; then
  if owned_by_us; then
    rm -rf "$DEST"
  else
    BACKUP="$STATE_DIR/backups/maxsh.pulse-$(date +%Y%m%d-%H%M%S)"
    mv "$DEST" "$BACKUP"
    echo "Existing $DEST was not installed by this script — moved to $BACKUP"
  fi
fi
mkdir -p "$DEST"
cp "$REPO/manifest.json" "$REPO/BarWidget.qml" "$REPO/Panel.qml" "$REPO/PulseModel.js" "$DEST/"
cp -r "$REPO/i18n" "$DEST/i18n"
printf '%s\n' "$DEST" > "$RECORD"

echo "Installed: $REPO -> $DEST"
echo "If the widget does not appear, run: omarchy-shell shell rescanPlugins"
