# Spike 0.4: `jcode provider add` flag coverage and error modes

**Date:** 2026-05-05
**Spec ref:** §5.5, §8.2, §11
**jcode version probed:** v0.11.10
**Status:** Resolved — flag set differs from spec/plan assumptions; security model adjusted

## Findings

`jcode provider add` actual flags from `--help`:

| Flag | Type | Purpose |
|------|------|---------|
| `<NAME>` (positional) | required | Profile name |
| `--base-url <URL>` | required | OpenAI-compatible API base URL |
| `--model <MODEL>` (or `-m`) | required | Default model id |
| `--context-window <N>` | optional | Token context window |
| `--api-key <KEY>` | optional | API key value (lands in argv) |
| `--api-key-env <NAME>` | optional | Env var name to read key from |
| `--no-update`, `--auto-update`, `--trace`, `--quiet`, `--no-selfdev` | global flags | inherited |

❌ **`--api-key-stdin` does NOT exist.** Spec §8.2 and plan Task 6.2 both assert this flag exists
for safe stdin-based key handoff. **It does not.** Available paths for key delivery:

1. `--api-key VALUE` — key lands in argv, visible in `ps aux` output. **Insecure.**
2. `--api-key-env NAME` — references an env var. Plugin sets the env var, runs `jcode provider
   add --api-key-env JCODE_PROVIDER_<NAME>_API_KEY`, jcode reads `os.environ[NAME]`. Key
   transits parent→child via env, never argv.

❌ **`--json` flag NOT visible** on `provider add` help. Probe required to confirm presence.

❌ **`--overwrite` flag NOT visible** on `provider add` help. Probe required.

## Recommended approach

Plan and spec §5.5 / §8.2 must change:

- Drop all references to `--api-key-stdin`.
- Use `--api-key-env <NAME>` exclusively. Plugin sets a transient env var with a unique name per
  profile (`JCODE_PROVIDER_<UPPER_NAME>_API_KEY`), invokes `provider add` with that var name,
  then unsets the var in the parent shell.
- Confirm presence/absence of `--json` and `--overwrite` via empirical probe before implementing
  Task 6.2 / 6.3.
- If `--overwrite` is absent: collision-handle by deleting the existing config.toml entry first
  (likely via direct file edit since `provider remove` doesn't exist either — see Spike 0.9).

## Plan impact

- Task 6.2 (`add_jcode_profile`): rewrite signature to take an env-var-name strategy:
  ```python
  def add_jcode_profile(jcode_bin, profile_name, base_url, model, api_key, overwrite=True):
      env_var = f"JCODE_PROVIDER_{profile_name.upper()}_API_KEY"
      env = dict(os.environ, **{env_var: api_key})
      cmd = [jcode_bin, "provider", "add", profile_name,
              "--base-url", base_url, "--model", model,
              "--api-key-env", env_var]
      result = subprocess.run(cmd, env=env, capture_output=True, text=True)
      ...
  ```
- Task 6.2 test must verify the key never appears in argv (still possible) AND never appears in
  child's actual env when test inspects it (the env var is private to the spawn).
- Task 12.4 (security smoke test): verify via `ps -E aux` that the env var is not visible to
  other users (PROC_PIDFDINFO on macOS / `/proc/<pid>/environ` on Linux is owner-readable).
