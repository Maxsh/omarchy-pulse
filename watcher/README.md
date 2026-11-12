# pulse-watcher

Counts keyboard and mouse input per minute — **never key content** — and ships the counts to
[ActivityWatch](https://activitywatch.net/) into the stock input bucket
(`aw-watcher-input_{hostname}`, type `os.hid.input`), so ActivityWatch's own tools keep working.

Design and decisions: see [../docs/PLAN.md](../docs/PLAN.md).

## Development

```bash
uv sync                 # creates .venv, installs evdev + dev tools
uv run pytest           # unit + integration tests (stub HTTP server; no real ActivityWatch needed)
uv run ruff check .
uv run pulse-watcher --verbose                 # uses http://localhost:5600
uv run pulse-watcher --verbose --exclude Yubico --exclude Power
```

Reading `/dev/input/event*` requires the `input` group (applies once, needs re-login):

```bash
sudo usermod -aG input $USER
```

## Install as a service

```bash
# ActivityWatch server (from the repo root — the AUR package ships no unit for it)
cp install/aw-server.service ~/.config/systemd/user/

# the watcher (adjust ExecStart if this repo lives elsewhere)
cp watcher/systemd/pulse-watcher.service ~/.config/systemd/user/

systemctl --user daemon-reload
systemctl --user enable --now aw-server.service pulse-watcher.service
journalctl --user -u pulse-watcher -f
```

## Config (optional)

`~/.config/omarchy-pulse/config.toml`:

```toml
aw_url = "http://localhost:5600"
bucket_prefix = "aw-watcher-input"
exclude = ["Yubico", "Power"]
verbose = false
```

CLI flags override the config file.
