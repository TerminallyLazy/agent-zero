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
- The IPC wire format is line-delimited JSON (`jcode/src/protocol.rs:1412-1421`) — trivially
  consumable from Python with `asyncio.open_unix_connection`. No SDK or Rust FFI required.

Two interaction modes coexist:

1. **Embedded session (default).** A0's agent loop runs normally. A `jcode_session` tool opens a
   bounded jcode session per coding task, streams events back into A0 chat, returns the final
   assistant message as the tool result. A0 supervises start/stop.
2. **Full-takeover (opt-in via agent profile `jcode_coder`).** The plugin's `monologue_start`
   extension short-circuits A0's loop: a sticky jcode session owns the conversation, A0 acts as
   chat shell. Memory, skills, swarm coordination, and ambient (when enabled) all run native
   inside jcode.

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

- Browser tool (Firefox Agent Bridge — separate native binary install, deferred)
- Ambient mode background cycles (long-lived process lifecycle, deferred to v2)
- iOS / mobile clients (per user direction)
- WebSocket gateway exposure (security: keeps plugin daemon socket-only)
- Native `LoopData.short_circuit` field — v1 uses a sentinel-on-`loop_data.result` workaround
- Embedding model offline pre-bundling — first run downloads ~85MB
- Multi-user / shared daemon mode
- Audit log implementation — design hook reserved, deferred

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

One `jcode serve` process per A0 instance, lazy-spawned on first tool invocation, kept alive
across A0 sessions. Socket under `~/.amplihack/jcode/jcode.sock` (or `.a0proj/jcode/jcode.sock`
when project-scoped). DaemonSupervisor enforces single-instance via flock'd PID file.

Multi-A0-instance isolation: each A0 install gets its own daemon, sockets, and logs. No cross-talk.

User's external `jcode` CLI is not affected — it uses `~/.jcode/` directly while plugin uses its
own private socket. Memory graph, skills, and provider credentials are shared (same `~/.jcode/`
data root), so a session started in plugin can be resumed from external `jcode` and vice versa.

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

Three exported functions called by A0 framework runtime (`/opt/venv-a0`):

- `install()` — runs after plugin copy. Detect existing `jcode` on PATH; else fetch latest release
  asset matching host architecture from `api.github.com/repos/1jehuang/jcode/releases/latest`,
  extract to `~/.jcode/builds/stable/jcode`, verify SHA-256 against the release's `SHA256SUMS`
  file, smoke-test with `jcode --version`. Probe `cargo --version` to set `self_dev_available`.
  Run provider importer once. All progress reported via A0 notification API
  (`AgentNotification.success/error/info`).
- `pre_update()` — graceful daemon shutdown before plugin code is replaced.
- `uninstall()` — kill daemon, delete `~/.amplihack/jcode/`. Leaves `~/.jcode/` user data alone
  unless user opts in via uninstall confirmation modal.

Permission scope: read/write `~/.jcode/builds/`, write `~/.amplihack/jcode/`, network out to
`api.github.com` plus release CDN. No system modification beyond owned paths.

### 5.3 DaemonSupervisor — `helpers/daemon.py`

Lazy-started, single-process-per-A0-instance.

- `ensure_running(working_dir) -> str` — spawns
  `jcode serve --socket <path> --no-tui --no-gateway` if not alive (PID file at
  `~/.amplihack/jcode/jcode.pid`); returns socket path.
- `is_running() -> bool` — flock check on PID file plus socket reachability.
- `shutdown()` — graceful `Request::Shutdown` over IPC, fall back to SIGTERM after 5s.
- `health() -> dict` — uptime, session count, last error.
- `restart()` — for upgrade flow.

State under `~/.amplihack/jcode/`: socket, pid, log, last-error. Logs streamed to A0 logging via
`python/helpers/log.py`.

### 5.4 JcodeClient — `helpers/jcode_client.py`

Pure-Python async client speaking jcode's NDJSON wire format (definitions:
`jcode/crates/jcode-protocol/src/lib.rs`).

```python
class JcodeClient:
    async def connect(self, socket_path: str) -> None
    async def subscribe(self, working_dir: str, target_session_id: str | None,
                        client_instance_id: str, allow_takeover: bool) -> SessionId
    async def send_message(self, content: str, images: list[bytes] = ()) -> int
    async def soft_interrupt(self, content: str, urgent: bool = False) -> None
    async def cancel(self) -> None
    async def background_tool(self, tool_id: str) -> None
    async def stdin_response(self, request_id: str, input: str) -> None
    async def resume_session(self, session_id: str) -> None
    async def list_sessions(self) -> list[SessionSummary]
    async def events(self) -> AsyncIterator[ServerEvent]
    async def close(self) -> None
```

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
`jcode provider add <name> --base-url ... --api-key-stdin --json --overwrite`.

