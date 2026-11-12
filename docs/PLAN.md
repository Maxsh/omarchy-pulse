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
| D5 | AFK/idle | Implicit: empty minutes are not emitted | Absence of an event means no input in that minute — enough for activity curves. An explicit AFK state (e.g. via hypridle) can be added later if "screen-on but idle" semantics are wanted. |
| D6 | Bucket schema | Stock-compatible: bucket id `aw-watcher-input_{hostname}`, type `os.hid.input`, data keys `presses`, `clicks`, `deltaX`, `deltaY`, `scrollX`, `scrollY` | Confirmed from aw-watcher-input/aw-watcher-afk sources (Q1 resolved). Deliberate deviation: per-minute events instead of 5s heartbeats — identical totals for AW tooling, ~12× fewer events, light payload for the widget. |
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
  "timestamp": "2026-11-12T13:37:00+00:00",
  "duration": 60.0,
  "data": { "presses": 214, "clicks": 31, "deltaX": 6120, "deltaY": 4180, "scrollX": 0, "scrollY": 12 }
}
```

- Keys match stock `aw-watcher-input` exactly (Q1 resolved), so ActivityWatch's own visualizations keep working.
- Minutes with zero input are not emitted — absence means idle (D5).
- "Total activity" per interval = count of minutes with any input (or sum of normalized counts — decide in Phase 3 while tuning the visual).

## 5. Component specs

### 5.1 pulse-watcher (Python)

| Module | Responsibility |
|---|---|
| `devices.py` | Enumerate `/dev/input/event*` (own glob — `evdev.list_devices()` silently drops unreadable devices); classify via capabilities (letters/LED → keyboard, relative/absolute motion → pointer, gamepads & power buttons → ignored). Logs a fix hint when devices are unreadable (missing `input` group). Rescanned every minute for hotplug. |
| `reader.py` | One thread per device: raw evdev events → semantic count records via `EventTranslator` (presses = physical presses only, autorepeat excluded; touchpad deltas while touched; hi-res wheel ignored to avoid double counting). |
| `counter.py` | Thread-safe per-minute bins with the stock keys; multi-device summing by construction. |
| `events.py` | Minute bin → ActivityWatch event (ISO timestamp, duration 60 s). |
| `awclient.py` | Bucket creation (`os.hid.input`), bulk event POST, bounded retry queue (180 min) across AW outages/restarts. |
| `config.py` | Defaults < `~/.config/omarchy-pulse/config.toml` < CLI flags. |
| `__main__.py` | Wiring: minute-boundary flush loop, device rescan, signal handling, clean shutdown. |

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

### Phase 1 — watcher MVP — **code complete (2026-11-12); live validation pending**
- Implemented: device discovery + classification; per-minute counter; AW client (create bucket + POST, retry queue); systemd user unit; TOML config + CLI; logging without key content; 27 unit/integration tests.
- **Acceptance:** with the service running on Hyprland, typing/mousing produces per-minute events in the AW bucket within ~60 s; service auto-restarts after device replug or crash; test suite green; inspection of logs/DB shows no key identifiers.
- **Remaining:** add user to `input` group + install ActivityWatch, then verify the acceptance above.

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
| activitywatch-bin autostart method varies (desktop entry vs user service) | **Resolved:** the AUR package ships no systemd unit for the Python server (only an `aw-server-rust` template under `/opt` and an XDG autostart for the tray) — `install/aw-server.service` provides a proper user unit. |

## 8. Open questions

1. ~~**Q1 — exact event `data` keys**~~ **Resolved 2026-11-12:** stock keys are `presses`, `clicks`, `deltaX`, `deltaY`, `scrollX`, `scrollY`; bucket `aw-watcher-input_{hostname}`, type `os.hid.input` (sources: aw-watcher-input `main.py`, aw-watcher-afk `listeners.py`).
2. **Q2 — "total" curve definition** for the visual: active-minutes per bin vs normalized event volume. Tune in Phase 3.
3. **Q3 — Omarchy plugin settings API** in the installed shell version (how built-ins read `shell.json` options).
4. **Q4 — week view** granularity beyond D7 if daily bins feel too coarse.
5. **Q5 — repo name/visibility** — currently `Maxsh/omarchy-pulse`, public; rename/visibility is a one-liner if wanted.
