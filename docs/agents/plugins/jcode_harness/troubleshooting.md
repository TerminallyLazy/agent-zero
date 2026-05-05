# jcode_harness — Troubleshooting

Common issues with the `jcode_harness` plugin and how to fix them. Each
heading matches the exact error string the plugin surfaces in the chat or
side panel, so you can search this page for what you saw.

## "jcode harness needs at least one configured provider"

The daemon refuses to start until at least one provider has credentials.
Three fix paths:

1. **Settings UI login** — open the **Plugins** dialog, expand
   `jcode_harness`, click **Login** next to a provider, and complete the
   OAuth popup. This is the path the non-tech-user policy assumes.
2. **Environment variable** — set the relevant key before launching A0:
   ```bash
   export ANTHROPIC_API_KEY=sk-ant-...
   export OPENAI_API_KEY=sk-...
   ```
   The provider importer picks up the env var on plugin enable.
3. **A0 key import** — if you already have keys configured in A0's main
   model settings, leave `providers.auto_import_a0_keys: true` and the
   plugin imports them as `_a0_imported_*` profiles automatically. Toggle
   off in plugin settings if you want manual control.

## "jcode binary missing"

The daemon binary cannot be located.

- **Auto-install mode** (default): the plugin downloads `jcode` into
  `~/.jcode/builds/stable/jcode` on first use and verifies SHA256. If the
  download fails, check the network and inspect
  `~/.amplihack/jcode/<id>/logs/install.log`.
- **Manual mode**: set `binary.path` in plugin settings to an absolute path:
  ```text
  binary.path: /usr/local/bin/jcode
  ```
  The path must be readable and executable by the A0 process.

If you see "binary version 0.10.x older than min_jcode_version 0.11.4",
either upgrade the binary or lower `min_jcode_version` in plugin settings.
Pinning below the default is unsupported and may break the protocol codec.

## "Cache went cold this turn"

This is a *warning*, not an error. It surfaces when jcode emits a
`compaction` event or when the Anthropic prompt cache TTL (5 minutes)
expires between turns. Effects:

- Next turn re-reads the full transcript uncached — slower and more
  expensive.
- Long sessions sitting idle past the 5-minute window will always trigger
  it on resume.

Mitigations:

- Keep sessions active (a turn at least every ~4 minutes) when you care
  about latency.
- Use `jcode_session` rather than the one-shot wrappers
  (`jcode_grep`, `jcode_memory`, `jcode_skill`) for multi-turn work — the
  one-shot wrappers always allocate fresh sessions and never benefit from
  cache.
- Compaction is intentional under load; treat the warning as informational.

## "Daemon won't start"

Inspect the per-instance log directory first:

```bash
ls ~/.amplihack/jcode/*/logs/
tail -n 200 ~/.amplihack/jcode/<id>/logs/daemon.log
```

Common causes:

- **Permission issues** — the socket path
  (`~/.amplihack/jcode/<id>/socket`) must be writable. If A0 runs as a
  different user than the directory owner, fix ownership or move the
  socket via `daemon.socket_path`.
- **SHA256 mismatch on download** — auto-install verifies the binary
  against the published manifest. A mismatch aborts the install. Delete
  `~/.jcode/builds/stable/jcode` and retry, or switch to manual mode.
- **External daemon stopped** — if `daemon.mode: external`, the plugin
  does not manage lifecycle. Start `jcode daemon` yourself.

Port collision is *not* a cause: the daemon transport is socket-only
(Unix domain socket / Windows named pipe). There is no TCP port to clash
with.

## "Self-dev disabled"

`jcode_self_dev` requires the Rust toolchain. The plugin never
auto-installs Rust (per the non-tech-user policy in
`AGENTS.plugins.md`).

To enable:

1. Install Rust from <https://rustup.rs>:
   ```bash
   curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
   ```
2. Confirm `cargo --version` reports a version on PATH.
3. Re-enable `features.self_dev` in plugin settings (the install hook
   auto-flips this to `true` if `cargo` is detected at install time, so
   you usually don't have to touch it manually).

The flag is intentionally stateful: turning it off persists until you
explicitly re-enable.

## "Cross-harness import (v2 deferred)"

The `features.cross_harness_import` setting exists but is a no-op in v1.
The v1 plugin can *resume* native jcode sessions and *list* sessions from
sibling harnesses (Claude Code, Codex, OpenCode, pi), but it does not
rewrite their transcripts into jcode-native sessions. That ships in v2.

If you set `features.cross_harness_import: true` you'll see a
"feature flag reserved for v2" notice in the logs and the flag is
ignored. Leave it `false`.

## Docker / volume mount caveat

The plugin keeps state in two locations on the host:

- `~/.jcode/` — binary builds, native jcode session history,
  user-scope memory.
- `~/.amplihack/jcode/<instance-id>/` — per-A0-instance daemon
  socket, logs, ephemeral state.

If A0 runs in Docker, both directories must be mounted as **persistent
volumes**. Otherwise:

- Sessions disappear on container restart.
- Daemon state is recreated every boot (slow first turn).
- `jcode_resume` will return an empty list because no transcripts persist.

Sample compose snippet:

```yaml
volumes:
  - ${HOME}/.jcode:/root/.jcode
  - ${HOME}/.amplihack:/root/.amplihack
```

## Windows v1

On Windows, the daemon transport is a **named-pipe stub** in v1. It runs,
but several edge cases are untested (concurrent listener teardown,
Unicode path handling, sandbox enforcement on `safety_mode: paranoid`).
Recommendation: use **WSL2** until v1.1, where native Windows support
becomes a tier-1 target.

The plugin does not refuse to load on native Windows; it logs a
`platform.windows.unsupported` warning at install time and continues.

## See also

- [`README.md`](../../../../usr/plugins/jcode_harness/README.md) for install + quick start.
- [`settings.md`](settings.md) for every config key.
- Spec: `docs/superpowers/specs/2026-05-05-jcode-harness-plugin-design.md`.
