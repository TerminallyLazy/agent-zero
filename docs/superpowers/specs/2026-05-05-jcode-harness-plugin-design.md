# jcode Harness Plugin for Agent Zero — Design Spec

**Status:** Draft
**Author:** Brainstorming session, 2026-05-05
**Plugin name:** `jcode_harness`
**Target:** Agent Zero community plugin under `usr/plugins/jcode_harness/`
**Upstream:** `github.com/1jehuang/jcode`

---

## 1. Purpose

Embed the jcode coding-agent harness inside Agent Zero as a community plugin so A0 users get jcode's
agent loop, memory graph, skills, swarm coordination, cross-harness session resume, and 28 native
tools without leaving the A0 WebUI.

The plugin must preserve jcode's speed and feature fidelity while honoring A0's plugin model
(`docs/agents/AGENTS.plugins.md`) and non-technical-user UX expectations.

## 2. Strategy

**Hybrid architecture.** Python plugin = thin client and UI surface. Rust `jcode serve` daemon =
engine. Newline-delimited JSON over a Unix socket (Windows named pipe) bridges the two.

Rationale:

- jcode is 35-crate Rust workspace. A pure-Python port would lose its signature speed and require
  reimplementing the agent loop, memory pipeline, embedding inference, and provider drivers.
- jcode already ships a server/client split (`jcode serve` + `jcode connect`, see
  `jcode/docs/SERVER_ARCHITECTURE.md`). The plugin attaches as just another client.
- The IPC wire format is line-delimited JSON (`jcode/src/protocol.rs:1412-1421`) — consumable
  from Python with `asyncio.open_unix_connection` and a hand-written dataclass codec mirroring
  the Rust `Request`/`ServerEvent` enums. No SDK or Rust FFI required.

Two interaction modes are designed; only one ships in v1:

1. **Embedded session (v1, default).** A0's agent loop runs normally. A `jcode_session` tool
   opens a bounded jcode session per coding task, streams events back into A0 chat, returns the
   final assistant message as the tool result. A0 supervises start/stop. The agent profile
   `jcode_coder` ships as a **prompt-routing profile**: its system prompt strongly favors using
   `jcode_session` for any non-trivial coding work, so the user perceives "jcode-driven" sessions
   without the framework needing a true loop short-circuit.
2. **True full-takeover (deferred to v2).** Originally designed as a `monologue_start` extension
   that bypasses A0's LLM call. **Blocked** because A0's `LoopData` (`agent.py:326-341`) has no
   short-circuit field and no early-exit hook in `before_main_llm_call`. Deferred until either
   (a) an upstream A0 PR adds `LoopData.short_circuit`, or (b) a custom A0 fork is acceptable.
   v2 work item.

## 3. Scope

### 3.1 In scope (v1)

- Core jcode agent loop and 28 built-in tools (read, write, edit, multiedit, patch, apply_patch,
  glob, ls, bash, webfetch, websearch, open, grep, lsp, session_search, conversation_search, batch,
  agentgrep, side_panel, schedule, goal, todo, gmail, codesearch, plus framework tools)
- Memory system: graph (`~/.jcode/memory/graph.json`), 384-dim embeddings, side-agent extraction,
  cascade retrieval (semantic + BFS depth 2 with 0.7 edge decay), explicit `memory_manage` tool
- Skills system: auto-injection by embedding similarity, `/skill-name` slash invocation, on-disk
  format `~/.jcode/skills/<name>/SKILL.md` with YAML frontmatter
- Swarm coordination: inter-agent messaging (DM, broadcast, channel), file-shift notifications,
  parent-coordinator/worker-spawn pattern via the `swarm` tool family
- Cross-harness session resume: import sessions from Claude Code, Codex, OpenCode, and pi using
  jcode's `provider_session_id` round-trip
- Provider OAuth: native flows for Claude, OpenAI/Codex, Gemini, GitHub Copilot, Azure OpenAI,
  triggered from the plugin's WebUI
- Self-dev mode: gated by Rust toolchain detection at install time

### 3.2 Out of scope (v1)

- **True full-takeover mode** — requires upstream A0 change (`LoopData.short_circuit`); v1 ships
  embedded-only. `jcode_coder` profile in v1 is prompt-routing, not loop-replacing.
- Browser tool (Firefox Agent Bridge — separate native binary install, deferred)
- Ambient mode background cycles (long-lived process lifecycle, deferred to v2)
- iOS / mobile clients (per user direction)
- WebSocket gateway exposure (kept disabled via daemon config; see §8.4)
- Embedding model offline pre-bundling — first run downloads embedding model (size unverified;
  empirically ~80–100MB for all-MiniLM-L6-v2)
- Multi-user / shared daemon mode
- Audit log implementation — design hook reserved, deferred
- Cross-harness credential import (`Request::ImportExternalCreds`) — does not exist in current
  jcode protocol; if shipped in v1, must be implemented as a subprocess invocation of `jcode`
  CLI wrapping `src/import.rs`. **Decision: defer credential import to v2; v1 reads only what
  the user explicitly logs in via `jcode login`.**

## 4. Architecture

```
┌─────────────────── Agent Zero (Python) ──────────────────┐
│                                                          │
│  WebUI                          Agent loop (agent.py)    │
│  ├ chat panel                   ├ monologue()            │
│  ├ side panel ◄──┐              │   ├ extension hooks    │
│  ├ settings      │              │   └ tool dispatch      │
│  └ notifications │              │                        │
│                  │              ▼                        │
│                  │  ┌─── usr/plugins/jcode_harness/ ───┐ │
│                  │  │                                  │ │
│                  │  │  hooks.py    install/upgrade     │ │
│                  │  │  helpers/    JcodeClient         │ │
│                  │  │  helpers/    DaemonSupervisor    │ │
│                  │  │  tools/      jcode_session +6    │ │
│                  │  │  extensions/python/              │ │
│                  │  │    monologue_start/  ◄── short-  │ │
│                  │  │       circuit for jcode_coder    │ │
│                  │  │  extensions/webui/               │ │
│                  │  │    side-panel-start/             │ │
│                  │  │    sidebar-quick-actions-…/      │ │
│                  │  │  agents/jcode_coder/agent.yaml   │ │
│                  │  │  webui/main.html                 │ │
│                  │  │  webui/config.html               │ │
│                  │  │  default_config.yaml             │ │
│                  │  │  plugin.yaml                     │ │
│                  │  └────────────┬─────────────────────┘ │
│                                  │ Unix socket            │
└──────────────────────────────────┼────────────────────────┘
                                   │ NDJSON: Request/ServerEvent
                                   ▼
┌──────────────── jcode serve daemon (Rust) ──────────────┐
│  socket: ~/.amplihack/jcode/jcode.sock (per-A0-instance)│
│                                                         │
│  Agent runtime ── 28 tools ── memory graph ── skills    │
│  Provider drivers ── Swarm coord ── Self-dev (gated)    │
│  ~/.jcode/{auth,sessions,memory,skills,builds}          │
└─────────────────────────────────────────────────────────┘
```

