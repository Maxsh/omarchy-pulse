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

# Safety net for the dev-install path: whatever occupies the destination is
# moved to a backup first, so nothing in an existing plugin folder is ever
# deleted. A folder counts as our previous copy only when BOTH an external
# record (~/.local/state/omarchy-pulse/plugin-install, kept outside the
# plugins dir because the shell hot-reloads on any change in there) and an
# .installed-by-omarchy-pulse marker inside the folder match — a stale record
# from an older install must not doom an unrelated widget directory.
STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/omarchy-pulse"
RECORD="$STATE_DIR/plugin-install"
OWN_TOKEN="installed by omarchy-pulse install/plugin.sh"
MARKER=".installed-by-omarchy-pulse"

owned_by_us() {
  [ -d "$DEST" ] && [ ! -L "$DEST" ] \
    && [ -f "$RECORD" ] && [ "$(cat "$RECORD")" = "$DEST" ] \
    && [ -f "$DEST/$MARKER" ] && grep -qxF "$OWN_TOKEN" "$DEST/$MARKER"
}

mkdir -p "$(dirname "$DEST")" "$STATE_DIR/backups"
if [ -e "$DEST" ] || [ -L "$DEST" ]; then
  if owned_by_us; then
    echo "==> refreshing the widget (the previous copy is kept as a backup)"
  else
    echo "==> existing $DEST was not provably installed by this script"
  fi
  BACKUP="$STATE_DIR/backups/maxsh.pulse-$(date +%Y%m%d-%H%M%S)-$$"
  mv "$DEST" "$BACKUP"
  echo "    previous copy moved to $BACKUP — nothing was deleted"
fi
mkdir -p "$DEST"
cp "$REPO/manifest.json" "$REPO/BarWidget.qml" "$REPO/Panel.qml" "$REPO/PulseModel.js" "$DEST/"
cp -r "$REPO/i18n" "$DEST/i18n"
printf '%s\n' "$DEST" > "$RECORD"
printf '%s\n' "$OWN_TOKEN" > "$DEST/$MARKER"

echo "Installed: $REPO -> $DEST"
echo "If the widget does not appear, run: omarchy-shell shell rescanPlugins"
