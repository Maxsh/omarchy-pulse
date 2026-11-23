#!/usr/bin/env bash
# Shared helpers for install.sh and uninstall.sh (sourced, never run directly).
# The caller must set VENV (the watcher venv dir) and SYSTEMD_DIR (user unit dir).

UNIT_NAME="pulse-watcher.service"
PULSE_UNIT="$SYSTEMD_DIR/$UNIT_NAME"
UNIT_MARKER="# Managed by omarchy-pulse install.sh"

# The terminal-focus watcher unit. Unlike pulse-watcher.service it needs no
# `input` group; the same marker line is the only proof of ownership.
TERM_UNIT_NAME="pulse-term-watcher.service"
TERM_UNIT="$SYSTEMD_DIR/$TERM_UNIT_NAME"

# True when the unit file at $1 is a regular file (not a symlink, e.g. into a
# dotfiles repo) written by install.sh: it carries our marker line. Nothing
# else counts as ownership — an ExecStart pointing at our venv proves
# nothing, a separately configured unit may launch the same watcher binary.
unit_is_ours() {
  [ -f "$1" ] && [ ! -L "$1" ] && grep -qF "$UNIT_MARKER" "$1"
}

# True when the unit file at $1 (symlinks followed read-only) runs the watcher
# binary from our venv without being provably ours: a leftover from an
# install older than the marker, or a custom unit reusing the binary. Never
# treated as ownership; scripts use it only to warn and to keep the venv
# alive on uninstall.
unit_runs_our_binary() {
  { [ -e "$1" ] || [ -L "$1" ]; } && grep -qF "ExecStart=$VENV/bin/pulse-watcher" "$1"
}

# Positive ownership check for pulse-watcher.service. Prints a reason and
# returns 0 when the unit is NOT ours and must not be overwritten, stopped,
# disabled or deleted; returns 1 when it is ours or does not exist yet.
# Checks both our target path and the file systemd actually loads (it may
# come from another unit directory, e.g. /etc/systemd/user).
foreign_unit_reason() {
  local effective note
  if [ -e "$PULSE_UNIT" ] || [ -L "$PULSE_UNIT" ]; then
    if ! unit_is_ours "$PULSE_UNIT"; then
      note=""
      if unit_runs_our_binary "$PULSE_UNIT"; then
        note=" (it runs the omarchy-pulse watcher binary but carries no omarchy-pulse marker)"
      fi
      echo "$PULSE_UNIT was not written by omarchy-pulse$note"
      return 0
    fi
  fi
  effective=$(systemctl --user show -p FragmentPath --value "$UNIT_NAME" 2>/dev/null || true)
  if [ -n "$effective" ] && [ "$effective" != "$PULSE_UNIT" ] && ! unit_is_ours "$effective"; then
    note=""
    if unit_runs_our_binary "$effective"; then
      note=" (it runs the omarchy-pulse watcher binary but carries no omarchy-pulse marker)"
    fi
    echo "$UNIT_NAME is loaded from $effective, not installed by omarchy-pulse$note"
    return 0
  fi
  return 1
}