### 4.1 Daemon lifecycle

One `jcode serve` process per **A0 instance**, lazy-spawned on first tool invocation, kept alive
across A0 sessions. DaemonSupervisor enforces single-instance via flock'd PID file.

**A0 instance defined:** the absolute realpath of A0's process root directory (the parent
of `agent.py`), hashed (SHA-256, first 12 hex chars). This disambiguates dev vs prod installs on
the same user account, two Docker containers mounting the same `~/.amplihack/`, and concurrent
`python agent.py` runs from different checkouts. Per-instance directory:
`~/.amplihack/jcode/<instance-id>/` containing `socket`, `pid`, `logs/`, `client_instance.json`
(persistent client UUID for reload recovery — see §7.1).

User's external `jcode` CLI uses `~/.jcode/` directly while plugin uses its own private socket
under `~/.amplihack/jcode/<instance-id>/socket`. Memory graph, skills, and provider credentials
live in `~/.jcode/` and are shared across daemons (jcode reads/writes a single user data root).
Sessions started in plugin can be resumed from external `jcode` and vice versa via shared journal
files at `~/.jcode/sessions/`.

**Spawn command** (verified against `jcode/src/cli/args.rs`):

```
jcode --socket <abs-path> serve --owner-pid <a0-pid>
```

Notes:
- `--socket` is a top-level `Args` flag (args.rs:78), not a `Serve` subcommand flag.
- Gateway is **not** disabled by a CLI flag (no `--no-gateway` exists). Plugin disables it via
  config: write `[gateway] enabled = false` to a per-instance overlay config file at
  `~/.amplihack/jcode/<instance-id>/jcode-config.toml` and pass `JCODE_CONFIG=<path>` env to
  the spawn (jcode honors env-overlay per `src/config/config_file.rs`). If env-overlay is not
  supported by the installed jcode version, the daemon comes up with the gateway enabled but
  bound to localhost only; **plugin must additionally configure `[gateway] bind = "127.0.0.1:0"`
  to make port choice ephemeral and explicitly-zero documented in settings**.
- TUI is not started by `serve` (TUI is a `connect` invocation), so no `--no-tui` is needed.

**Multi-instance contention:** If a daemon already exists for the same instance-id (active PID,
0600 socket reachable), DaemonSupervisor reuses it. If the PID file references a dead PID or
foreign user, the file is moved to `.dead.<ts>` and a fresh daemon spawned. Two A0 instances on
**different** instance-ids run independent daemons; their sessions are isolated, and swarm
coordination only spans sessions inside a single daemon.

### 4.1.1 Docker awareness

A0 framework runtime is `/opt/venv-a0` (Docker convention from AGENTS.plugins.md §2). Plugin's
`hooks.py` runs there. The jcode daemon spawned by `hooks.py` inherits Docker's environment:

- `~/` resolves to the container user's home; if `~/.jcode/` and `~/.amplihack/` are not on
  mounted volumes, all state is ephemeral. Plugin install **logs a warning toast** when the
  resolved home directory is inside the container's writable layer (heuristic: `df -T` reports
  `overlay`).
- The downloaded jcode binary must match the container's libc/architecture, not the host. Plugin
  uses `uname -m` plus `getconf GNU_LIBC_VERSION` (Linux) or `sysctl hw.optional.arm64` (macOS,
  detects Rosetta correctly) to select the release asset.
- Network access from inside the container is the user's responsibility; plugin install fails
  loudly if `api.github.com` is unreachable.

### 4.2 Working-directory scoping

Every `Subscribe` request carries `working_dir` (jcode protocol). jcode's memory graph is keyed by
the hash of this path; switching to a different repo automatically switches memory context.
Plugin passes A0's project root as `working_dir`.

### 4.3 Self-dev gating

On plugin enable, `cargo --version` is probed. Result stored as
`features.self_dev` config flag. The `jcode_self_dev` tool checks this flag at registration time
and self-omits when missing. Per the non-technical-user constraint, the plugin never auto-installs
Rust; it surfaces a one-line settings notice with the rustup URL when self-dev is desired but
unavailable.

## 5. Components

Each component named with file path, responsibility, and key API.

### 5.1 Manifest — `plugin.yaml`

```yaml
name: jcode_harness
title: jcode Coding Harness
description: Embeds the jcode coding agent (memory graph, skills, swarm, 28 tools) into Agent Zero.
version: 0.1.0
settings_sections: [agent, developer, external]
per_project_config: true
per_agent_config: true
always_enabled: false
```

### 5.2 Install/upgrade — `hooks.py`

Functions called by A0 framework runtime (`/opt/venv-a0`) per AGENTS.plugins.md §2:

- `install()` — runs after plugin copy. Detect existing `jcode` on PATH; else fetch latest
  release asset matching host architecture (see §4.1.1) from
  `api.github.com/repos/1jehuang/jcode/releases/latest`, extract to `~/.jcode/builds/stable/jcode`,
  verify SHA-256 against the release's `SHA256SUMS` file (verified at `.github/workflows/release.yml`
  in the jcode repo — CI generates and uploads SHA256SUMS per release), smoke-test with
  `jcode --version`. Probe `cargo --version` to set `self_dev_available`.
  Run provider importer once. All progress reported via A0 notification API
  (`AgentNotification.success/error/info`).
- `pre_update()` — graceful daemon stop before plugin code is replaced (see §5.3 stop method).

**Plugin removal:** AGENTS.plugins.md §2 lists only `install()` and `pre_update()` as guaranteed
hooks. Cleanup runs from a manual `execute.py`-driven path: when user clicks "Uninstall and clean
data" in plugin UI, `execute.py` stops the daemon, deletes
`~/.amplihack/jcode/<instance-id>/`, and optionally (with explicit checkbox) deletes
`~/.jcode/`. Bare plugin removal via A0's plugin manager only deletes `usr/plugins/jcode_harness/`;
the daemon process exits when its socket FD closes (orphaned, but still graceful).

Permission scope: read/write `~/.jcode/builds/`, write `~/.amplihack/jcode/<instance-id>/`,
network out to `api.github.com` plus release CDN. No system modification beyond owned paths.

### 5.2.1 Python import discipline

Per AGENTS.plugins.md §2 ("Python import rule for user plugins"), all plugin-internal imports
**must** use the fully qualified `usr.plugins.jcode_harness...` package path:

