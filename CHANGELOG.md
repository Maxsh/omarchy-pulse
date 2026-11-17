# Changelog

## 0.1.1 — 2026-11-17

- The Omarchy plugin lives at the repository root now, so
  `omarchy plugin add https://github.com/Maxsh/omarchy-pulse` works directly —
  the marketplace (and `omarchy plugin add`) clones the whole repo and expects
  `manifest.json` in its root.
- `install.sh` builds the watcher venv *outside* the plugin folder
  (`~/.local/share/omarchy-pulse/venv`, `uv sync --no-editable`), so nothing
  inside an installed plugin changes at runtime: no symlinks (the validator
  refuses them) and no hot-reload churn from the shell's inotify watcher.
- `install.sh` detects a git-managed (marketplace) plugin install and leaves
  it alone — re-run it after `omarchy plugin update` to rebuild the watcher.
  New `--no-widget` flag installs only the watcher.
- New `install/uninstall.sh`: stops and removes the watcher service and venv.
  ActivityWatch and its recorded data are untouched.
- The widget's "no input data" hint now points at the watcher install command.
- Top apps: `appLabels` setting for display-name overrides, and a generic
  reverse-DNS tail rule (`com.slk.Tui` → `slk` without any override).

## 0.1.0 — 2026-11-17

First release: evdev watcher with HCI-based input-time attribution
(Keystroke-Level Model constants), Omarchy bar widget and panel — today's
keyboard/mouse/idle split, per-app Top apps, last 7 days, weekly total —
English and Ukrainian, one-step install, privacy-first (counts and seconds,
never key content).
