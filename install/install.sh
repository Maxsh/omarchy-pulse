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
echo "==> uv sync (watcher venv at $VENV)"
( cd "$REPO/watcher" && UV_PROJECT_ENVIRONMENT="$VENV" uv sync --no-editable )

# --- 2. systemd user units ---------------------------------------------------
mkdir -p "$SYSTEMD_DIR"

unit_active_or_present() {
  systemctl --user is-active --quiet "$1" 2>/dev/null && return 0
  systemctl --user is-enabled --quiet "$1" 2>/dev/null && return 0
  [ -f "$SYSTEMD_DIR/$1" ]
}

# The watcher unit points at the external venv, so it survives the repo or
# plugin folder moving; keep in sync with watcher/systemd/pulse-watcher.service
# (that copy is for dev checkouts running from watcher/.venv).
echo "==> installing pulse-watcher.service (ExecStart -> $VENV)"
cat > "$SYSTEMD_DIR/pulse-watcher.service" <<UNIT
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
