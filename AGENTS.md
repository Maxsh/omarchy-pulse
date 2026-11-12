# AGENTS.md

Guidance for AI coding agents (and human contributors) working in this repository.

## What this project is

**omarchy-pulse** tracks keyboard and mouse activity on Omarchy (Hyprland/Wayland) and shows it as day/week curves — total, keyboard, mouse — in an Omarchy shell bar widget.

- Data backend: [ActivityWatch](https://activitywatch.net/) (local REST API, storage, web dashboard).
- Input source: a custom evdev watcher, because Wayland blocks global input hooks.
- Frontend: an Omarchy shell plugin (Quickshell/QML).

**Current status: design phase.** The draft plan — decisions, component specs, phases, acceptance criteria — lives in [`docs/PLAN.md`](docs/PLAN.md). Read it before writing code, and update it when a decision changes.

## Repository layout (target state)

```
watcher/pulse_watcher/   Python package: device discovery, per-minute aggregation, ActivityWatch client
watcher/systemd/         pulse-watcher.service (systemd user unit)
widget/                  Omarchy shell plugin source (QML); installed into ~/.config/omarchy/plugins/
install/                 install/update scripts (Phase 2+)
docs/                    plan and design notes
```

## Golden rules

1. **Privacy invariant: counts, never content.** The watcher may count events per device class and derive idle time. It must never record, log, store, or transmit keycodes, keysyms, characters, or anything that identifies *which* key was pressed. This holds during debugging too: no raw evdev dumps, no verbose key logging. Prefer unit tests that assert emitted events contain only counts.
2. **Never edit `/usr/share/omarchy/`.** It is owned by the omarchy package and overwritten on update. Reading it is safe and encouraged (great source of patterns). User customization lives in `~/.config/`.
3. **The widget is an Omarchy shell plugin** and must follow Omarchy's plugin rules:
   - Treat any text not produced by the plugin itself as untrusted: bind it only to `Text { textFormat: Text.PlainText }` sinks. ActivityWatch API responses count as untrusted.
   - Keep network access explicit and local-only (`http://localhost:5600`), with timeouts and response-size caps.
   - Motion via Omarchy kit (`qs.Ui` components) or `Style.duration(ms)` / `Style.easeOut` from `qs.Commons`; no bare durations, no ease-in, ≤300 ms.
   - Ship strings as flat JSON catalogs in `i18n/` read via `Commons.Translations`; format numbers with `Commons.I18n.formatNumber`. English-only at first is fine.
4. **Theme-aware, never hardcoded colors.** Use the palette exposed by `qs.Commons` — check a built-in plugin under `/usr/share/omarchy/shell/plugins/` for the exact API of the installed Omarchy version.

## Environment notes (this machine)

- Omarchy skill docs: `~/.agents/skills/omarchy/` — read `plugins.md` before touching the widget; `hyprland.md` for keybindings; `theming.md` for theme handling.
- Built-in plugins to copy patterns from: `/usr/share/omarchy/shell/plugins/` (read-only).
- Plugin code under `~/.config/omarchy/plugins/` hot-reloads on save; force with `omarchy-shell shell rescanPlugins` if a change doesn't apply.
- For development, the install script will symlink `widget/pulse` into `~/.config/omarchy/plugins/<user>.pulse`. If hot-reload doesn't follow the symlink, copy instead and keep the repo copy canonical.
- **Git identity:** this repo lives under `~/projects`, which maps via `includeIf` to `~/.config/git/maxsh.gitconfig` (personal identity + `id_ed25519_personal` SSH key).
- **GitHub account:** the repo belongs to the `Maxsh` account, but this machine's default active `gh` account is `maksym-shaiev`. Switch with `gh auth switch -u Maxsh` for repo-management commands (creating the repo, releases, settings) and switch back afterward.

## Setup (Phase 1; adjust as code lands)

```bash
# dependencies
omarchy pkg add python-evdev
omarchy pkg aur add activitywatch-bin

# the watcher needs raw input access
sudo usermod -aG input $USER   # re-login required

# start ActivityWatch, then verify its API
curl -s http://localhost:5600/api/0/buckets | head -c 400

# run the watcher manually (from watcher/)
python -m pulse_watcher --verbose
```

## Conventions

- **Python** (watcher): 3.11+, full type hints, `asyncio` event loop, `ruff` for lint+format, `pytest` for tests. Keep dependencies minimal: `evdev` + stdlib.
- **QML** (widget): match the style of Omarchy's built-in plugins (naming, imports, file layout). Run `qmllint` where available.
- Keep chart data-shaping (binning, series building) in small pure JS functions in the QML so they can be exercised by `qmltestrunner`.
- Commits: short imperative subjects; docs-only changes prefixed `docs:`.

## Testing

- Watcher: unit-test the aggregator with synthetic evdev events (per-minute buckets, AFK transitions, multi-device summing). Integration-test the AW client against a local HTTP stub — CI must not require a running ActivityWatch.
- Add a test asserting the watcher's emitted event schema contains only count/idle fields (privacy rule #1).
- Widget: no automated UI tests planned; rely on `qmllint` + manual checks after hot-reload. Keep logic testable as described under Conventions.

## Do not

- Don't capture key content "temporarily for debugging".
- Don't add network access beyond ActivityWatch's localhost endpoints.
- Don't hardcode theme colors or edit packaged Omarchy components.
- Don't store raw input events to disk anywhere.

## References

- ActivityWatch REST API: https://docs.activitywatch.net/en/latest/api.html
- aw-watcher-input (bucket schema to stay compatible with): https://github.com/ActivityWatch/aw-watcher-input
- Omarchy: https://omarchy.org/ — shell/plugin docs via the local skill (`~/.agents/skills/omarchy/`)