- Maps each A0 provider with a key to one named jcode profile (`a0_<provider_id>`).
- Does not touch jcode OAuth credentials at `~/.jcode/auth*.json` — user creates those via plugin
  UI.
- Idempotent (`--overwrite`).
- Drift detection: when A0 keys change, plugin offers re-sync via toast + WebUI button.

Keys never appear in command-line arguments (always stdin), never in shell history, never logged.

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
| `jcode_resume` | List + resume cross-harness sessions | `Request::ListSessions` + `Subscribe { target_session_id }` |
| `jcode_swarm_msg` | DM / broadcast / channel-send | `CommMessage`, `CommShare`, `CommRead` |
| `jcode_self_dev` | Trigger self-modification cycle (gated) | dispatches selfdev session |

### 5.7 Extensions

- `extensions/python/monologue_start/jcode_takeover.py` — when profile is `jcode_coder`, attach to
  a sticky jcode session keyed on `agent.context.id`, stream user input + jcode response, set
  `loop_data.result` and a sentinel that `before_main_llm_call` checks to suppress A0's loop.
- `extensions/python/agent_init/jcode_register.py` — register tools, ensure daemon running.
- `extensions/python/_functions/agent/Agent/process_tools/start/jcode_intercept.py` — optional
  tool-call rewrite when in profile mode.

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

```yaml
title: jcode Coder
description: Full-takeover mode — jcode runs the agent loop, A0 is chat shell.
context: |
  This profile delegates the entire conversation to a jcode session. All tool calls,
  memory retrieval, and skill activation happen inside jcode. Use for sustained
  coding work where jcode's memory graph and skill auto-injection give the most lift.
prompts: {}
```

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

### 6.2 Full-takeover

Profile `jcode_coder` triggers the `monologue_start` extension. It attaches to a sticky jcode
session keyed on `agent.context.id` (one jcode session per A0 conversation, persists across
turns). User input is forwarded as `Message`. Streaming events update A0 chat in real time. The
extension sets `loop_data.result` and a sentinel; `before_main_llm_call` (`agent.py:404`) sees the
sentinel and skips A0's LLM call. A0 returns the assistant message normally.

Soft-interrupt path: A0 cancel button emits `cancel`, extension translates to
`Request::SoftInterrupt`, jcode injects message at safe point D (default) or C (urgent), no
cancellation.

Memory and skill auto-injection are fully native — jcode's memory_agent computes per-turn
embeddings and BFS retrieval, emits `MemoryInjected` events; skill registry auto-loads on
similarity match.

### 6.3 Cross-harness resume

WebUI calls `/api/plugins/jcode_harness/list_sessions`. The handler issues
`Request::ListSessions { include_external: true }`, receives a `SessionList` event with sessions
grouped by `provider_key` (`claude-code`, `codex`, `opencode`, `pi`, `jcode`). User selects one.
WebUI POSTs `/api/plugins/jcode_harness/resume_session { session_id }`. The handler opens a fresh
A0 conversation, subscribes with `target_session_id` and `allow_takeover=true`, receives a
`History` event with full message log and `provider_session_id`, backfills A0 chat. Subsequent
turns use full-takeover mode against that session — the upstream provider's cache stays warm.

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
- Two A0 instances same project: second attaches existing socket; multi-client supported by jcode
  protocol.
- `Reloading { new_socket }`: client follows new socket, resubscribes with same
  `client_instance_id`.
- Plugin disabled mid-turn: `Cancel` plus graceful shutdown; persist session id so re-enable
  resumes.

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

- Single-stop with text: `Request::SoftInterrupt`, injected at point D. No cancellation. User's
  redirect lands at next safe boundary.
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
  `jcode provider add --api-key-stdin`.
- Cross-harness imports (`~/.claude/.credentials.json` etc.): jcode reads them, plugin doesn't
  touch.
- A0 LiteLLM keys: plugin reads at import time, pipes via stdin to jcode, never logs.
- Session journal (`~/.jcode/sessions/<id>/`, 0600): plugin reads via IPC `History` event, redacts
  in info-level logs.

Plugin must never write keys to plugin config files, toast messages, log lines, or error
responses; never use `--api-key VALUE` argument form (visible in `ps`); add plugin `config.json`
to `.gitignore` as part of install.