```python
# Good (DO):
from usr.plugins.jcode_harness.helpers.daemon import DaemonSupervisor
from usr.plugins.jcode_harness.helpers.jcode_client import JcodeClient
import usr.plugins.jcode_harness.helpers.protocol as proto

# Forbidden (DON'T):
import sys; sys.path.insert(0, ...)   # no path hacks
from helpers.daemon import DaemonSupervisor   # no relative-style top-level
from plugins.jcode_harness.helpers.daemon import …   # no symlink-based imports
```

Tools, extensions, and helpers all follow this rule. Code review enforces.

### 5.3 DaemonSupervisor — `helpers/daemon.py`

Lazy-started, single-process-per-A0-instance.

- `ensure_running(working_dir) -> str` — spawns `jcode --socket <path> serve --owner-pid <a0_pid>`
  with `JCODE_CONFIG=<overlay>` env (overlay disables gateway; see §4.1) if not alive (PID file
  at `~/.amplihack/jcode/<instance-id>/pid`); returns socket path.
- `is_running() -> bool` — flock check on PID file plus socket reachability plus 0600 perm check.
- `stop()` — close all client sockets, then SIGTERM the daemon process (no `Request::Shutdown`
  exists in protocol; verified absent from `crates/jcode-protocol/src/lib.rs`). Wait up to 5s for
  exit, then SIGKILL.
- `health() -> dict` — uptime, session count, last error.
- `restart()` — for upgrade flow; calls `stop()` then `ensure_running()`.

State under `~/.amplihack/jcode/<instance-id>/`: `socket`, `pid`, `logs/`, `last-error`,
`client_instance.json` (persisted client UUID — see §7.1). Logs streamed to A0 logging via
`python/helpers/log.py`.

### 5.4 JcodeClient — `helpers/jcode_client.py`

Pure-Python async client speaking jcode's NDJSON wire format (definitions:
`jcode/crates/jcode-protocol/src/lib.rs`).

Field name `allow_session_takeover` (verified, `lib.rs:155, 184`) — not the shorter
`allow_takeover` originally drafted.

```python
class JcodeClient:
    async def connect(self, socket_path: str) -> None
    async def subscribe(self, working_dir: str, target_session_id: str | None,
                        client_instance_id: str, allow_session_takeover: bool) -> SessionId
    async def send_message(self, content: str, images: list[bytes] = ()) -> int
    async def soft_interrupt(self, content: str, urgent: bool = False) -> None
    async def cancel_soft_interrupts(self) -> None
    async def cancel(self) -> None
    async def background_tool(self, tool_id: str) -> None
    async def stdin_response(self, request_id: str, input: str) -> None
    async def resume_session(self, session_id: str) -> None
    async def get_history(self) -> History
    async def ping(self) -> Pong
    async def events(self) -> AsyncIterator[ServerEvent]
    async def close(self) -> None
```

Note: `Request::ListSessions` does **not** exist in the jcode protocol. Cross-harness session
listing (§6.3) is implemented by subscribing to a no-op session and invoking the
`session_search` agent tool inside that session via a synthesized `Message`. Alternative: invoke
`jcode session list --json` as a subprocess. The §6.3 redesign uses the subprocess path because
it doesn't require a daemon connection at all — see §6.3.

Implementation:

- `asyncio.open_unix_connection(socket_path)`; Windows uses `pywin32` named pipes.
- Reader task yields parsed `ServerEvent` dataclasses (mirror Rust enum names).
- Writer: `writer.write(json.dumps(req).encode() + b"\n")`.
- Reconnect: exponential backoff 1s→30s on socket drop; auto-resubscribe with `client_instance_id`
  to recover the session.
- Forward-compat: unknown event variants pass through as `UnknownEvent { type, raw }`, logged but
  never crash the connection.

### 5.5 Provider importer — `helpers/provider_import.py`

Runs once on install and on settings save. Reads A0's `models.py` and `conf/model_providers.yaml`
plus user-configured API keys, registers each one as a jcode `openai-compatible` profile via
`jcode provider add <name> --base-url <url> --model <id> --api-key-env <ENV_VAR_NAME>` with the
key transiently injected into the spawned process's environment by the plugin (never argv,
never persisted).

- `--model` is **required** by `jcode provider add` (`src/cli/args.rs:447-448`); plugin uses A0's
  configured default model id for that provider, or the first model from A0's
  `model_providers.yaml` model list.
- Maps each A0 provider with a key to one named jcode profile. Naming convention:
  `_a0_imported_<provider_id>` (leading underscore + `_a0_imported_` prefix). Plugin checks for
  collisions before write via `jcode provider list --json`; a colliding name owned by the user
  (no prefix) blocks the import with a toast and a "Choose alternate name" UI affordance.
  `--overwrite` is only used against the plugin's own prefix-matched profiles.
- Does not touch jcode OAuth credentials at `~/.jcode/auth*.json` — user creates those via plugin
  UI.
- Idempotent for plugin-owned profiles.
- Drift detection: when A0 keys change, plugin offers re-sync via toast + WebUI button.

**Disabling `auto_import_a0_keys` after install:** existing `_a0_imported_*` profiles persist
in `~/.config/jcode/`. The plugin settings page exposes a "Purge imported profiles" button that
invokes `jcode provider remove` for each prefixed profile. Without an explicit purge, profiles
remain functional until manually removed.

Keys never appear in command-line arguments (always env-var passthrough), never in shell
history, never logged. Plugin generates a unique env var name per profile
(`JCODE_PROVIDER_<UPPER_NAME>_API_KEY`), sets it only in the child subprocess's environment via
`subprocess.run(..., env=...)`, and never writes it to its own process env. Child process env
under `/proc/<pid>/environ` (Linux) or via `ps -E` (macOS, BSD) is owner-readable only.

> **Note (verified 2026-05-05 against jcode v0.11.10):** the originally drafted `--api-key-stdin`
> flag does not exist in jcode's CLI. The `--api-key-env <NAME>` flag does. The env-var pattern
> above achieves equivalent security: key never appears in argv (so not in `ps aux`) and never
> persists in shell history. See spike `docs/superpowers/spikes/2026-05-05-spike-provider-add-errors.md`.

### 5.6 Tools (Python, in `tools/`)

Subclasses of A0's `Tool` (`helpers/tool.py:17`). Each maps to a JcodeClient call. Streaming
progress via `await self.set_progress(...)` translates `TextDelta`/`ToolStart`/`ToolDone` events
into A0's progress UI.

