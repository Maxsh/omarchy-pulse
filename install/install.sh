#!/usr/bin/env bash
# One-step install/update for omarchy-pulse:
#   1. the watcher's venv — built OUTSIDE the plugin folder, so nothing inside
#      an installed plugin changes at runtime (the plugin validator refuses
#      symlinks, and the shell hot-reloads on any file change under the
#      plugins directory)
#   2. systemd user units (ActivityWatch units only when the machine has none)
#   3. the bar widget — dev checkouts only; a git-managed install made with
#      `omarchy plugin add` is left alone so `omarchy plugin update` keeps
#      working
# Safe to re-run — an update is the same command after `git pull`.
#
# Usage: install.sh [--no-widget]
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/omarchy-pulse"
VENV="$DATA_DIR/venv"
SYSTEMD_DIR="${HOME}/.config/systemd/user"
INSTALL_WIDGET=1

for arg in "$@"; do
  case "$arg" in
    --no-widget) INSTALL_WIDGET=0 ;;
    *) echo "Unknown option: $arg (supported: --no-widget)" >&2; exit 1 ;;
  esac
done

# --- 1. watcher venv ---------------------------------------------------------
if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required to build the watcher (https://docs.astral.sh/uv/)." >&2
  exit 1
fi
echo "==> uv sync --locked (watcher venv at $VENV)"
# --locked: fail when uv.lock does not match pyproject.toml, so a reviewed
# commit can never silently install different dependency versions than the
# ones recorded in the lock (marketplace review #15375).
( cd "$REPO/watcher" && UV_PROJECT_ENVIRONMENT="$VENV" uv sync --locked --no-editable )

# --- 1b. version marker + standalone uninstall -------------------------------
mkdir -p "$DATA_DIR"
# The widget compares this file against its own manifest version, so the
# panel can hint at a stale watcher after `omarchy plugin update` (which
# refreshes the plugin folder but never the venv built outside it).
WATCHER_VERSION="$(sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$REPO/manifest.json" | head -1)"
if [ -n "$WATCHER_VERSION" ]; then
  printf '%s\n' "$WATCHER_VERSION" > "$DATA_DIR/version"
  echo "==> watcher version $WATCHER_VERSION recorded in $DATA_DIR/version"
fi
# Keep a working uninstall next to the venv: `omarchy plugin remove` deletes
# the plugin folder — this script included — which would leave the service
# and venv behind with no documented way to remove them.
install -m 755 "$REPO/install/uninstall.sh" "$DATA_DIR/uninstall.sh"
install -m 644 "$REPO/install/lib.sh" "$DATA_DIR/lib.sh"

# --- 2. systemd user units ---------------------------------------------------
mkdir -p "$SYSTEMD_DIR"

# "Present" covers every way the machine can already provide the unit:
# active, enabled, a leftover from a previous install, or a disabled fragment
# in any other unit directory systemd looks at. Our copies land in
# ~/.config/systemd/user, which shadows every other definition of the same
# name — so a unit systemd knows from anywhere must never be replaced, and
# one the user disabled must never be started behind their back
# (marketplace review #15375).
unit_active_or_present() {
  systemctl --user is-active --quiet "$1" 2>/dev/null && return 0
  systemctl --user is-enabled --quiet "$1" 2>/dev/null && return 0
  [ -f "$SYSTEMD_DIR/$1" ] && return 0
  systemctl --user list-unit-files --no-legend -- "$1" 2>/dev/null | grep -q .
}

# Point at the manual enable when the unit exists but runs neither now nor at
# boot (e.g. a disabled fragment from another unit directory): installing our
# copy would shadow it, and starting it would override the user's choice.
unit_left_off_note() {
  if ! systemctl --user is-active --quiet "$1" 2>/dev/null &&
     ! systemctl --user is-enabled --quiet "$1" 2>/dev/null; then
    echo "    It is neither active nor enabled — run this to start it:"
    echo "      systemctl --user enable --now $1"
  fi
}

