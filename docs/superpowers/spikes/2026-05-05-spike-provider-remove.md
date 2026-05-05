# Spike 0.9: `jcode provider remove --json` subcommand

**Date:** 2026-05-05
**Spec ref:** §5.5, §11
**jcode version probed:** v0.11.10
**Status:** Resolved — subcommand does NOT exist; fallback chosen

## Findings

❌ **`provider remove` does not exist.**

```
$ jcode provider remove
error: unrecognized subcommand 'remove'
```

`provider` subcommand only exposes: `list`, `current`, `add`, `help`.

## Fallback chosen

**Edit `~/.jcode/config.toml` directly.** The provider profile is stored as a `[providers.<name>]`
TOML section per spec §2 and `jcode/src/config/config_file.rs`. Plugin reads, deletes the
section, writes back.

```python
import tomli, tomli_w  # or tomllib (3.11+) for read + tomli_w for write

def remove_jcode_profile(profile_name: str):
    config_path = Path.home() / ".jcode" / "config.toml"
    if not config_path.exists():
        return
    data = tomllib.loads(config_path.read_text())
    providers = data.get("providers", {})
    if profile_name not in providers:
        return
    del providers[profile_name]
    # Also remove any private env file under ~/.config/jcode/
    env_file = Path.home() / ".config" / "jcode" / f"provider-{profile_name}.env"
    env_file.unlink(missing_ok=True)
    # Reset default_provider if it pointed at removed profile
    if data.get("provider", {}).get("default_provider") == profile_name:
        data["provider"]["default_provider"] = "auto"
    config_path.write_text(tomli_w.dumps(data))
    config_path.chmod(0o600)
```

**Risks:**
- Race condition: jcode daemon reads/writes config concurrently. Plugin must stop daemon before
  edit, or use file locking.
- TOML round-trip may lose comments/formatting. `tomli_w` does not preserve. Acceptable for
  plugin-managed profiles only — never edit profiles the user wrote by hand.

## Plan impact

- Task 6.4 (`purge_imported_profiles`): rewrite to use direct config edit; gate on daemon stop
  first.
- Task 11.5 (`api/purge_imported_profiles.py`): same.
- Add `tomli_w` to test deps in Task 12.0 (Python 3.11 has read-only `tomllib`).
- Plan must add a "stop daemon, edit config, restart daemon" sequence to the purge flow.