| Tool | Purpose | jcode IPC |
|---|---|---|
| `jcode_session` | Open bounded coding-task session, stream until done | `Subscribe` + `Message` loop |
| `jcode_grep` | agentgrep semantic+structure-aware grep | session-less RPC: short-lived subscribe |
| `jcode_memory` | `action: remember/recall/search/forget/tag/link` | dispatches `memory_manage` inside ephemeral session |
| `jcode_skill` | `action: load/list/reload/read` | dispatches `skill_manage` |
| `jcode_resume` | List + resume cross-harness sessions | subprocess `jcode session list --json` (or fallback; see §6.3 + §11 spike) + `Subscribe { target_session_id }` |
| `jcode_swarm_msg` | DM / broadcast / channel-send | `CommMessage`, `CommShare`, `CommRead` |
| `jcode_self_dev` | Trigger self-modification cycle (gated) | dispatches selfdev session |

### 5.7 Extensions

- `extensions/python/agent_init/jcode_register.py` — register tools, ensure daemon running on
  agent init.
- `extensions/python/monologue_start/jcode_warmup.py` — when profile is `jcode_coder`, calls
  `DaemonSupervisor.ensure_running()` with the agent's working directory so the daemon is hot
  before the user's first turn. Does **not** short-circuit the loop (true full-takeover is v2).

**Removed for v1:** the originally planned `jcode_takeover.py` extension that set
`loop_data.result` is dropped because A0's `LoopData` has no short-circuit field
(`agent.py:326-341`) and `before_main_llm_call` (`agent.py:404`) has no early-exit hook. v2
work item.

The implicit `_functions/<module>/<qualname>/<start|end>/` extension layout (AGENTS.plugins.md
§2) is **not used** in v1 because v1 doesn't intercept any A0 internal call sites. If a future
version needs to wrap (for example) `Agent.process_tools`, the qualname must be verified against
the live `Agent` class in `agent.py` before adding such an extension.

### 5.8 WebUI

- `webui/main.html` — full plugin page: session list (resumable across harnesses), provider login
  buttons, daemon status, memory graph viewer.
- `webui/config.html` — settings: binary path override, daemon socket path, swarm enabled,
  self-dev advanced toggle, provider import status.
- `extensions/webui/side-panel-start/jcode_panel.html` — render jcode `SidePanel*` events (file
  diff, mermaid) using A0's existing side-panel surface.
- `extensions/webui/sidebar-quick-actions-main-start/jcode_quick.html` — "New jcode session" and
  "Resume" buttons.
- All errors and successes routed through A0's `notificationStore.frontendError/Success/Warning`
  per AGENTS.plugins.md §3, never inline error boxes.

### 5.9 Agent profile — `agents/jcode_coder/agent.yaml`

v1 ships a **prompt-routing** profile, not a loop-replacing profile. The system prompt strongly
favors `jcode_session` for any non-trivial coding work, so the user perceives jcode-driven
behavior even though A0's loop still runs:

```yaml
title: jcode Coder
description: Routes coding work through the jcode harness via the jcode_session tool.
context: |
  For any non-trivial coding task — refactoring, multi-file edits, debugging, code search,
  test writing — call jcode_session with the task description. The jcode harness has memory
  graph, skill auto-injection, agentgrep, and 28 native tools that outperform direct edits
  for sustained coding work. Use direct tools only for one-line changes or chat replies.
prompts: {}
```

True loop-replacing full-takeover is deferred to v2 pending an upstream A0 change to
`LoopData`.

### 5.10 Config schema — `default_config.yaml`

```yaml
binary:
  path: ""
  auto_update: true
daemon:
  mode: per_project
  socket_path: ""
features:
  swarm: true
  self_dev: false
  cross_harness_resume: true
  cross_harness_import: false
providers:
  auto_import_a0_keys: true
  oauth_subscriptions: []
ui:
  side_panel: true
  mermaid: true
  notifications: true
safety_mode: default
```

## 6. Data flow

### 6.1 Embedded session

A0 agent calls `jcode_session(task=...)`. Tool calls
`DaemonSupervisor.ensure_running()`, then `JcodeClient.connect`/`subscribe` with a fresh
`client_instance_id`, sends a `Message`, iterates `client.events()`. Streamed events map to A0
progress hooks: `TextDelta` to `set_progress`, `ToolStart`/`ToolInput`/`ToolDone` to running-tool
indicators, `MemoryInjected` to side-panel chip, `Compaction` with `cache_cold:true` to a warning
toast, `MessageEnd` and `Done` close the loop. The final assistant text is returned as the tool
result and added to A0 history.

### 6.2 Full-takeover (deferred to v2)

Originally specified as a `monologue_start` extension that sets `loop_data.result` and a
sentinel checked by `before_main_llm_call` to skip A0's LLM call. **Not implementable in v1:**
A0's `LoopData` (`agent.py:326-341`) has no `result` field and `before_main_llm_call`
(`agent.py:404`) has no early-exit hook. Implementing this requires modifying A0 itself.

v1 substitutes a **prompt-routing profile** (§5.9): A0's loop still runs, but the profile's
system prompt directs the model to call `jcode_session` for coding work. This achieves ~80% of
the perceived UX (jcode handles the actual coding work, with native memory/skills/swarm) without
the framework change.

**v2 plan:**
1. Open upstream PR to A0 adding `LoopData.short_circuit: bool` and an early-exit check in
   `before_main_llm_call`.
2. Once merged + version-pinned in plugin's `default_config.yaml` minimum-A0-version, ship the
   `monologue_start` short-circuit extension.
3. Sticky session id stored in `~/.amplihack/jcode/<instance-id>/sessions/<a0_ctx_id>.json` so
   multi-turn conversations resume the same jcode session.

Soft-interrupt mapping (works in v1 for embedded sessions and v2 for full-takeover):

