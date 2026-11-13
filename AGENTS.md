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
   - `KeyboardPanel` sizes its card from the content root's `implicitHeight` — set it (`implicitHeight: contentColumn.implicitHeight`), or the card collapses and the content overflows below it. Note also: singleton access must be qualified (`Commons.Style`, not `Style`) in third-party plugins, and the shell defers plugin hot-reloads while the session is locked — verify changes with `omarchy restart shell` unlocked.
   - Qt date-formatting quirks in this build: the 3-arg `Qt.formatDate(date, fmt, locale)` throws "Passing incompatible arguments to C++ functions"; use `date.toLocaleDateString(Qt.locale(name), fmt)` on a plain `new Date()` receiver — calling it on a QML `property date` receiver fails the same way.
4. **Theme-aware, never hardcoded colors.** Use the palette exposed by `qs.Commons` — check a built-in plugin under `/usr/share/omarchy/shell/plugins/` for the exact API of the installed Omarchy version.
5. **Input-time attribution follows HCI research — verify it stays that way.** The keyboard/mouse/idle split is computed by the device-ownership timeline in `watcher/pulse_watcher/timeline.py`, whose constants come from published HCI motor-behavior results: the **Keystroke-Level Model** (Card, Moran & Newell 1980; operator times in Kieras 2001, <https://web.eecs.umich.edu/~kieras/docs/GOMS/KLM.pdf>: keystroke K ≈ 0.2 s, button B ≈ 0.1 s, point P ≈ 1.1 s, homing H = 0.4 s) and **typing-burst studies** (~2 s word pauses end a burst). Before changing classification or attribution code, re-check the implementation against those sources and the parameter table in docs/PLAN.md (decision D10) — the constants are research values, not ad-hoc guesses, and must not be silently retuned. Keep the module docstring citing the sources, and keep the worked examples in `watcher/tests/test_timeline.py` passing (they are the executable form of the model).

## Environment notes (this machine)

- Omarchy skill docs: `~/.agents/skills/omarchy/` — read `plugins.md` before touching the widget; `hyprland.md` for keybindings; `theming.md` for theme handling.
- Built-in plugins to copy patterns from: `/usr/share/omarchy/shell/plugins/` (read-only).
- Plugin code under `~/.config/omarchy/plugins/` hot-reloads on save; force with `omarchy-shell shell rescanPlugins` if a change doesn't apply.
- **Environment extras:** window and AFK buckets come from `aw-awatcher` (Wayland-native, ships with `activitywatch-bin`), supervised by the `aw-awatcher.service` user unit alongside `aw-server.service`; the tray client `aw-qt` is suppressed via `~/.config/autostart/aw-qt.desktop` (`Hidden=true`) since Omarchy has no system tray — don't re-enable it. Never write a second watcher into those buckets; read them instead. Widget changes must be verified with `omarchy restart shell` on an unlocked session; hot reload is unreliable here.
- **Git identity:** this repo lives under `~/projects`, which maps via `includeIf` to `~/.config/git/maxsh.gitconfig` (personal identity + `id_ed25519_personal` SSH key).
- **GitHub account:** the repo belongs to the `Maxsh` account, but this machine's default active `gh` account is `maksym-shaiev`. Switch with `gh auth switch -u Maxsh` for repo-management commands (creating the repo, releases, settings) and switch back afterward.

## Setup (Phase 1; adjust as code lands)

```bash
# watcher dependencies (uv-managed venv; no pacman python-evdev needed)
cd watcher && uv sync

# ActivityWatch (AUR)
omarchy pkg aur add activitywatch-bin

# the watcher needs raw input access
sudo usermod -aG input $USER   # re-login required

# start ActivityWatch, then verify its API
curl -s http://localhost:5600/api/0/buckets | head -c 400

# tests / linter / run (from watcher/)
uv run pytest
uv run ruff check .
uv run pulse-watcher --verbose
```

## Conventions

- **Python** (watcher): 3.11+, full type hints, threaded device readers + a simple main loop (asyncio was rejected as unnecessary for blocking evdev reads), `ruff` for lint+format, `pytest` for tests, `uv` for env and deps. Keep dependencies minimal: `evdev` + stdlib.
- **QML** (widget): match the style of Omarchy's built-in plugins (naming, imports, file layout). Run `qmllint` where available.
- Keep chart data-shaping (binning, series building) in small pure JS functions in the QML so they can be exercised by `qmltestrunner`.
- Commits: short imperative subjects; docs-only changes prefixed `docs:`.

## Testing

- Watcher: unit-test the aggregator with synthetic evdev events (per-minute buckets, AFK transitions, multi-device summing). Unit-test the timeline with synthetic action streams — the worked examples of docs/PLAN.md D10 are the test names in `watcher/tests/test_timeline.py`. Integration-test the AW client against a local HTTP stub — CI must not require a running ActivityWatch.
- Add a test asserting the watcher's emitted event schema contains only count/seconds fields (privacy rule #1).
- Widget: no automated UI tests planned; rely on `qmllint` + manual checks after hot-reload. Keep logic testable as described under Conventions — the pure model logic runs under node (`widget/tests/pulse-model.test.js`, also in CI).

## CI

- `.github/workflows/tests.yml` runs on push to main and on PRs: watcher lint + pytest (via `uv`), and the widget model tests under node. Keep it hermetic — no ActivityWatch, no devices.

## Do not

- Don't capture key content "temporarily for debugging".
- Don't add network access beyond ActivityWatch's localhost endpoints.
- Don't hardcode theme colors or edit packaged Omarchy components.
- Don't store raw input events to disk anywhere.

## References

- ActivityWatch REST API: https://docs.activitywatch.net/en/latest/api.html
- aw-watcher-input (bucket schema to stay compatible with): https://github.com/ActivityWatch/aw-watcher-input
- **Bucket schema (confirmed from source, 2026-11-12):** bucket id `aw-watcher-input_{hostname}`, type `os.hid.input`, event data keys `presses`, `clicks`, `deltaX`, `deltaY`, `scrollX`, `scrollY`. Never rename these keys — compatibility with ActivityWatch tooling depends on them. Since the input-time timeline (D10, 2026-11-13) the watcher also writes three **additive** keys — `kbS`, `mouseS`, `bothS` (device-ownership seconds per minute); they extend, never replace, the stock schema.
- Omarchy: https://omarchy.org/ — shell/plugin docs via the local skill (`~/.agents/skills/omarchy/`)
