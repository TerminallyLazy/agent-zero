# Spike 0.X: Top-level CLI flag coverage (general)

**Date:** 2026-05-05
**jcode version probed:** v0.11.10
**Status:** Resolved

## Probes against `jcode` v0.11.10 — findings table

| Spec/plan claim | Reality | Status |
|---|---|---|
| `jcode --socket <path> serve --owner-pid <pid>` | `--socket` works at top level AND on `serve`. **`--owner-pid` does NOT exist** on `serve` subcommand. | ❌ Drop `--owner-pid` |
| `jcode serve --no-tui` | No `--no-tui` flag; `serve` does not start TUI by default | ✅ Drop `--no-tui` (already done in iter 1) |
| `jcode serve --no-gateway` | No `--no-gateway`; gateway controlled via config | ✅ Use `JCODE_CONFIG` overlay |
| `jcode session list --json` | Subcommand does not exist | ❌ See Spike 0.2 — read `~/.jcode/sessions/` |
| `jcode provider add --api-key-stdin` | Flag does not exist | ❌ See Spike 0.4 — use `--api-key-env` |
| `jcode provider add --json --overwrite` | Not visible in `--help`; need empirical check | ⚠️ Probe before relying |
| `jcode provider remove` | Subcommand does not exist | ❌ See Spike 0.9 — direct config edit |
| `jcode provider list --json` | Exists | ✅ |
| `jcode login --print-auth-url --json` | Exists, full set of completion flags | ✅ See Spike 0.8 |
| `jcode self-dev` | Top-level subcommand exists | ✅ |
| `jcode --resume <id>` | Resumes by id; `--resume` (no id) lists in TUI | ✅ |

## New top-level subcommands not used in plan but worth knowing

- `pair` — generate pairing code for iOS/web client
- `transcript` — inject externally transcribed text into active TUI
- `dictate` — send to last-focused jcode client or type raw text
- `setup-hotkey` — global hotkey Alt+;
- `setup-launcher` — install in app launcher
- `auth-test` — full credential probe + smoke
- `model` — model management
- `restart` — save/restore open jcode windows across reboot
- `replay` — replay saved session in TUI
- `update` — self-update mechanism
- `permissions` — review pending ambient permission requests

## Plan impact

Spawn command in Task 4.3 (`DaemonSupervisor.ensure_running`) corrected:

```python
proc = subprocess.Popen(
    [self.jcode_binary, "--socket", str(self.socket_file), "serve"],
    env=env,  # JCODE_CONFIG=overlay set by caller
    stdout=open(log_file, "ab"),
    stderr=subprocess.STDOUT,
    start_new_session=True,
)
```

Drop `--owner-pid <pid>` from spawn; jcode v0.11.10 doesn't support it. Daemon supervision falls
back to PID file + flock.
