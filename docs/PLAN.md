# omarchy-pulse — Implementation Plan (draft)

Version 0.2 · 2026-11-17 · Status: implementation — Phase 5 (v0.1 release)

## 1. Goal

Give an Omarchy user a live, local view of their day: how active they were, and how that activity splits between keyboard and mouse — as a bar widget plus a popup panel (today, per-app, last 7 days), one click away in the bar.

**Non-goals:** keylogging or any key-content capture; productivity scoring; cloud sync; screenshots; app usage tracking as a core feature (per-app stats are a Phase 4 bonus).

## 2. Decisions

| # | Decision | Choice | Rationale / rejected alternatives |
|---|----------|--------|-----------------------------------|
| D1 | Data backend | ActivityWatch (local server) | Solves storage, retention, and a web dashboard for free; simple local REST API. Rejected: custom SQLite (re-implements storage + dashboard, no reuse of community tooling). Can be revisited if AW feels heavy (~50–100 MB RAM). |
| D2 | Input source | evdev via `python-evdev` | Wayland/Hyprland blocks global input hooks; stock `aw-watcher-input` is pynput/X11-based and can't see input on Hyprland. evdev reads `/dev/input/event*` directly (requires `input` group). |
| D3 | Widget | Omarchy shell plugin (Quickshell/QML) | Native to the bar, theme-aware, hot-reloads, matches Omarchy UX (`KeyboardPanel`). Rejected: separate Qt app (heavier, not in the bar), terminal chart (less discoverable). |
| D4 | Widget ↔ AW | Direct HTTP from QML to `http://localhost:5600` | No helper process to run. Fallback: tiny Python helper printing JSON if QML's XHR gets in the way. |
| D5 | AFK/idle | Implicit: empty minutes are not emitted | Absence of an event means no input in that minute — enough for activity curves. An explicit AFK state (e.g. via hypridle) can be added later if "screen-on but idle" semantics are wanted. |
| D6 | Bucket schema | Stock-compatible: bucket id `aw-watcher-input_{hostname}`, type `os.hid.input`, data keys `presses`, `clicks`, `deltaX`, `deltaY`, `scrollX`, `scrollY` | Confirmed from aw-watcher-input/aw-watcher-afk sources (Q1 resolved). Deliberate deviation: per-minute events instead of 5s heartbeats — identical totals for AW tooling, ~12× fewer events, light payload for the widget. |
| D7 | Popup design | **Horizontal stacked bars**: today's percentages as rows on top; one stacked bar per day for the last 7 days (hover tooltip with exact keyboard/mouse/idle percentages); a total bar for the week; refresh action in the header | Superseded the original canvas-curves idea after the first live design pass — per-day bars answer "how did my split look each day" at a glance, and reuse the mini-bar visual language. |
| D8 | Values shown | **Relative only**: keyboard/mouse/idle as percentages of the session so far (first input minute → now); no absolute counts in bar or panel | Product direction from first field use: absolute click/press counts don't answer "how did my time split". Classification per minute by dominant input (presses vs clicks/scroll/movement). Session span instead of since-midnight so night sleep doesn't dilute the split. |
| D9 | Window source | The system's own window watcher: the `aw-awatcher.service` user unit runs `aw-awatcher` (Wayland-native, ships with activitywatch-bin), writing the stock `currentwindow` bucket | The popup joins input minutes onto its focus spans and reads only `data.app`. A custom app-only window watcher was built first, then dropped — it duplicated awatcher and double-wrote the shared bucket with different semantics (titles on/off). The widget auto-discovers any `currentwindow` bucket, so it also works with `aw-watcher-window` or future replacements. |
| D10 | Keyboard/mouse split | **Seconds, not counts** (2026-11-13): a device-ownership timeline (`timeline.py`) reconstructs per-second which device the hands were on. Constants from HCI research — Keystroke-Level Model (Card, Moran & Newell 1980; Kieras 2001, https://web.eecs.umich.edu/~kieras/docs/GOMS/KLM.pdf): homing H = 0.4 s credited to the device switched *to*; typing bursts end after ~2 s keyboard / ~1 s mouse silence plus a 1 s tail; keys within 0.3 s of a click or during a held button (Shift+drag, Ctrl+click) count as mouse; motion is real at ≥ 1 mm / 250 ms (kernel resolution, mice assumed 1000 DPI); autorepeat and held buttons are continuous keep-alives; rapid alternation (flips faster than H, e.g. WASD + aiming) is binned as `bothS` and split evenly for display. Event data gains additive keys `kbS`/`mouseS`/`bothS` (stock keys untouched); minutes flush only after gap+tail (`RESOLVE_S`) so boundary bursts resolve. Widget: percentages come from seconds; gaps > 180 s (AW AFK threshold) drop out of the span as "away"; duplicate minutes (retry/late flush) collapse or merge. The old dominant-count classification remains as fallback for count-only events. Review findings that motivated this: counts aren't comparable units, minute ties leaned keyboard, touchpad touch-down jumps and tap-to-click/two-finger scroll were miscounted. |
| D11 | Widget settings | **Inline `shell.json` entry** (2026-11-17): the bar host hands each widget its layout entry as `settings`, read via the base `setting()` API (the clock plugin is the reference). The widget honors `awUrl` and `pollSeconds`; `resolveAwUrl` validates the URL local-only (http(s) to `localhost` / `127.x` / `[::1]`, else the default) to keep plugin network access loopback-bound. The manifest's `settingsForm`/`schema` hooks are parsed by the shell but not yet consumed by any settings UI, so values are edited in `~/.config/omarchy/shell.json` (hot-reloads). Rejected: a bespoke in-panel editor (scope creep for two settings), a plugin-local JSON config (duplicates what shell.json already does). |

## 3. Architecture

```
        ┌──────────────────────────┐
        │   /dev/input/event*      │
        └────────────┬─────────────┘
                     ▼
┌────────────────────────────────────────┐
│ pulse-watcher (Python + evdev)         │
│ systemd user service · counts only     │
└──────────────────┬─────────────────────┘
                   ▼  per-minute counts (REST · localhost:5600)
┌────────────────────────────────────────┐
│ ActivityWatch                          │
│ storage · REST API · web dashboard     │
└──────────────────┬─────────────────────┘
                   ▼  HTTP/JSON, polled every 60 s and on panel open
┌────────────────────────────────────────┐
│ Omarchy shell widget (Quickshell/QML)  │
│ bar mini-bar · popup panel             │
└────────────────────────────────────────┘
```

Responsibilities:

- **pulse-watcher** — device discovery & classification (keyboard vs pointer), per-minute aggregation, idle/AFK derivation, resilient shipping to AW (retry + small queue), systemd user service.
- **ActivityWatch** — persistence, retention, REST API, web dashboard (used for deep dives; not modified by this project). Window focus (`currentwindow`) and AFK come from the system `aw-awatcher` watcher (D9), not from this project.
- **pulse widget** — polls the API, shapes the data (seconds → percentages, per-day spans, app join), renders the bar mini-bar and the panel; pure display, no storage.

Cadence: watcher flushes every 60 s; widget polls every 60 s (`pollSeconds` setting) and refetches the week on panel open.

## 4. Data model

One event per minute, in the `input` bucket:

```json
{
  "timestamp": "2026-11-12T13:37:00+00:00",
  "duration": 60.0,
  "data": { "presses": 214, "clicks": 31, "deltaX": 6120, "deltaY": 4180, "scrollX": 0, "scrollY": 12 }
}
```

- Keys match stock `aw-watcher-input` exactly (Q1 resolved), so ActivityWatch's own visualizations keep working.
- Minutes with zero input are not emitted — absence means idle (D5).
- Since D10 (2026-11-13) events also carry `kbS`, `mouseS`, `bothS` — device-ownership seconds per minute (additive keys; the stock keys above are never renamed).
- "Total activity" per interval = count of minutes with any input (or sum of normalized counts — decide in Phase 3 while tuning the visual).

## 5. Component specs

### 5.1 pulse-watcher (Python)

| Module | Responsibility |
|---|---|
| `devices.py` | Enumerate `/dev/input/event*` (own glob — `evdev.list_devices()` silently drops unreadable devices); classify via capabilities (letters/LED → keyboard, relative/absolute motion → pointer, gamepads & power buttons → ignored). Logs a fix hint when devices are unreadable (missing `input` group). Rescanned every minute for hotplug. |
| `reader.py` | One thread per device: raw evdev events → count records + timeline actions via `EventTranslator` (presses = physical presses only, autorepeat forwarded as keep-alive; touchpad deltas in mm via the device's resolution; touch-down resets the contact origin; short still touches synthesize tap-to-click; hi-res wheel ignored to avoid double counting). |
| `timeline.py` | Device-ownership timeline (D10): ordered input actions → per-minute keyboard/mouse/both seconds, with burst gaps/tails, KLM homing on device switches, click chords, a motion jitter filter, and rapid-alternation "both" detection. Drains once per minute on the main loop. |
| `counter.py` | Thread-safe per-minute bins with the stock keys plus the seconds keys; multi-device summing by construction; `resolve_s` delays completion until boundary bursts are resolved. |
| `events.py` | Minute bin → ActivityWatch event (ISO timestamp, duration 60 s). |
| `awclient.py` | Bucket creation (`os.hid.input`), bulk event POST, bounded retry queue (180 min) across AW outages/restarts. |
| `config.py` | Defaults < `~/.config/omarchy-pulse/config.toml` < CLI flags. |
| `__main__.py` | Wiring: minute-boundary flush loop, device rescan, signal handling, clean shutdown. |

Config file: `~/.config/omarchy-pulse/config.toml` (optional; CLI flags override).

Service: `watcher/systemd/pulse-watcher.service` (user unit): `Restart=on-failure`, starts after login; document co-start with AW.

### 5.2 pulse widget (QML)

| Piece | Behavior |
|---|---|
| Bar item | Stacked mini-bar — keyboard/mouse/idle as percentages of the session, one accent hue at three intensities (theme-safe); percentage tooltip; left click opens the panel, right click forces a refresh; fixed-width row. |
| Panel | Popup panel: header (title links to the ActivityWatch dashboard, `PanelActionButton` refresh), "Since %1" subtitle, today's percentage rows, **Top apps** tornado section (per-app share of active time, each bar split by the app's own keyboard/mouse ratio, hover tooltips, hidden-with-hint while no window bucket exists), "Last 7 days" stacked bars (localized day labels, `PanelToolTip` hover, today highlighted), weekly "Total" bar, error reporting, keyboard dismissal. |
| Data | `PulseModel.fetch(awUrl, daysBack)` — bucket discovery by type, event fetch capped with an explicit positive limit, per-day spans from per-minute seconds (`kbS`/`mouseS`/`bothS`; legacy count fallback), AFK-gap exclusion, duplicate-minute merge, `topApps` window join. The pure JS stays in `PulseModel.js` and runs under node (`widget/tests/pulse-model.test.js`). |
| Settings | Inline `shell.json` entry via the base `setting()` API (D11): `awUrl` (validated loopback-only by `PulseModel.resolveAwUrl`) and `pollSeconds` (min 5 s, default 60 s). The shell parses the manifest's `settingsForm`/`schema` but no settings UI consumes them yet — edit values in `~/.config/omarchy/shell.json`; it hot-reloads. |
| i18n | Plugin-local flat catalogs (`i18n/en.json`, `i18n/uk.json`) read via `Commons.Translations`; numbers via `Commons.I18n.formatNumber`. Key and placeholder parity enforced by `widget/tests/i18n.test.js`. |

## 6. Phases

### Phase 0 — Kickoff (done)
Repo, README, AGENTS.md, this plan.

### Phase 1 — watcher MVP — **done (2026-11-12)**
- Implemented: device discovery + classification; per-minute counter; AW client (create bucket + POST, retry queue); systemd user unit; TOML config + CLI; logging without key content; 27 unit/integration tests.
- **Acceptance:** met — live on this machine: 6 devices read (built-in keyboard, touchpad, mouse, hotkey pads), per-minute events visible in AW within ~60 s while typing/mousing (e.g. `presses=121` in one minute), watcher survives AW starting later via its retry queue.

### Phase 2 — bar widget MVP — **done (2026-11-12)**
- Shipped: `maxsh.pulse` bar widget — stacked mini-bar (keyboard/mouse/idle percentages of the session), percentage tooltip, summary popup with swatch rows; plugin-local i18n (en.json); panel IPC (`omarchy-shell maxsh.pulse toggle`); `install/plugin.sh`; `install/aw-server.service`.
- Verified live: data pipeline (watcher → AW → QML) with real values; JS analysis in an isolated quickshell run (28/4/68% over a 47-minute session); bar mini-bar and popup confirmed by screenshot after a clean shell restart.
- Field findings fixed: `evdev.list_devices()` hides unreadable devices; `qs.Commons` import semantics for third-party plugins (singletons need the qualified `Commons.X` form — bare `Style` fails even though it works for first-party plugins); imperative tooltip built before the i18n catalog loaded (made reactive); raw `%1` plural row (missing tn+arg).
- Note: the shell defers/loses hot reloads while the session is locked — always verify widget changes after `omarchy restart shell` on an unlocked session.

### Phase 3 — popup redesign — **done (2026-11-12)**
- Shipped: panel with header (title + `PanelActionButton` refresh), today's percentage rows, "Last 7 days" section with one stacked bar per day (localized day labels, hover `PanelToolTip` with exact percentages, today highlighted), "Total" section with the weekly aggregate bar, keyboard dismissal, error reporting.
- Data: `PulseModel.fetch(awUrl, daysBack)` — the bar's 60 s poll fetches 1 day; opening the panel (or the refresh button) fetches 7 days; per-day classification and session-window spans computed in `analyzeWeek`.
- Verified live by screenshot: 27/11/62% today, day bars (Fri–Thu), total bar; no QML errors after a clean restart.
- Field findings: Qt's 3-arg `Qt.formatDate(date, fmt, locale)` throws "incompatible arguments" in this Quickshell build — use `date.toLocaleDateString(Qt.locale(name), fmt)` on a plain `new Date()` receiver (calling locale formatting on a `property date` receiver fails the same way).

### Phase 4 — polish — **done (2026-11-17)**

- **Input-time attribution (D10, 2026-11-13):** replaced the per-minute dominant-count classification with a device-ownership timeline measuring keyboard/mouse/idle in seconds. Watcher: `timeline.py` (state machine + jitter filter + chord/both detection), translator rework (autorepeat keep-alives, touchpad resolution, tap-to-click, touch-down reset), resolve-margin flush, additive `kbS`/`mouseS`/`bothS` event keys. Widget: seconds-based percentages, AFK gap exclusion, duplicate-minute merge, legacy fallback. Tests: 28 watcher cases incl. the seven worked examples; `widget/tests/pulse-model.test.js` under node; CI in `.github/workflows/tests.yml`.
- **Per-app breakdown:** "Top apps" section in the popup — window-focus spans from the system awatcher bucket joined onto today's input minutes; top 5 + "other", share-of-active bar split by each app's own keyboard/mouse ratio, hover tooltips; live via the 60 s poll (self-heals once the window bucket exists); hidden-with-hint while it doesn't.
- **Widget polish (2026-11-17):** panel typography unified on Omarchy font tokens; the panel title opens the ActivityWatch dashboard; event fetches bounded with an explicit positive limit (aw-server-rust rejects the "no limit" sentinel); `slk` pinned-class app label fix.

### Phase 5 — release v0.1 (in progress)

- **Docs:** the README reflects the shipped widget (mini-bar, Top apps, seconds-based measurement); this plan updated (§1, §3, §5.2, D11, closed questions).
- **One-step install:** `install/install.sh` — `uv sync`, systemd units with `ExecStart` rewritten to the clone's path, `aw-server`/`aw-awatcher` units only when the machine has none (never clobber an existing ActivityWatch setup), widget install, `input`-group check; safe to re-run, so an update is `git pull` + the same command. Ships `install/aw-awatcher.service` so Top apps works out of the box.
- **i18n:** Ukrainian catalog (`i18n/uk.json`); key + placeholder parity against `en.json` enforced by `widget/tests/i18n.test.js` (CI).
- **Settings (Q3 → D11):** `awUrl` (validated loopback-only) and `pollSeconds` honored from the inline `shell.json` entry; documented in the README.
- **Packaging/legal:** MIT `LICENSE`; manifest descriptions now describe the time split. An AUR PKGBUILD is deliberately deferred — the install script covers it.
- **Screenshots:** bar + panel (`docs/img/`), linked from the README.
- **Release:** push `main`, delete merged feature branches, tag `v0.1.0`, GitHub release (as the `Maxsh` account, switch back after).
- **Acceptance:** fresh clone → `install/install.sh` → re-login → widget live within ~2 minutes of input; script re-run is a no-op; CI green (privacy schema test, model tests, i18n parity); README matches reality; tag + release exist.
- **After acceptance:** share on Omarchy community channels — deliberately the last step, only once everything above is confirmed.

## 7. Risks & mitigations

| Risk | Mitigation |
|---|---|
| `input` group grants read access to *all* input devices | Privacy invariant in AGENTS.md; count-only code path; test asserting event schema; code review discipline. |
| Device hotplug / suspend-resume breaks reads | Rescan on read error; `Restart=on-failure`; skip/merge minutes across clock jumps after resume. |
| AW API details differ (query params, auth) | Confirm against installed AW version in Phase 1; pin behavior; localhost-only. |
| QML Canvas perf | Repaint only on new data (60 s) and on view toggle; never on an animation timer. |
| Double counting with multiple keyboards/mice | Summing across devices is the intended semantic (an event is an event); document it. |
| activitywatch-bin autostart method varies (desktop entry vs user service) | **Resolved:** the AUR package ships no systemd unit for the Python server (only an `aw-server-rust` template under `/opt` and an XDG autostart for the tray) — `install/aw-server.service` provides a proper user unit. |

## 8. Open questions

1. ~~**Q1 — exact event `data` keys**~~ **Resolved 2026-11-12:** stock keys are `presses`, `clicks`, `deltaX`, `deltaY`, `scrollX`, `scrollY`; bucket `aw-watcher-input_{hostname}`, type `os.hid.input` (sources: aw-watcher-input `main.py`, aw-watcher-afk `listeners.py`).
2. ~~**Q2 — "total" curve definition**~~ **Resolved 2026-11-17:** the popup redesign dropped curves entirely (D7); "Total" is the weekly aggregate over the per-day session spans, in the same seconds-based split. Nothing left to define.
3. ~~**Q3 — Omarchy plugin settings API**~~ **Resolved 2026-11-17:** bar widgets receive their inline `shell.json` layout entry as `settings` and can persist via `bar.shell.updateEntryInline` (the clock plugin is the reference). The manifest's `settingsForm`/`schema` hooks are parsed by the shell but no settings UI consumes them yet — see D11.
4. ~~**Q4 — week view granularity**~~ **Resolved 2026-11-17:** one stacked bar per day answers "how did my split look each day" at a glance; finer bins would need scrolling without adding answers. Revisit only if a real use appears.
5. ~~**Q5 — repo name/visibility**~~ **Resolved 2026-11-17:** stays `Maxsh/omarchy-pulse`, public.
