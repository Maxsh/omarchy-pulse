# Changelog

## Unreleased

- `install.sh` no longer overwrites a `pulse-watcher.service` it did not
  write, and `uninstall.sh` stops, disables or deletes one only with positive
  proof of ownership: the `# Managed by omarchy-pulse install.sh` marker in
  the regular unit file at the expected path, and — for anything beyond
  writing it — the unit systemd actually loads (`FragmentPath`; it may come
  from another unit directory). A matching `ExecStart` alone proves nothing,
  so a separately configured unit that launches the same watcher binary is
  left untouched, and uninstall keeps the venv that such a unit runs from
  instead of breaking it. The shared checks live in the new `install/lib.sh`.
- The ActivityWatch client reads at most 2000 bytes of any response (success
  or HTTP error) instead of loading the whole body before truncating it, so an
  oversized response can no longer exhaust the watcher's memory.
- `install/plugin.sh` (dev install) never deletes an existing plugin folder:
  whatever occupies the destination is first moved to
  `~/.local/state/omarchy-pulse/backups/`. A folder is treated as our
  previous copy only when both an external record
  (`~/.local/state/omarchy-pulse/plugin-install`) and an
  `.installed-by-omarchy-pulse` marker inside the folder match, so a stale
  record from an older install cannot doom an unrelated widget directory.

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
