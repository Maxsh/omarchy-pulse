# Changelog

## 0.1.3 — 2026-11-21

Fixes for the three findings that blocked the verification round for
`a2a91bb` ([omarchy-plugin-marketplace#15375](https://github.com/omacom/omarchy-plugin-marketplace/issues/15375)):

- The watcher's ActivityWatch client no longer honors session proxy settings:
  requests to the loopback-only endpoint go through an opener with proxy
  handling disabled, so `http_proxy`/`https_proxy` without a localhost
  exception can no longer route per-minute input counts and the hostname to
  a proxy. A test pins this by pointing the proxy environment at a dead port
  and asserting delivery still succeeds.
- The watcher build is reproducible: `install.sh` runs `uv sync --locked`
  (fails instead of silently installing when the lock does not match
  `pyproject.toml`), and `pyproject.toml` constrains the build backend via
  `[tool.uv] build-constraint-dependencies` (`hatchling==1.33.0`), so the
  isolated build environment no longer floats between runs of the same
  commit.
- `install.sh` treats an ActivityWatch unit as present when systemd knows it
  from *any* unit directory — active, enabled or disabled — not just
  `~/.config/systemd/user`. Our copies can no longer shadow another
  definition of the same name, and a unit that is neither active nor enabled
  is reported with its `systemctl --user enable --now` command instead of
  being started behind the user's back.

## 0.1.2 — 2026-11-19

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
- The panel shows a hint when the plugin folder is newer than the watcher
  venv — `install.sh` records the watcher version it built in
  `~/.local/share/omarchy-pulse/version` and the widget compares it with its
  own manifest, so `omarchy plugin update` without a following `install.sh`
  no longer goes unnoticed. A missing version file never triggers the hint.
- `install.sh` copies `uninstall.sh` (with `lib.sh`) next to the venv, so
  removal still works after `omarchy plugin remove` deleted the plugin
  folder: `~/.local/share/omarchy-pulse/uninstall.sh`.

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