# The watcher unit points at the external venv, so it survives the repo or
# plugin folder moving; keep in sync with watcher/systemd/pulse-watcher.service
# (that copy is for dev checkouts running from watcher/.venv).
# The unit carries a marker line so install and uninstall can tell it apart
# from a user's own pulse-watcher.service. The ownership rules live in lib.sh:
# only a unit we wrote — at our path and as the one systemd actually loads — is
# ever overwritten, stopped or removed.
# shellcheck source=lib.sh
. "$REPO/install/lib.sh"

ENABLE_UNITS=()
if reason=$(foreign_unit_reason); then
  echo "==> $reason — leaving it alone"
  echo "    (move it aside and re-run this script to let omarchy-pulse manage the unit)"
else
  echo "==> installing pulse-watcher.service (ExecStart -> $VENV)"
  cat > "$PULSE_UNIT" <<UNIT
$UNIT_MARKER
[Unit]
Description=omarchy-pulse input activity watcher
Documentation=https://github.com/Maxsh/omarchy-pulse
PartOf=graphical-session.target
After=graphical-session.target

[Service]
ExecStart=$VENV/bin/pulse-watcher
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=graphical-session.target
UNIT
  ENABLE_UNITS+=(pulse-watcher.service)
fi

# Terminal-focus watcher: names the program with focus inside the terminal
# window (herdr / tmux / plain pty) so Top apps is not all "foot". Same
# ownership rule as above: a unit we did not write is never touched.
if { [ -e "$TERM_UNIT" ] || [ -L "$TERM_UNIT" ]; } && ! unit_is_ours "$TERM_UNIT"; then
  echo "==> $TERM_UNIT was not written by omarchy-pulse — leaving it alone"
else
  echo "==> installing $TERM_UNIT_NAME (ExecStart -> $VENV)"
  cat > "$TERM_UNIT" <<UNIT
$UNIT_MARKER
[Unit]
Description=omarchy-pulse terminal focus watcher
Documentation=https://github.com/Maxsh/omarchy-pulse
PartOf=graphical-session.target
After=graphical-session.target

[Service]
ExecStart=$VENV/bin/pulse-term-watcher
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=graphical-session.target
UNIT
  ENABLE_UNITS+=($TERM_UNIT_NAME)
fi

# ActivityWatch server: only provide our unit when the machine has none yet.
if unit_active_or_present aw-server.service; then
  echo "==> aw-server.service already present — leaving it alone"
  unit_left_off_note aw-server.service
else
  echo "==> installing aw-server.service (bundled aw-server-rust)"
  cp "$REPO/install/aw-server.service" "$SYSTEMD_DIR/aw-server.service"
  ENABLE_UNITS+=(aw-server.service)
fi

# Window/AFK watcher: powers the Top apps section; install when missing.
if unit_active_or_present aw-awatcher.service; then
  echo "==> aw-awatcher.service already present — leaving it alone"
  unit_left_off_note aw-awatcher.service
else
  echo "==> installing aw-awatcher.service (window focus for Top apps)"
  cp "$REPO/install/aw-awatcher.service" "$SYSTEMD_DIR/aw-awatcher.service"
  ENABLE_UNITS+=(aw-awatcher.service)
fi

systemctl --user daemon-reload
if (( ${#ENABLE_UNITS[@]} )); then
  systemctl --user enable --now "${ENABLE_UNITS[@]}"
fi

# --- 3. the bar widget -------------------------------------------------------
if (( INSTALL_WIDGET )); then
  PLUGIN_DEST="${HOME}/.config/omarchy/plugins/maxsh.pulse"
  if [ -d "$PLUGIN_DEST/.git" ]; then
    echo "==> plugin is git-managed (omarchy plugin add) — leaving it alone"
    echo "    update it with: omarchy plugin update maxsh.pulse"
  else
    echo "==> installing the pulse bar widget"
    "$REPO/install/plugin.sh"
  fi
else
  echo "==> --no-widget: skipping the widget install"
fi

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
