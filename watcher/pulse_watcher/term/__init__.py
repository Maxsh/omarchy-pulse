"""pulse-term-watcher: which program has focus inside the focused terminal window.

The window watcher (aw-awatcher) only sees the terminal emulator ("foot"). This
package resolves the program running inside it - a herdr pane, a tmux pane or the
plain pty foreground process - and heartbeats just its *name* into its own
ActivityWatch bucket (type ``app.terminal.focus``).

Privacy (AGENTS.md rule 1): only a process or agent name is ever stored. Never
cwd, paths, arguments, pane/terminal titles or pane contents.
"""