### 8.3 Cross-harness import opt-in

Off by default. When user enables via WebUI:

1. Modal lists exact files that would be read with size and last-modified timestamps.
2. User clicks "Allow" per source (granular, not all-or-nothing).
3. Plugin writes consent record to `~/.amplihack/jcode/import_consent.json`.
4. jcode IPC `Request::ImportExternalCreds { sources: [...] }` invoked.
5. On future re-import, consent record is consulted; if file path or hash differs, re-prompt.

Revocation: settings page button deletes consent record plus `Request::ForgetExternalCreds`.

### 8.4 Socket and file permissions

```
~/.amplihack/jcode/jcode.sock           srw-------
~/.amplihack/jcode/jcode.pid            -rw-------
~/.amplihack/jcode/import_consent.json  -rw-------
~/.amplihack/jcode/logs/                drwx------
```

DaemonSupervisor refuses sockets looser than 0600 (re-spawns daemon), refuses stale PID files
owned by other users. Logs rotated daily, retain 7 days, redact request bodies (only event names
and sizes at info level; full content only at debug with explicit `JCODE_LOG_PAYLOADS=1`).

WebSocket gateway disabled at daemon spawn (`--no-gateway`). Plugin never opens a network port.

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

`uninstall()` kills daemon, removes `~/.amplihack/jcode/`, leaves `~/.jcode/` user data alone
unless user opts in via uninstall confirmation modal. Does not touch `~/.cargo/`, `~/.claude/`,
`~/.codex/`. After uninstall, user's external `jcode` CLI keeps working.

### 8.8 Threat model summary

| Threat | Mitigation |
|---|---|
| Malicious plugin update steals creds | Plugin doesn't store creds; daemon update SHA-256 verified; user can pin version |
| Prompt injection causes exfiltration | jcode tool safety; `paranoid` mode; bash allowlist; network calls require explicit network-capable tool |
| Compromised daemon process | Same trust boundary as user; loss = jcode-only data; uninstall containable |
| Local privilege escalation via socket | 0600 perms, PID ownership check |
| Cross-A0-instance leakage | Per-A0-instance daemon (per Q5b) — isolated socket and logs |
| Self-dev rebuilds malicious binary | Gated behind cargo detection plus settings opt-in; rollback artifacts in `~/.jcode/builds/versions/`; original `stable` preserved |
| WebSocket gateway accidentally exposed | `--no-gateway` at spawn, explicit setting required to enable |

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
  stops generation cleanly.
- Full-takeover: profile triggers `monologue_start` short-circuit, A0 LLM never called,
  `MemoryInjected` events surface in side panel, multi-turn persists same session_id.
- Cross-harness resume: lists sessions from claude-code, codex, opencode, pi; resume restores
  history; `provider_session_id` round-trips.
- Memory + skills: `jcode_memory` round-trips remember/recall/search; persists across daemon
  restart; auto-injection fires in full-takeover; `/skill-name` activates manually.
- Provider import: A0 keys imported as openai-compatible profiles; `--api-key-stdin` verified via
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
- Both interaction modes demonstrated.
- Cross-harness resume works for at least Claude Code, Codex, OpenCode, pi.
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
| `loop_data.result` short-circuit may not skip A0 LLM call cleanly | 1-day spike: prove the seam on a current A0 build |
| jcode `Reloading` event semantics differ from doc | 0.5-day: trigger self-update during connection, observe |
| Cross-harness creds may have changed file format in latest Claude Code / Codex | 0.5-day: test against real installs |
| `jcode provider add --json` may not surface all error modes plugin needs | 0.5-day: enumerate exit codes |
| WebUI side-panel breakpoint may not match jcode's rendering payload shape | 0.5-day: grep `x-extension`, confirm match |

Total: ~3 days. Findings fold into the implementation plan.

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
| Q2 | Embedded mode + profile-switchable full-takeover (IV + III) | Ships incrementally; avoids losing memory/skills/swarm coupling that mode II would break |
| Q3 | Scope: a + b + c + e + g + h + i; defer d, f, j | Browser, ambient, mobile out for v1 |
| Q4 | Hybrid provider import (III) | Single import on install + native OAuth via UI; preserves cross-harness resume |
| Q5 | Binary: PATH-aware install with download fallback (c); daemon: per-A0-instance (e); self-dev: cargo-detect, graceful degrade (j) | Matches non-tech UX while supporting power users |
