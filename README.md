# omarchy-pulse

> See the pulse of your day: keyboard, mouse, and total activity as live curves — right in your Omarchy bar.

**Status: design phase.** Docs first, code next — see [docs/PLAN.md](docs/PLAN.md) for the draft implementation plan.

## What it shows

Three curves, side by side, for the current day or week:

| Curve | Meaning |
|---|---|
| **Total** | Active time per interval (any input counts) |
| **Keyboard** | Seconds your hands were on the keyboard |
| **Mouse** | Seconds your hands were on the mouse (moving, clicking, scrolling) |

A compact bar widget shows today's numbers at a glance; clicking it opens a themed panel with the charts.

## Why

Omarchy runs Hyprland on Wayland, and Wayland deliberately keeps apps from sniffing global input — so the stock ActivityWatch input watcher (pynput/X11-based) can't see your input there. Existing tools either don't work on Wayland or don't give you keyboard-vs-mouse curves you can keep on screen.

omarchy-pulse fills the gap with two small pieces:

1. **`pulse-watcher`** — a tiny evdev-based watcher that attributes your input time per minute (never key contents) and stores it in [ActivityWatch](https://activitywatch.net/), which already solves storage, retention, and a full web dashboard.
2. **`pulse` widget** — an [Omarchy shell](https://omarchy.org/) plugin (Quickshell/QML) that reads ActivityWatch's local API and draws day/week curves that follow your Omarchy theme.

## How activity is measured

Raw counts alone can't answer "was I typing or mousing?" — one key press and one second of scrolling are both just "1". So the watcher goes one step further and reconstructs, per second, **which device your hands were on**, using results from HCI motor-behavior research (the same constants that power the [Keystroke-Level Model](https://web.eecs.umich.edu/~kieras/docs/GOMS/KLM.pdf), Card, Moran & Newell 1980):

- **Input comes in bursts.** A pause longer than ~2 s ends a typing burst (a word pause), ~1 s ends a pointing burst; the last 1 s of each burst still counts as that device's time.
- **Switching devices costs "homing" time** — the KLM's H operator, 0.4 s — credited to the device you switch *to*. A quick click after typing therefore charges the click (plus homing) to the mouse, not the keyboard.
- **Modifiers belong to mouse actions.** A key event within 0.3 s of a click, or while a button is held (Shift+drag, Ctrl+click), counts as mouse work.
- **Motion is real only above a threshold.** ≥ 1 mm of pointer travel within 250 ms (touchpad resolution from the kernel; mice assumed 1000 DPI). Hand tremor while reading stays idle.
- **Held keys and buttons count as continuous time.** Autorepeat keeps the keyboard alive; a held button keeps the mouse alive without needing movement.
- **Gaming-style overlap** — WASD plus aiming, alternating faster than homing — is recognized as *both* at once and split evenly for display.
- **Away time.** In the widget, input gaps longer than 3 minutes (ActivityWatch's AFK threshold) drop out of the day's span instead of reading as idle — lunch and sleep don't dilute the split.

Per minute, the watcher stores the stock counters (`presses`, `clicks`, …) plus `kbS` / `mouseS` / `bothS` — seconds per device class. Keyboard, mouse, and idle are then measured in the same unit and always add up to the span. Classification never sees *which* key was pressed — timing and counts only.

## Architecture

```
        ┌──────────────────────────┐
        │   /dev/input/event*      │
        └────────────┬─────────────┘
                     ▼
┌────────────────────────────────────────┐
│ pulse-watcher (Python + evdev)         │
│ systemd user service · counts only     │
└──────────────────┬─────────────────────┘
                   ▼  per-minute counts + seconds (REST · localhost:5600)
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

## Privacy: counts, never content

- The watcher counts `EV_KEY` press events and immediately discards *which* key was pressed. No keylogging, ever — not even in debug logs.
- Mouse is counted as clicks, scroll steps, and accumulated pointer distance.
- Everything stays local: ActivityWatch's localhost API and its local SQLite files.
- It's a normal systemd user service — stop it any time.

## Roadmap

- [x] Phase 0 — project kickoff, docs (this repo state)
- [x] Phase 1 — `pulse-watcher` MVP: evdev → ActivityWatch, systemd user service
- [x] Phase 2 — bar widget MVP: keyboard/mouse/idle split as a stacked mini-bar + percentage popup
- [x] Phase 3 — popup: today's numbers, last-7-days bars with hover tooltips, weekly total bar, refresh action
- [x] Per-app breakdown — "Top apps" (today) joining window focus with input minutes ([PR](../../pulls))
- [x] Input-time attribution — keyboard/mouse measured in seconds via a device-ownership timeline inspired by HCI's Keystroke-Level Model (see "How activity is measured")
- [ ] Phase 4 — polish: i18n, per-app breakdown (via `aw-watcher-window-hyprland`), packaging, screenshots

Details, decisions, and acceptance criteria: [docs/PLAN.md](docs/PLAN.md).

## Requirements (planned)

- Omarchy (Hyprland + Omarchy shell)
- [ActivityWatch](https://activitywatch.net/) — `omarchy pkg aur add activitywatch-bin`
- Python 3.11+ with `python-evdev` — `omarchy pkg add python-evdev`
- Your user in the `input` group (so the watcher can read device events)

## Related

- [ActivityWatch](https://activitywatch.net/) — local time/data tracker used as the storage backend
- [aw-watcher-window-hyprland](https://docs.activitywatch.net/en/latest/watchers.html) — community window watcher for Hyprland (used in Phase 4 for per-app stats)
- Omarchy shell plugin docs — see `~/.agents/skills/omarchy/plugins.md` on an Omarchy machine with this skill installed

## License

MIT — to be added with the first code drop.