- A0 cancel button (single press) → `Request::SoftInterrupt { content, urgent: false }`, jcode
  injects message at safe injection point **D** (after all tools complete in current batch,
  before next API call — the default safe site per `jcode/docs/SOFT_INTERRUPT.md` §"Injection
  Points").
- A0 cancel button (double press / hard stop) → `Request::Cancel`, jcode interrupts cleanly.

Memory and skill auto-injection are native to embedded sessions: jcode's memory_agent computes
per-turn embeddings and cascade retrieval, emits `MemoryInjected` events; skill registry
auto-loads on similarity match. Both visible to plugin via `ServerEvent::MemoryInjected` and
the side-panel UI.

### 6.3 Cross-harness resume

`Request::ListSessions` does **not** exist in the jcode protocol. v1 implementation uses a
subprocess invocation of `jcode session list --json` (CLI subcommand backed by
`src/import.rs`). Round-trip pseudocode:

```
WebUI → GET /api/plugins/jcode_harness/list_sessions
    api/list_sessions.py:
        → subprocess.run(["jcode", "session", "list", "--json"], capture)
        → parse JSON: list of {id, title, provider_key, working_dir, updated_at}
        → return JSON to WebUI
WebUI renders list grouped by provider_key (claude-code, codex, opencode, pi, jcode)
User clicks a session
WebUI → POST /api/plugins/jcode_harness/resume_session {session_id}
    api/resume_session.py:
        → DaemonSupervisor.ensure_running()
        → JcodeClient.subscribe(working_dir, target_session_id, allow_session_takeover=True)
        → receive ServerEvent::History with full message log + provider_session_id
        → backfill A0 chat
    Subsequent turns use the embedded jcode_session tool against the resumed session_id;
    upstream provider cache stays warm via the round-tripped provider_session_id.
```

**Verified:** `provider_session_id` exists at `src/session.rs:77` and round-trips through
`src/import.rs:864`. Cache-warmth claim is upstream-provider-dependent and remains an
unverified-but-plausible assumption (see §11 spike).

### 6.4 Event ↔ notification mapping

| jcode `ServerEvent` | A0 surface |
|---|---|
| `Compaction { cache_cold: true }` | `frontendWarning("Cache went cold — extra tokens this turn")` |
| `Interrupted` | `frontendInfo("Turn cancelled")` |
| `Reloading { new_socket }` | DaemonSupervisor reconnects silently; toast if >2s |
| `StdinRequest { is_password }` | A0 password modal; response via `Request::StdinResponse` |
| `MemoryInjected` | side-panel chip "+N memories" with computed-age timestamp |
| `SwarmStatus { members }` | swarm widget in side panel |
| daemon crash / socket EOF | `frontendError("jcode daemon stopped — restarting…")`, auto-restart, retry last message |

## 7. Error handling and edge cases

### 7.1 Daemon lifecycle failures

- Binary missing: surface "click to reinstall" toast that calls `hooks.install()` repair path.
- Crash mid-turn: reader sees EOF; supervisor respawns; client auto-resubscribes with
  `client_instance_id`; replay last user message; toast `frontendWarning`.
- Hung (>120s no Pong keepalive): send `Cancel`; if no response in 5s, SIGTERM and restart.
- Stale PID file: move to `.dead.<ts>`, never kill foreign PIDs.
- Two A0 instances on the **same instance-id** (rare; same checkout, same process root):
  multi-client to one daemon, supported by jcode protocol. Two A0 instances on **different
  instance-ids** (different checkouts, dev vs prod, two Docker containers): each runs its own
  daemon; their swarm sessions are isolated. This contradicts an earlier draft of this section
  and supersedes it.
- `Reloading { new_socket }`: variant exists at `lib.rs:945`; reconnect contract specifics are a
  v1 spike (§11). Defensive implementation: client closes current connection, waits 100ms, opens
  new socket, resubscribes with same `client_instance_id`.
- Plugin disabled mid-turn: `Cancel` plus stop-via-SIGTERM; persist `(session_id,
  client_instance_id)` to `~/.amplihack/jcode/<instance-id>/sessions/<a0_ctx_id>.json` so
  re-enable resumes.

**Plugin reload (Python module reloaded without process restart):** A0's plugin cache may
invalidate the plugin module (AGENTS.plugins.md §2). When this happens, in-memory
`client_instance_id` UUIDs are lost. Defensive design: persist the UUID per A0 conversation in
`~/.amplihack/jcode/<instance-id>/sessions/<a0_ctx_id>.json`. On reload, JcodeClient reads the
file and resubscribes with the persisted UUID, allowing jcode to reattach the existing session.

**Plugin reload during active stream:** the in-flight reader task is cancelled when the module
unloads. Recovery uses `client_instance_id` resubscribe; the current turn may emit a duplicate
`Done` event on resubscribe — client deduplicates by event id.

### 7.2 Wire-protocol failures

- Broken pipe: reconnect with exp backoff 1s→30s.
- Malformed JSON: log and skip; do not drop connection.
- Unknown event variant: `UnknownEvent` fallback; log; never crash.
- Wire-format drift: dataclasses ignore extra fields; plugin pins a minimum jcode version in
  `default_config.yaml`.

### 7.3 Provider/auth failures

- OAuth token expired: WebUI button calls `jcode login --provider claude --print-auth-url --json`,
  plugin polls for completion.
- Rate limit: toast plus auto-retry after `retry_after`; suggest `/account` switch.
- A0 keys changed: re-run provider importer on settings save, toast confirmation.
- Cross-harness import permission denied: modal asking to enable in settings, per-source consent.

### 7.4 Tool execution edge cases

- `StdinRequest`: A0 modal; password type uses `<input type="password">`, value never logged;
  timeout 5min cancels tool.
- Long-running tool: `BackgroundTool` request shows "Running in background" badge, allows
  foregrounding via WebUI.
- Output truncation: trust jcode's existing 90% budget threshold; do not double-truncate.
- Browser tool invoked: out of scope v1; plugin returns `frontendInfo` explaining feature is
  deferred.
- Self-dev without Rust: tool re-checks at invocation; clean error pointing to rustup URL.
- Tool image: forward `ToolImage` blocks to A0 chat as inline images.

### 7.5 Memory/skill edge cases

- Graph corruption: jcode rebuilds from `~/.jcode/memory/embeddings/`; catastrophic case offers
  reset button.
- Pipeline lag (results 1 turn behind by design): `computed_age_ms` shown when >5000ms so
  freshness is visible.
- Skill load fails: jcode logs and skips; plugin surfaces `frontendWarning` with file path.
- Embedding model not yet downloaded: first turn slow; toast "Downloading embedding model…
  (~85MB, one-time)".
- Low-RAM mode: config flag spawns daemon without embeddings; memory falls back to recency-only.

### 7.6 Swarm edge cases

- Message to non-existent agent: error includes recipient list.
- File-shift: `FileShift` event surfaces in side panel with diff preview.
- Member crash: `SwarmStatus` drops member; coordinator informed via `CommMessage`.

### 7.7 Self-dev edge cases

- `cargo` disappears post-install: tool re-checks and errors cleanly.
- Self-dev breaks binary: jcode rolls back to `~/.jcode/builds/versions/<previous>/`; plugin
  warns.
- Self-dev triggered while session active: rejected with "requires idle daemon".

### 7.8 Session/storage edge cases

- Journal corruption: jcode auto-runs `detect_crashed_sessions()` plus `recover_crashed_sessions()`
  at start; plugin surfaces count.
- Resume with missing creds: error with login button.
- Project moved/renamed: old memory persists at old hash; plugin offers "Migrate memory" if both
  paths detected.
- Disk full: graceful error, halt new sessions, hint at usage.

### 7.9 Cancellation discipline

- Single-stop with text: `Request::SoftInterrupt`, injected at safe point **D** (post-tool-batch,
  pre-next-API-call; see `jcode/docs/SOFT_INTERRUPT.md`). No cancellation. User's redirect lands
  at the next safe boundary.
- Double-stop: hard `Request::Cancel`. In-flight tools allowed to finalize. `Interrupted` event.
- Network drop during turn: treated as hard cancel, last received state persisted.

## 8. Security and permissions

### 8.1 Trust boundaries

Plugin Python code runs in A0 framework runtime (`/opt/venv-a0`). jcode daemon runs as same OS
user, separate process. Plugin does not elevate jcode beyond A0's user account. No setuid, no
network ports, no Docker break-out.

### 8.2 Credential handling

- jcode OAuth tokens (`~/.jcode/auth*.json`, 0600): jcode-managed, plugin reads only via IPC.
- jcode API keys (`~/.config/jcode/<provider>.env`, 0600): plugin writes only via
  `jcode provider add --api-key-env <NAME>` with `env=` injection in the subprocess call.
- Cross-harness imports (`~/.claude/.credentials.json` etc.): jcode reads them, plugin doesn't
  touch.
- A0 LiteLLM keys: plugin reads at import time, injects into a uniquely named env var visible
  only to the spawned `jcode provider add` subprocess (`subprocess.run(..., env={**os.environ,
  env_var: key})`), never logs.
- Session journal (`~/.jcode/sessions/<id>/`, 0600): plugin reads via IPC `History` event, redacts
  in info-level logs.

Plugin must never write keys to plugin config files, toast messages, log lines, or error
responses; never use `--api-key VALUE` argument form (visible in `ps`); add plugin `config.json`
to `.gitignore` as part of install.

### 8.3 Cross-harness import opt-in (v2 design — deferred)

**Cross-harness credential import is deferred to v2** per §3.2; the protocol requests
`Request::ImportExternalCreds` and `Request::ForgetExternalCreds` referenced in earlier drafts
do not exist in the jcode protocol. v1 only reads credentials the user explicitly creates via
`jcode login` flows from the plugin UI.

The consent model below is reserved for v2 implementation:

1. Off by default in `default_config.yaml` (`features.cross_harness_import: false`).
2. When enabled via WebUI: modal lists exact files that would be read with size and last-modified
   timestamps.
3. User clicks "Allow" per source (granular, not all-or-nothing).
4. Plugin writes consent record to `~/.amplihack/jcode/<instance-id>/import_consent.json`.
5. v2 implementation either uses a new jcode protocol request, a `jcode import` CLI subcommand,
   or a direct subprocess against `src/import.rs`-equivalent bindings.
6. On future re-import, consent record is consulted; if file path or hash differs, re-prompt.

Revocation (v2): settings page button deletes consent record and triggers credential purge via
the chosen v2 mechanism.

### 8.4 Socket and file permissions

**POSIX (Linux/macOS):**

```
~/.amplihack/jcode/<instance-id>/socket           srw-------  (0600)
~/.amplihack/jcode/<instance-id>/pid              -rw-------  (0600)
~/.amplihack/jcode/<instance-id>/client_instance.json  -rw-------  (0600)
~/.amplihack/jcode/<instance-id>/logs/            drwx------  (0700)
```

DaemonSupervisor refuses sockets looser than 0600 (re-spawns daemon), refuses stale PID files
owned by other users. Logs rotated daily, retain 7 days, redact request bodies (only event names
and sizes at info level; full content only at debug with explicit `JCODE_LOG_PAYLOADS=1`).

**Windows (per `jcode/docs/WINDOWS.md`):**

NTFS has no POSIX 0600. jcode uses **named pipes** instead of Unix sockets on Windows. Plugin
configures the named pipe with an ACL restricting access to the current user's SID:

```
\\.\pipe\jcode-<instance-id>      ACL: current-user SID only
%LOCALAPPDATA%\amplihack\jcode\<instance-id>\pid                 (Owner: current-user)
%LOCALAPPDATA%\amplihack\jcode\<instance-id>\client_instance.json
%LOCALAPPDATA%\amplihack\jcode\<instance-id>\logs\
```

DaemonSupervisor verifies pipe ACL at attach time using `pywin32`'s
`win32security.GetSecurityInfo`; if the pipe is accessible by anyone other than the current user,
the daemon is killed and respawned.

**Gateway disabled via daemon config**, not CLI flag (no `--no-gateway` exists). Per-instance
overlay config at `~/.amplihack/jcode/<instance-id>/jcode-config.toml` sets:

```toml
[gateway]
enabled = false
```

passed to spawn via `JCODE_CONFIG=<path>` env. Plugin never opens a network port. If the
installed jcode version doesn't honor `[gateway] enabled = false`, the daemon comes up with the
gateway listening on `127.0.0.1:0` (ephemeral); plugin documents this and surfaces a warning
toast on detect.

### 8.5 Tool sandboxing

jcode's existing `src/safety.rs` enforces bash allowlist/denylist, file-write confirmations, and
network gating. Plugin inherits these and exposes a `safety_mode` setting:

| Mode | Behavior |
|---|---|
| `default` | jcode default — ask before destructive ops |
| `paranoid` | All FS writes outside `working_dir` blocked, network confirmations |
| `yolo` | Hidden behind dev settings, sticky banner, warning toast on enable |

Plugin's `monologue_start` extension passes `safety_mode` through `Subscribe.config`.

`StdinRequest` sensitive input handled via password modal; value never logged, transmitted only
over the local Unix socket, cleared from memory after `Request::StdinResponse`.

### 8.6 Plugin install network trust

`hooks.py install()` downloads only from `github.com/1jehuang/jcode/releases/...`, verifies SHA-256
against the release's `SHA256SUMS`, refuses install on mismatch. Records install metadata in
`~/.amplihack/jcode/install.json`. Auto-update uses the same verification chain. Never auto-runs
`cargo build` (would be code-exec on update). User-supplied binary paths are trusted as
user-managed; plugin only smoke-tests `--version`.

### 8.7 Plugin removal hygiene

AGENTS.plugins.md §2 only guarantees `install()` and `pre_update()` hooks. Cleanup runs from a
manual `execute.py`-driven path (see §5.2 "Plugin removal") rather than an `uninstall()` hook.

The `execute.py`-driven cleanup:

- Stops the daemon via `DaemonSupervisor.stop()` (SIGTERM, SIGKILL fallback).
- Removes `~/.amplihack/jcode/<instance-id>/`.
- Leaves `~/.jcode/` user data alone unless the user opts in via the cleanup confirmation modal.
- Does not touch `~/.cargo/`, `~/.claude/`, `~/.codex/`.

If the user removes the plugin via A0's plugin manager **without** running cleanup, the daemon
process orphans cleanly when its socket FD closes; `~/.amplihack/jcode/` remains on disk. After
cleanup, the user's external `jcode` CLI keeps working with `~/.jcode/` unchanged.

### 8.8 Threat model summary

| Threat | Mitigation |
|---|---|
| Malicious plugin update steals creds | Plugin doesn't store creds; daemon update SHA-256 verified; user can pin version |
| Prompt injection causes exfiltration | jcode tool safety; `paranoid` mode; bash allowlist; network calls require explicit network-capable tool |
| Compromised daemon process | Same trust boundary as user; loss = jcode-only data; uninstall containable |
| Local privilege escalation via socket | 0600 perms, PID ownership check |
| Cross-A0-instance leakage | Per-A0-instance daemon (per Q5b) — isolated socket and logs |
| Self-dev rebuilds malicious binary | Gated behind cargo detection plus settings opt-in; rollback artifacts in `~/.jcode/builds/versions/`; original `stable` preserved |
| WebSocket gateway accidentally exposed | `JCODE_CONFIG` overlay sets `[gateway] enabled = false`; explicit setting required to enable |

### 8.9 Compliance lockdown profile

`safety_mode: paranoid` + `cross_harness_import: false` + `self_dev: false` + `auto_update: false`
yields a locked-down profile. Settings can be marked read-only via A0's project-level config
(`.a0proj/`) so users can't loosen. Audit log of plugin actions reserved at
`~/.amplihack/jcode/audit.jsonl` (append-only; implementation deferred to v2).

## 9. Testing

### 9.1 Layers

- Unit (Python): JcodeClient JSON encode/decode, DaemonSupervisor state machine, provider importer
  logic, tool arg validation. `pytest` + `pytest-asyncio`.
- Wire-protocol contract: golden fixtures (`tests/fixtures/protocol/*.jsonl`) replayed through
  client.
- Integration: spawn real `jcode serve` in test fixture, run scripted conversations, assert event
  order. CI downloads pinned jcode release.
- Tool-level: each plugin tool invoked end-to-end against real daemon.
- Extension hook: `monologue_start` short-circuits A0 loop, history mirrors jcode events.
- WebUI: side-panel rendering, settings save, session list. Playwright via `playwright-skill`.
- Performance: benchmark suite mirroring jcode's README metrics.
- Security: cred handling smoke tests, socket perms, sandbox attempts. Custom plus `bandit`.

### 9.2 Wire-protocol contract fixtures

```
tests/fixtures/protocol/
├── subscribe_handshake.jsonl
├── simple_message.jsonl
├── tool_call.jsonl
├── soft_interrupt.jsonl
├── memory_injection.jsonl
├── compaction.jsonl
├── cross_harness_resume.jsonl
└── stdin_request.jsonl
```

When jcode releases new version, contract tests run against new daemon. Failures = breaking
change, plugin update required before pin bump.

### 9.3 Critical test cases (must-pass for v1)

- Daemon lifecycle: spawns on first `ensure_running`, survives plugin reload, respawns on crash
  with auto-resubscribe to same session_id, `pre_update` graceful shutdown, `uninstall` removes
  `~/.amplihack/jcode/` but leaves `~/.jcode/`.
- Embedded session: `jcode_session("hello")` streams text, returns final message, history
  captures result via `hist_add_tool_result`, streaming progress visible, cancel during stream
  stops generation cleanly. `MemoryInjected` events surface in side panel during multi-turn
  embedded conversations.
- Prompt-routing profile: with `jcode_coder` selected, A0's model consistently chooses
  `jcode_session` for non-trivial coding requests (verified by replay of canned prompts and
  inspection of selected tool calls).
- (v2) Full-takeover: profile triggers `monologue_start` short-circuit, A0 LLM never called,
  multi-turn persists same session_id. **Out of scope for v1; gated on upstream A0 PR.**
- Cross-harness resume: lists sessions from claude-code, codex, opencode, pi; resume restores
  history; `provider_session_id` round-trips.
- Memory + skills: `jcode_memory` round-trips remember/recall/search; persists across daemon
  restart; auto-injection fires in full-takeover; `/skill-name` activates manually.
- Provider import: A0 keys imported as openai-compatible profiles; `--api-key-env` verified via
  `/proc` inspection (no key in `ps`); idempotent re-import; OAuth login completes via
  `--print-auth-url`.
- Soft interrupt: single-stop with text injects at point D; double-stop hard cancels.
- Self-dev gating: `cargo` present registers tool; absent omits cleanly; rollback preserved.
- Security: socket 0600; no keys in `ps`; config gitignored; cross-harness import requires
  per-source consent; uninstall leaves `~/.jcode/`; `yolo` mode shows banner.
- Failure modes: crash mid-turn reconnect-and-retry; socket EOF backoff; `Reloading { new_socket }`
  follows transparently; disk full handled; malformed event survived.

### 9.4 Performance acceptance

| Metric | Target | Method |
|---|---|---|
| Time to first token (warm daemon) | <500ms | subscribe → first TextDelta |
| Daemon boot | <2s on M1, <4s on Linux x86_64 | time `ensure_running()` cold |
| RAM (idle, 1 session) | <200MB total | `ps -o rss` |
| Per-session RAM | ~12MB | 10-session benchmark |
| `jcode_grep` latency | <150ms p50 / <300ms p99 | repeated grep on agent-zero repo |
| WebUI initial load | <500ms | Playwright timing |

If plugin adds >10% overhead vs raw jcode: regression, optimize before ship.

## 10. Acceptance criteria (v1 done)

**Functional:**

- All seven tools work end-to-end with real jcode daemon.
- Embedded session mode demonstrated. (True full-takeover is v2.)
- Prompt-routing profile `jcode_coder` demonstrated to consistently route coding work through
  `jcode_session`.
- Cross-harness resume works for at least Claude Code, Codex, OpenCode, pi. Cache-warmth on
  resume is **downgrade-tolerant**: resume is acceptance-passing even when the upstream
  provider's KV cache has been evicted (jcode pays a one-time cache-creation cost; subsequent
  turns hit warm cache).
