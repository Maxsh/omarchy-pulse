# omarchy-pulse — Implementation Plan (draft)

Version 0.1 · 2026-11-12 · Status: design phase

## 1. Goal

Give an Omarchy user a live, local view of their day: how active they were, and how that activity splits between keyboard and mouse — as curves for the current day or week, one click away in the bar.

**Non-goals:** keylogging or any key-content capture; productivity scoring; cloud sync; screenshots; app usage tracking as a core feature (per-app stats are a Phase 4 bonus).

## 2. Decisions

| # | Decision | Choice | Rationale / rejected alternatives |
|---|----------|--------|-----------------------------------|
| D1 | Data backend | ActivityWatch (local server) | Solves storage, retention, and a web dashboard for free; simple local REST API. Rejected: custom SQLite (re-implements storage + dashboard, no reuse of community tooling). Can be revisited if AW feels heavy (~50–100 MB RAM). |
| D2 | Input source | evdev via `python-evdev` | Wayland/Hyprland blocks global input hooks; stock `aw-watcher-input` is pynput/X11-based and can't see input on Hyprland. evdev reads `/dev/input/event*` directly (requires `input` group). |
| D3 | Widget | Omarchy shell plugin (Quickshell/QML) | Native to the bar, theme-aware, hot-reloads, matches Omarchy UX (`KeyboardPanel`). Rejected: separate Qt app (heavier, not in the bar), terminal chart (less discoverable). |
| D4 | Widget ↔ AW | Direct HTTP from QML to `http://localhost:5600` | No helper process to run. Fallback: tiny Python helper printing JSON if QML's XHR gets in the way. |
| D5 | AFK/idle | Derived inside the watcher from the last-seen input event | The watcher already sees every event; no extra daemon needed. Used to mark minutes as active/idle. |
| D6 | Bucket naming | Reuse the stock schema: bucket id `aw-watcher-input_{hostname}`, type `input` | Keeps compatibility with ActivityWatch's built-in queries/visualizations. Exact event `data` keys to be confirmed from aw-watcher-input source before coding (open question Q1). |
| D7 | Chart granularity | Day = 24 hourly bins; Week = 7 daily bins | Readable at panel size; weekly hourly (168 points) only if it looks good later. |

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
                   ▼  HTTP/JSON, polled every 30–60 s
