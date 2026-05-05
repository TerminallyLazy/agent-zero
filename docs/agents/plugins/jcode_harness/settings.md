# jcode_harness — Settings Reference

Every key in `usr/plugins/jcode_harness/default_config.yaml`, with default,
allowed values, and when to change.

## `binary`

Controls the `jcode` binary used by the daemon.

### `binary.path`

- **Type**: string
- **Default**: `""` (auto-detect)
- **Allowed**: any absolute path, or blank
- **Resolution order when blank**: PATH lookup -> `~/.jcode/builds/stable/jcode` -> auto-download
- **Change when**: you want to point at a self-built or system-installed binary
  (for example `/usr/local/bin/jcode` or a `cargo install` artifact).

### `binary.auto_update`

- **Type**: bool
- **Default**: `true`
- **Allowed**: `true` | `false`
- **Change when**: you want to pin a specific version. With `false`, the
  plugin still verifies SHA256 but never replaces an existing binary.

## `daemon`

Daemon lifecycle and transport.

### `daemon.mode`

- **Type**: string enum
- **Default**: `per_project`
- **Allowed**: `per_project` | `per_a0_instance` | `external`
- `per_project` — one daemon per working directory. Sessions and memory are
  scoped to the project. Recommended.
- `per_a0_instance` — one daemon shared across all projects in this A0
  instance. Use when you want unified memory across projects.
- `external` — the plugin does not manage daemon lifecycle. You are
  responsible for starting `jcode daemon` and pointing `socket_path` at it.

### `daemon.socket_path`

- **Type**: string
- **Default**: `""` (auto-derived to `~/.amplihack/jcode/<instance-id>/socket`)
- **Allowed**: any writable absolute path, or blank
- **Change when**: running multiple A0 instances on the same host with
  conflicting auto-derived paths, or when the home directory is not
  writable (CI, restricted containers).

## `features`

Feature flags that gate optional subsystems.

### `features.swarm`

- **Type**: bool
- **Default**: `true`
- **Change when**: you want to disable `jcode_swarm_msg` entirely (for
  example to prevent agent-to-agent messaging in multi-tenant deployments).

### `features.self_dev`

- **Type**: bool
- **Default**: `false`
- **Auto-flip**: install hook sets this to `true` if `cargo` is detected on
  PATH at install time.
- **Change when**: you've installed Rust after enabling the plugin, or you
  want to forcibly disable jcode self-modification regardless of toolchain.

### `features.cross_harness_resume`

- **Type**: bool
- **Default**: `true`
- **Change when**: you want to hide `jcode_resume`'s cross-harness listing
  (for example to keep Codex / OpenCode sessions out of the picker).

### `features.cross_harness_import`

- **Type**: bool
- **Default**: `false`
- **Status**: v2 deferred. The flag is read but the import path is a no-op
  in v1; setting it `true` logs a "feature flag reserved for v2" notice
  and is otherwise ignored.

## `providers`

Provider credentials and login state.

### `providers.auto_import_a0_keys`

- **Type**: bool
- **Default**: `true`
- **Effect**: imports A0 LiteLLM keys as `_a0_imported_*` profiles via
  `jcode --api-key-env`, so the daemon never sees the raw secret in its
  config file.
- **Change when**: you want jcode to use only its own OAuth subscriptions,
  not A0's API keys.

### `providers.oauth_subscriptions`

- **Type**: list (managed)
- **Default**: `[]`
- **Notes**: populated by the side-panel Login UI flow. Not user-edited.
  Listing here lets the daemon recreate subscriptions on restart without
  another OAuth round-trip.

## `ui`

Side panel and surfacing.

### `ui.side_panel`

- **Type**: bool
- **Default**: `true`
- **Effect**: renders `SidePanelSnapshot` pages in A0's right-canvas
  surface (status, providers, sessions).
- **Change when**: you prefer the chat-only surface and want to hide the
  side panel entirely.

### `ui.mermaid`

- **Type**: bool
- **Default**: `true`
- **Effect**: renders Mermaid diagrams emitted by the daemon inline.
- **Change when**: you want plain-text fallback (slower terminals, screen
  readers).

### `ui.notifications`

- **Type**: bool
- **Default**: `true`
- **Effect**: surfaces compaction and cache-cold warnings via A0's
  notification helper.
- **Change when**: you want a quieter UI; the events still log.

## `safety_mode`

- **Type**: string enum
- **Default**: `default`
- **Allowed**: `default` | `paranoid` | `yolo`
- Controls jcode tool sandbox aggressiveness.
- `default` — sensible mid-point: shell tools require approval for
  destructive operations, file edits run unattended within the working
  tree.
- `paranoid` — every tool call requires explicit approval. Slow but
  audit-friendly. Recommended for shared / multi-user hosts.
- `yolo` — no approvals, no sandbox enforcement. Use only in disposable
  containers.

## `min_jcode_version`

- **Type**: string (semver)
- **Default**: `0.11.4`
- **Effect**: install and start refuse binaries older than this version.
  The protocol codec is pinned to the matching jcode protocol revision;
  older binaries will fail handshake.
- **Change when**: pinning a newer floor for a deployment. Lowering below
  the default is unsupported.

## See also

- [`README.md`](../../../../usr/plugins/jcode_harness/README.md) for install + quick start.
- [`troubleshooting.md`](troubleshooting.md) for error messages and fixes.
- Spec: `docs/superpowers/specs/2026-05-05-jcode-harness-plugin-design.md`.