- Memory graph + skills function (auto + manual).
- Swarm messaging works between two A0 instances in same repo.
- Self-dev gracefully degrades when Rust absent.

**Non-functional:**

- All critical test cases pass in CI.
- Performance targets met on macOS arm64 + Linux x86_64.
- Security checks pass.
- Plugin installs in <30s on broadband.
- Plugin uninstalls cleanly with no orphaned files outside `~/.jcode/`.

**UX:**

- Errors surface as A0 notifications, never inline.
- Settings UI is fully operational from the plugin page.
- Cross-harness import is consent-gated and reversible.
- Daemon status, session count, last error visible in plugin WebUI.
- Self-dev advanced toggle hidden behind dev settings tab with warning copy.

**Documentation:**

- README with screenshots, install steps, supported providers.
- LICENSE at plugin root (required for Plugin Index per AGENTS.plugins.md §8).
- Settings reference: each `default_config.yaml` field documented.
- Troubleshooting page: daemon won't start, login flows, missing binary, cache cold warnings.

**Plugin Index ready:**

- `plugin.yaml` complete with required `name` matching folder.
- `index.yaml` drafted as separate community PR.
- Tags: `tools`, `coding`, `agent`, `memory`.
- Up to 5 screenshots.

## 11. Open risks and pre-implementation spikes

