# Spike 0.6: gateway disable via `JCODE_CONFIG` overlay

**Date:** 2026-05-05
**Spec ref:** §4.1, §8.4, §11
**jcode version probed:** v0.11.10
**Status:** Resolved — overlay works; daemon refuses to start without creds

## Method

Spawn `jcode serve` with `JCODE_CONFIG=<overlay path>` env var pointing at:

```toml
[gateway]
enabled = false
```

Verify: socket created with 0600 perms, no TCP listens, daemon stays alive.

## Findings

✅ **Overlay honored.** Daemon spawned successfully, socket created at 0600, **no TCP listens**:

```
--- TCP listens any process ---
(empty)
--- socket file ---
srw-------@ 1 lazy wheel 0 May  5 05:02 /tmp/jcode-spike06b.sock
--- log head ---
Using Claude (use /model to switch models)
```

(`rapportd` listens that appeared on `:60903` are macOS AirDrop/Continuity, unrelated to jcode.)

⚠️ **Daemon refuses to start without configured credentials.** First spike attempt with no
`ANTHROPIC_API_KEY` and no jcode auth files failed:

```
Error: No credentials configured. Run 'jcode login' or set ANTHROPIC_API_KEY to authenticate.
```

Workaround for spike: passed dummy `ANTHROPIC_API_KEY=sk-ant-fake-not-real-just-for-startup`.
Daemon started; overlay applied; socket created.

## Plan impact

### 1. Gateway disable

Plan Task 4.3 spawn command stays correct:

```python
env = dict(os.environ, JCODE_CONFIG=str(self.overlay_config))
proc = subprocess.Popen(
    [self.jcode_binary, "--socket", str(self.socket_file), "serve"],
    env=env,
    ...
)
```

Overlay file content stays as drafted:

```toml
[gateway]
enabled = false
```

### 2. NEW PLAN ADDITION: Pre-spawn credential check

Plan Chunk 4 must add a credential probe before `ensure_running()` actually spawns:

```python
def _has_creds(self) -> bool:
    """Check whether jcode would refuse to start due to missing creds."""
    auth_files = [
        Path.home() / ".jcode" / "auth.json",
        Path.home() / ".jcode" / "openai-auth.json",
        Path.home() / ".jcode" / "gemini_oauth.json",
        Path.home() / ".jcode" / "antigravity_oauth.json",
    ]
    if any(f.exists() for f in auth_files):
        return True
    if any(env in os.environ for env in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY",
                                          "GEMINI_API_KEY", "OPENROUTER_API_KEY")):
        return True
    # Plugin-imported provider profiles count
    try:
        result = subprocess.run([self.jcode_binary, "provider", "list", "--json"],
                                 capture_output=True, text=True, timeout=5)
        profiles = json.loads(result.stdout)
        return len(profiles) > 0
    except Exception:
        return False

async def ensure_running(self, working_dir: str) -> str:
    if self.is_running():
        return str(self.socket_file)
    if not self._has_creds():
        raise NoCredentialsError(
            "jcode daemon needs at least one configured provider. "
            "Visit plugin settings → Login or set an API key env var."
        )
    # ... rest of spawn logic
```

`NoCredentialsError` is caught by tools (Task 7.x) and returned as a `Response` with a clear
user message + WebUI deep-link to login.

### 3. Plugin install flow ordering

Plan Task 5.1 (`hooks.py install()`) currently:
1. Detect/download binary
2. Probe `cargo`
3. Run provider importer
4. Persist meta

After this spike, ordering must be: detect binary → import providers → **only then attempt
daemon spawn for smoke test**, since `--version` works without creds but a real `serve` needs
them.

`hooks.py install()` should NOT spawn the daemon at all. The `_has_creds()` check + spawn moves
to `ensure_running()` first-use lazy path.

## Risk

If user has zero providers configured at first plugin use (very common for new A0 user), the
plugin must surface a clear "Login required" UI flow before the user clicks any jcode tool.
Add a Welcome banner via `welcome-banners-start` x-extension that says "jcode harness ready —
log in to a provider to begin" with a button that opens the login modal.
