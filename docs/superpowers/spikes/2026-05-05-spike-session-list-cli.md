# Spike 0.2: `jcode session list --json` subcommand

**Date:** 2026-05-05
**Spec ref:** §6.3, §11
**jcode version probed:** v0.11.10 (release binary, macos-aarch64)
**Status:** Resolved — subcommand does NOT exist; fallback chosen

## Question

Does `jcode session list --json` exist as a CLI subcommand for cross-harness session listing?
If not, what is the fallback?

## Findings

❌ **There is no `session` subcommand.** `jcode --help` enumerates all top-level subcommands:
`serve, connect, run, login, repl, update, version, usage, self-dev, debug, auth, provider,
memory, ambient, pair, permissions, transcript, dictate, setup-hotkey, setup-launcher, browser,
replay, model, auth-test, restart, help`. No `session`.

❌ **`--resume --json` is rejected.** Probe:

```
$ jcode --resume --json
error: unexpected argument '--json' found
Usage: jcode --resume [<RESUME>]
```

The `--resume` flag is global (not a subcommand), takes an optional session-id, and emits no
JSON. When given without an id, it lists sessions in the TUI — not script-friendly.

## Fallback chosen

**Read `~/.jcode/sessions/` directly.** The session journal layout is documented in spec §6.3
and `jcode/src/storage.rs`. Each session is `~/.jcode/sessions/<id>/journal.jsonl` plus a
`session.json` snapshot containing the title, `provider_key`, `provider_session_id`, model,
created_at, updated_at.

```python
def list_sessions() -> list[dict]:
    base = Path.home() / ".jcode" / "sessions"
    if not base.exists():
        return []
    out = []
    for sess_dir in base.iterdir():
        snap = sess_dir / "session.json"
        if not snap.exists():
            continue
        try:
            data = json.loads(snap.read_text())
            out.append({
                "id": sess_dir.name,
                "title": data.get("title", ""),
                "provider_key": data.get("provider_key", "jcode"),
                "updated_at": data.get("updated_at"),
                "working_dir": data.get("working_dir"),
            })
        except (json.JSONDecodeError, OSError):
            continue
    return sorted(out, key=lambda s: s.get("updated_at") or 0, reverse=True)
```

## Plan impact

Update Task 11.1 (`api/list_sessions.py`) and Task 7.5 (`jcode_resume`) to use the journal-file
reader above instead of the (non-existent) `jcode session list --json` subprocess.

Schema for `session.json` requires reading `jcode/src/session.rs` to confirm exact field names.
Add a sub-spike if any field guess is wrong during implementation.