| Risk | Spike |
|---|---|
| jcode `Reloading { new_socket }` event field name and reconnect semantics | 0.5-day: trigger self-update mid-stream, observe variant + verify field is `new_socket` |
| `jcode session list --json` subcommand existence and output schema | 0.5-day: confirm subcommand exists in `src/cli/args.rs`; if absent, identify fallback (e.g., `jcode resume --json` no-id form, or direct read of `~/.jcode/sessions/` index) |
| `provider_session_id` round-trip actually keeps Claude/OpenAI cache warm | 1-day: instrument before/after, measure cache_read_input_tokens |
| `jcode provider add --json` exit-code/error-shape coverage | 0.5-day: enumerate failure modes (collision, bad URL, missing model, network error) |
| WebUI `x-extension` breakpoint fit for jcode `SidePanel*` events | 0.5-day: grep `x-extension`, prototype panel render |
| jcode honors `[gateway] enabled = false` in overlay config — fallback if not | 0.5-day: spawn daemon with overlay, verify via `lsof -i` |
| A0 `_functions/<module>/<qualname>` extension paths for any future intercept | 0.5-day if needed (not v1) |

Total v1 spikes: ~3.5 days. Findings fold into the implementation plan.

**v2 spike (gating full-takeover):**

| Risk | Spike |
|---|---|
| Upstream A0 PR adding `LoopData.short_circuit` lands and ships | Open PR, await merge, pin minimum A0 version in plugin |

