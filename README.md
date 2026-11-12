# omarchy-pulse

> See the pulse of your day: keyboard, mouse, and total activity as live curves — right in your Omarchy bar.

**Status: design phase.** Docs first, code next — see [docs/PLAN.md](docs/PLAN.md) for the draft implementation plan.

## What it shows

Three curves, side by side, for the current day or week:

| Curve | Meaning |
|---|---|
| **Total** | Active minutes per interval (any input counts) |
| **Keyboard** | Keystrokes per interval |
| **Mouse** | Clicks, scroll steps, and pointer distance per interval |

A compact bar widget shows today's numbers at a glance; clicking it opens a themed panel with the charts.

## Why

Omarchy runs Hyprland on Wayland, and Wayland deliberately keeps apps from sniffing global input — so the stock ActivityWatch input watcher (pynput/X11-based) can't see your input there. Existing tools either don't work on Wayland or don't give you keyboard-vs-mouse curves you can keep on screen.

omarchy-pulse fills the gap with two small pieces:

1. **`pulse-watcher`** — a tiny evdev-based watcher that counts input *events* per minute (never key contents) and stores them in [ActivityWatch](https://activitywatch.net/), which already solves storage, retention, and a full web dashboard.
2. **`pulse` widget** — an [Omarchy shell](https://omarchy.org/) plugin (Quickshell/QML) that reads ActivityWatch's local API and draws day/week curves that follow your Omarchy theme.

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

## Privacy: counts, never content

- The watcher counts `EV_KEY` press events and immediately discards *which* key was pressed. No keylogging, ever — not even in debug logs.
- Mouse is counted as clicks, scroll steps, and accumulated pointer distance.
- Everything stays local: ActivityWatch's localhost API and its local SQLite files.
- It's a normal systemd user service — stop it any time.

## Roadmap

- [x] Phase 0 — project kickoff, docs (this repo state)
- [ ] Phase 1 — `pulse-watcher` MVP: evdev → ActivityWatch, systemd user service *(code complete; live validation pending — needs `input` group + ActivityWatch install)*
- [ ] Phase 2 — bar widget MVP: today's keyboard/mouse counts in the bar
- [ ] Phase 3 — chart popup: day/week views, three curves, theme colors
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