┌────────────────────────────────────────┐
│ Omarchy shell widget (Quickshell/QML)  │
│ bar text · day/week chart popup        │
└────────────────────────────────────────┘
```

Responsibilities:

- **pulse-watcher** — device discovery & classification (keyboard vs pointer), per-minute aggregation, idle/AFK derivation, resilient shipping to AW (retry + small queue), systemd user service.
- **ActivityWatch** — persistence, retention, REST API, web dashboard (used for deep dives; not modified by this project).
- **pulse widget** — polls the API, shapes series, draws the chart, renders bar text; pure display, no storage.

Cadence: watcher flushes every 60 s; widget polls every 30–60 s and on panel open.

## 4. Data model

One event per minute, in the `input` bucket:

```json
{
  "timestamp": "2026-11-12T14:37:00+01:00",
  "duration": 60.0,
  "data": { "keystrokes": 214, "clicks": 31, "scroll_events": 12, "distance_px": 18540, "afk": false }
}
```

- `afk: true` minutes carry zeros (or are skipped entirely — decide at implementation; skipping keeps the DB small).
- "Total activity" per interval = count of minutes with any input (or sum of normalized counts — decide in Phase 3 while tuning the visual).
- Final `data` keys follow stock `aw-watcher-input` (Q1) so AW's own visualizations keep working.

## 5. Component specs

### 5.1 pulse-watcher (Python)

| Module | Responsibility |
|---|---|
| `devices.py` | Enumerate evdev devices; classify via capabilities (`EV_KEY`+keys → keyboard, `EV_REL` → pointer). Handle EACCES with a clear "add user to input group" message. Rescan on read errors (hotplug); udev monitor is a Phase 4 nicety. |
| `counter.py` | Per-minute aggregation; multi-device summing; idle timer (configurable, default 180 s) → `afk`; flush tick. |
| `awclient.py` | Create bucket if missing; POST events; retry with backoff; keep a bounded queue of unshipped minutes across AW restarts. |
| `__main__.py` | CLI: `--verbose`, `--aw-url`, `--bucket-prefix`, device include/exclude filters. |

Config file: `~/.config/omarchy-pulse/config.toml` (optional; CLI flags override).

Service: `watcher/systemd/pulse-watcher.service` (user unit): `Restart=on-failure`, starts after login; document co-start with AW.

### 5.2 pulse widget (QML)

| Piece | Behavior |
|---|---|
| Bar item | Compact text (e.g. `⌨ 12.4k · 🖱 1.8k`) or mini sparkline; updates ≤ every 60 s; click opens panel; keyboard-accessible. |
| Panel | `KeyboardPanel`-based popup: Day/Week toggle, `Canvas` line chart with 3 series (total/keyboard/mouse) in palette colors, hover/touch readout, axis labels via `Commons.I18n`. |
| Data | On open + on poll timer: resolve bucket id from `/api/0/buckets`, fetch events for the range, bin into 24/7 points, cap response size, cache last-good data on error. |
| Settings | Poll interval, bucket prefix, AFK threshold — via Omarchy plugin settings if available in the installed version (verify against built-ins, Q3), else `~/.config/omarchy-pulse.json`. |

## 6. Phases

### Phase 0 — Kickoff (done)
Repo, README, AGENTS.md, this plan.

### Phase 1 — watcher MVP
- evdev device discovery + classification; per-minute counter; AW client (create bucket + POST); systemd user unit; logging without key content; unit tests.
- **Acceptance:** with the service running on Hyprland, typing/mousing produces per-minute events in the AW bucket within ~60 s; service auto-restarts after device replug or crash; test suite green; inspection of logs/DB shows no key identifiers.

### Phase 2 — bar widget MVP
- Plugin scaffold copied from a built-in plugin's structure; bar text with today's totals; AW fetch with error caching; install script (symlink into `~/.config/omarchy/plugins/`).
- **Acceptance:** bar shows today's keyboard/mouse counts, refreshes ≤60 s, survives theme switch and `omarchy restart shell`.

### Phase 3 — chart popup
- `KeyboardPanel` with Day/Week toggle and 3-series `Canvas` chart; hover readout; theme colors; motion per Omarchy guidelines.
- **Acceptance:** both views render correctly across midnight rollover; curves follow the palette after `omarchy theme set <name>`; panel opens via mouse and keyboard.

### Phase 4 — polish & share
- i18n catalogs (`en.json` + structure), per-app breakdown joining `aw-watcher-window-hyprland` data, PKGBUILD/install script polish, README screenshots, release v0.1, (optional) submit to Omarchy community channels.

## 7. Risks & mitigations

| Risk | Mitigation |
|---|---|
| `input` group grants read access to *all* input devices | Privacy invariant in AGENTS.md; count-only code path; test asserting event schema; code review discipline. |
| Device hotplug / suspend-resume breaks reads | Rescan on read error; `Restart=on-failure`; skip/merge minutes across clock jumps after resume. |
| AW API details differ (query params, auth) | Confirm against installed AW version in Phase 1; pin behavior; localhost-only. |
| QML Canvas perf | Repaint only on new data (60 s) and on view toggle; never on an animation timer. |
| Double counting with multiple keyboards/mice | Summing across devices is the intended semantic (an event is an event); document it. |
| activitywatch-bin autostart method varies (desktop entry vs user service) | Verify on this machine in Phase 1; document the chosen method in the README install section. |

## 8. Open questions

1. **Q1 — exact event `data` keys** of stock `aw-watcher-input` (to keep the bucket schema drop-in compatible). Check source before Phase 1 coding.
2. **Q2 — "total" curve definition** for the visual: active-minutes per bin vs normalized event volume. Tune in Phase 3.
3. **Q3 — Omarchy plugin settings API** in the installed shell version (how built-ins read `shell.json` options).
4. **Q4 — week view** granularity beyond D7 if daily bins feel too coarse.
5. **Q5 — repo name/visibility** — currently `Maxsh/omarchy-pulse`, public; rename/visibility is a one-liner if wanted.