## 12. References

- `jcode/README.md` — features overview
- `jcode/AGENTS.md` — workflow conventions
- `jcode/docs/SERVER_ARCHITECTURE.md` — daemon design
- `jcode/docs/MULTI_SESSION_CLIENT_ARCHITECTURE.md` — multi-client semantics
- `jcode/docs/SOFT_INTERRUPT.md` — interrupt injection points
- `jcode/docs/MEMORY_ARCHITECTURE.md` — memory graph + extraction
- `jcode/docs/SWARM_ARCHITECTURE.md` — swarm coordination
- `jcode/docs/AMBIENT_MODE.md` — deferred ambient design (v2 reference)
- `jcode/docs/SAFETY_SYSTEM.md` — sandboxing
- `jcode/crates/jcode-protocol/src/lib.rs` — wire format definitions
- `jcode/src/protocol.rs` — server-side protocol implementation
- `agent-zero/docs/agents/AGENTS.plugins.md` — A0 plugin contract
- `agent-zero/agent.py` — agent loop and extension points
- `agent-zero/helpers/extension.py`, `helpers/plugins.py`, `helpers/subagents.py`

## 13. Decisions captured during brainstorming

| ID | Decision | Rationale |
|---|---|---|
| Q1 | Hybrid bridge (option C) | Keeps Rust speed, preserves jcode features, clean Python plugin shell |
| Q2 | Embedded mode v1, full-takeover deferred to v2 | A0's `LoopData` has no short-circuit field; full-takeover requires upstream A0 change. v1 ships embedded + prompt-routing profile (§5.9) for ~80% of perceived UX. |
| Q3 | Scope: a + b + c + e + g + h + i; defer d, f, j; defer credential import | Browser, ambient, mobile out for v1; cross-harness credential import requires protocol additions, deferred. |
| Q4 | Hybrid provider import (III) — keys-only, OAuth via plugin UI | Single import on install + native OAuth via UI; preserves cross-harness resume |
| Q5 | Binary: PATH-aware install with download fallback (c); daemon: per-A0-instance (e); self-dev: cargo-detect, graceful degrade (j) | Matches non-tech UX while supporting power users |

## 14. Review iteration history

- **Iter 1 (2026-05-05):** Initial draft committed. External reviewer flagged: full-takeover not
  implementable as written, several CLI flags fictional (`--no-tui`, `--no-gateway`,
  `--socket` placement on subcommand), `Request::Shutdown`/`ListSessions`/`ImportExternalCreds`
  fictional, `allow_takeover` field name wrong, `provider add` missing required `--model`,
  Python import discipline missing, "A0 instance" undefined, Windows ACL semantics not
  addressed, plugin reload UUID loss not addressed, swarm scope contradiction.
- **Iter 2 (2026-05-05):** All critical and major issues addressed. Reviewer flagged consistency
  drift in untouched sections (§5.6 tool table, §8.3 import flow, §8.7 uninstall naming, §8.8
  threat-table mitigation, §9.3 full-takeover test) plus need for explicit `point D` definition
  and a spike on `jcode session list --json` subcommand existence.
- **Iter 3 (2026-05-05):** Consistency drift swept. Spike list expanded. Cache-warmth claim
  downgraded to tolerant. SHA256SUMS source linked. Ready for user review.
- **Iter 4 (2026-05-05):** All 9 Chunk 0 spikes complete (5 verified, 2 daemon-tested, 2
  deferred with defensive plans). Spec §8.2 security model updated: `--api-key-stdin` (which
  does not exist) replaced by `--api-key-env` env-var pattern with same security guarantee
  (key never in argv/shell-history/logs; env var is private to parent→child spawn). See
  spike findings at `docs/superpowers/spikes/`. Other findings folded into plan iter 2 rather
  than spec — spec describes desired behavior; plan describes how to achieve it given the
  actual jcode v0.11.10 CLI surface.
- **Iter 4 (2026-05-05):** Empirical verification against jcode v0.11.10 binary. §5.5, §8.2
  rewritten: `--api-key-stdin` flag does not exist in jcode CLI; switched security model to
  `--api-key-env` with private env-var injection per spawn. Equivalent argv-protection
  guarantee preserved. Spikes 0.2/0.4/0.6/0.8/0.9 verified, 0.1/0.3/0.5 deferred to
  integration phase with concrete plans, see `docs/superpowers/spikes/`.
