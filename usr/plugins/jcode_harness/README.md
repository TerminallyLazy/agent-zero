# jcode_harness

Agent Zero plugin that embeds the **jcode** coding-agent harness as a first-class
A0 surface. Adds a memory graph, skills, swarm coordination, agentgrep, 28 native
coding tools, and cross-harness session resume from Claude Code, Codex, OpenCode,
and pi — all driven from inside Agent Zero with no separate CLI to babysit.

## Status

Pre-release — `0.1.0`. APIs and config keys may shift before the first stable tag.
Spec: `docs/superpowers/specs/2026-05-05-jcode-harness-plugin-design.md`.
Plan: `docs/superpowers/plans/2026-05-05-jcode-harness-plugin.md`.

## Install

The plugin works in two modes. Both are configured from the A0 **Plugins** dialog
(no terminal required, per the non-tech user policy in `AGENTS.plugins.md`).

### Mode A — Auto-install (recommended)

When you enable the plugin and `binary.path` is left blank, A0 downloads the
`jcode` binary into `~/.jcode/builds/stable/jcode` on first use, verifies its
SHA256 against the published manifest, and starts the daemon in `per_project`
mode. Nothing else is required.

### Mode B — Bring your own binary

If you already have `jcode` installed (for example a self-built `cargo install
--path crates/jcode-cli` artifact), set the absolute path in plugin settings:

```text
Plugins -> jcode_harness -> Settings -> binary.path = /usr/local/bin/jcode
```

The plugin enforces `min_jcode_version` (default `0.11.4`) and refuses to start
older binaries. See `docs/agents/plugins/jcode_harness/settings.md`.

## Quick Start

1. Open the **Plugins** dialog in A0 and enable `jcode_harness`.
2. Open the **jcode side panel** (right-canvas surface) — you should see
   "Daemon: stopped" and a single "Start" button.
3. Click **Start**. The daemon comes up on a per-project Unix socket at
   `~/.amplihack/jcode/<instance-id>/socket`. The status flips to "ready".
4. In the side panel, click **Login** next to a provider (Claude / OpenAI /
   Gemini / Copilot / Azure) and complete the OAuth flow in the popup. A0
   auto-imports any LiteLLM keys you already configured as `_a0_imported_*`
   profiles, so users with API keys can skip OAuth entirely.
5. Send a chat message. The `jcode_coder` profile is now available via the
   profile picker; selecting it routes coding requests through `jcode_session`.

## Provider Login

Native OAuth subscriptions supported by jcode:

- Anthropic (Claude Pro / Max)
- OpenAI (ChatGPT Plus / Pro / Team)
- Google (Gemini Advanced)
- GitHub Copilot
- Azure OpenAI

Plus auto-imported A0 provider keys, exposed to jcode as `_a0_imported_*`
profiles via `jcode --api-key-env` so the daemon never sees the raw secrets in
its config file. Toggle with `providers.auto_import_a0_keys` in plugin settings.

## Cross-harness Resume

The plugin reads existing session histories from sibling coding harnesses —
no manual export needed. The `jcode_resume` tool scans:

- `~/.claude/projects/<...>/` (Claude Code)
- `~/.codex/sessions/`        (Codex)
- `~/.opencode/sessions/`     (OpenCode)
- `~/.pi/sessions/`           (pi)
- `~/.jcode/sessions/`        (jcode itself)

Listed sessions can be opened read-only or, for jcode-native sessions, resumed
with `allow_session_takeover=True`. Cross-harness *import* (rewriting another
harness's transcript into a jcode session) ships in v2 — the
`features.cross_harness_import` flag is currently a no-op.

## Tools

Seven A0 tools land when the plugin is enabled:

- **jcode_session** — opens a bounded jcode session, streams text deltas back
  to A0, surfaces auto-compaction warnings. Default for any non-trivial coding
  task in the `jcode_coder` profile.
- **jcode_memory** — drives jcode's memory graph (`remember | recall | search |
  forget | tag | link | related`). Default scope is `project`.
- **jcode_skill** — `load | list | reload | reload_all | read` against the
  jcode skills subsystem.
- **jcode_grep** — short-lived session that runs jcode's `agentgrep` tool and
  returns the raw output. Use for repo-scale code search.
- **jcode_swarm_msg** — DM, broadcast, share, or read messages between agents
  in the same swarm (mirrors `Comm*` protocol variants).
- **jcode_resume** — list cross-harness resumable sessions, or resume one by id.
- **jcode_self_dev** — trigger jcode self-modification. Gated on a Rust
  toolchain (`cargo` on PATH); never auto-installs Rust.

## Settings

Every key in `default_config.yaml` is documented in
[`docs/agents/plugins/jcode_harness/settings.md`](../../../docs/agents/plugins/jcode_harness/settings.md).
Highlights:

- `daemon.mode` — `per_project` (default), `per_a0_instance`, or `external`
- `safety_mode` — `default` | `paranoid` | `yolo` (controls jcode tool sandbox)
- `features.swarm` / `features.self_dev` / `features.cross_harness_resume`
- `min_jcode_version` — refuses older binaries

## Troubleshooting

See [`docs/agents/plugins/jcode_harness/troubleshooting.md`](../../../docs/agents/plugins/jcode_harness/troubleshooting.md)
for the full set. Common entries:

- "jcode harness needs at least one configured provider"
- "jcode binary missing"
- "Cache went cold this turn"
- "Daemon won't start"
- "Self-dev disabled" (Rust toolchain missing)
- Docker / volume mount caveats
- Windows v1 (named-pipe stub — use WSL2)

## References

- Spec: `docs/superpowers/specs/2026-05-05-jcode-harness-plugin-design.md`
- Plan: `docs/superpowers/plans/2026-05-05-jcode-harness-plugin.md`
- Plugin Index manifest: `index.yaml` (filed separately to `agent0ai/a0-plugins`)
- License: `LICENSE` in this directory.
