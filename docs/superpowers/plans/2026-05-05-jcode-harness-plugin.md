# jcode_harness Plugin Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the v1 `jcode_harness` Agent Zero plugin that embeds the jcode coding-agent harness via a Python plugin shell + Rust `jcode serve` daemon over NDJSON Unix socket IPC.

**Architecture:** Hybrid bridge. Python plugin in `usr/plugins/jcode_harness/` runs inside A0 framework runtime. A `DaemonSupervisor` lazy-spawns one `jcode serve` per A0 instance. A `JcodeClient` speaks the protocol from `jcode/crates/jcode-protocol/src/lib.rs`. Seven tools expose embedded jcode capability to the A0 agent. A prompt-routing agent profile (`jcode_coder`) nudges the model toward the harness without requiring an upstream A0 change.

**Tech Stack:** Python 3.11+ (asyncio), Agent Zero plugin framework, jcode (Rust binary), pytest + pytest-asyncio, Playwright (WebUI tests), Alpine.js (existing A0 WebUI conventions).

**Spec:** `docs/superpowers/specs/2026-05-05-jcode-harness-plugin-design.md` (commit `4c28f316`).

---

## File Structure

All paths relative to repo root unless absolute.

```
usr/plugins/jcode_harness/
├── plugin.yaml                               manifest
├── default_config.yaml                       config schema
├── README.md                                 user-facing docs
├── LICENSE                                   plugin license (Apache-2.0)
├── execute.py                                manual cleanup entry point
├── hooks.py                                  install + pre_update hooks
├── helpers/
│   ├── __init__.py
│   ├── instance.py                           A0 instance-id computation
│   ├── paths.py                              ~/.amplihack/jcode/<id>/ resolver
│   ├── protocol.py                           Request/ServerEvent dataclasses
│   ├── jcode_client.py                       async NDJSON client
│   ├── daemon.py                             DaemonSupervisor
│   ├── provider_import.py                    A0 → jcode provider sync
│   ├── arch.py                               binary arch detection
│   ├── download.py                           release asset fetcher + SHA256
│   ├── notifications.py                      A0 toast wrappers
│   └── persistence.py                        client_instance_id JSON store
├── tools/
│   ├── __init__.py
│   ├── jcode_session.py
│   ├── jcode_grep.py
│   ├── jcode_memory.py
│   ├── jcode_skill.py
│   ├── jcode_resume.py
│   ├── jcode_swarm_msg.py
│   └── jcode_self_dev.py
├── api/
│   ├── __init__.py
│   ├── list_sessions.py                      ApiHandler for cross-harness list
│   ├── resume_session.py
│   ├── login_provider.py                     OAuth flow proxy
│   ├── daemon_status.py
│   └── purge_imported_profiles.py
├── extensions/
│   ├── python/
│   │   ├── agent_init/
│   │   │   └── jcode_register.py
│   │   └── monologue_start/
│   │       └── jcode_warmup.py
│   └── webui/
│       ├── side-panel-start/
│       │   └── jcode_panel.html
│       │   └── jcode_panel.js
│       └── sidebar-quick-actions-main-start/
│           └── jcode_quick.html
│           └── jcode_quick.js
├── agents/
│   └── jcode_coder/
│       └── agent.yaml
├── webui/
│   ├── main.html
│   ├── main.js
│   └── config.html
└── tests/
    ├── unit/
    │   ├── test_protocol_codec.py
    │   ├── test_jcode_client.py
    │   ├── test_daemon_supervisor.py
    │   ├── test_provider_import.py
    │   ├── test_arch.py
    │   ├── test_download.py
    │   ├── test_persistence.py
    │   └── test_instance.py
    ├── integration/
    │   ├── conftest.py                       spawns real jcode daemon
    │   ├── test_subscribe_handshake.py
    │   ├── test_simple_message.py
    │   ├── test_tool_call_streaming.py
    │   ├── test_soft_interrupt.py
    │   ├── test_memory_injection.py
    │   ├── test_compaction.py
    │   ├── test_cross_harness_resume.py
    │   ├── test_stdin_request.py
    │   ├── test_reload_event.py
    │   ├── test_daemon_lifecycle.py
    │   ├── test_jcode_session_e2e.py
    │   ├── test_jcode_grep_e2e.py
    │   ├── test_jcode_memory_e2e.py
    │   ├── test_jcode_skill_e2e.py
    │   ├── test_jcode_resume_e2e.py
    │   └── test_jcode_swarm_msg_e2e.py
    ├── fixtures/
    │   └── protocol/                          golden NDJSON fixtures
    │       ├── subscribe_handshake.jsonl
    │       ├── simple_message.jsonl
    │       ├── tool_call.jsonl
    │       ├── soft_interrupt.jsonl
    │       ├── memory_injection.jsonl
    │       ├── compaction.jsonl
    │       ├── cross_harness_resume.jsonl
    │       └── stdin_request.jsonl
    ├── webui/
    │   ├── conftest.py
    │   ├── test_main_page.py
    │   ├── test_config_page.py
    │   ├── test_side_panel.py
    │   └── test_sidebar_quick_actions.py
    ├── perf/
    │   ├── test_ttft.py                       time-to-first-token
    │   ├── test_daemon_boot.py
    │   ├── test_ram.py
    │   └── test_grep_latency.py
    └── security/
        ├── test_socket_perms.py
        ├── test_no_keys_in_ps.py
        └── test_uninstall_hygiene.py

docs/superpowers/spikes/
├── 2026-05-05-spike-reloading-event.md
├── 2026-05-05-spike-session-list-cli.md
├── 2026-05-05-spike-cache-warmth.md
├── 2026-05-05-spike-provider-add-errors.md
├── 2026-05-05-spike-side-panel-breakpoint.md
├── 2026-05-05-spike-gateway-config-overlay.md
└── 2026-05-05-spike-functions-extension-paths.md
```

---

## Chunk Index

| # | Chunk | Approx Tasks |
|---|-------|--------------|
| 0 | Pre-implementation spikes | 7 |
| 1 | Scaffolding & manifest | 4 |
| 2 | Wire protocol codec + golden fixtures | 6 |
| 3 | JcodeClient (async NDJSON) | 8 |
| 4 | DaemonSupervisor | 6 |
| 5 | hooks.py install path | 5 |
| 6 | Provider importer | 4 |
| 7 | Tools (7 sub-chunks) | 14 |
| 8 | Extensions (Python) | 2 |
| 9 | WebUI | 5 |
| 10 | Profile + execute.py cleanup | 2 |
| 11 | API handlers | 5 |
| 12 | Integration & acceptance tests | 6 |
| 13 | Docs + plugin index prep | 4 |

---

## Chunk 0: Pre-implementation spikes

Spec §11 lists 7 v1 spikes. Run them all before touching plugin code. Each spike outputs a 1-page markdown doc with finding + recommendation; spike findings update the plan if needed.

### Task 0.1: Spike — `Reloading { new_socket }` event

**Files:**
- Create: `docs/superpowers/spikes/2026-05-05-spike-reloading-event.md`

- [ ] **Step 1: Write spike script**

```bash
# Spawn jcode daemon, attach with debug logger, trigger self-update,
# observe Reloading event field name + reconnect contract.
cd /tmp && mkdir -p reloading-spike && cd reloading-spike
~/.jcode/builds/stable/jcode --socket ./test.sock serve --owner-pid $$ &
DAEMON_PID=$!
sleep 1
# Connect with `socat - UNIX-CONNECT:./test.sock`, send Subscribe,
# observe stream while triggering jcode update via /selfdev or external.
```

- [ ] **Step 2: Run spike, capture observations**

Run the connect; trigger reload via `kill -HUP $DAEMON_PID` or jcode self-update. Capture:
- exact event JSON
- field name (`new_socket` vs `socket` vs other)
- timing between event and old socket close
- whether `client_instance_id` reattaches the same session

- [ ] **Step 3: Write finding to spike doc**

Doc template:

```markdown
# Spike: Reloading event semantics

**Date:** 2026-05-05
**Spec ref:** §7.1 + §11
**Status:** Resolved | Blocked | Inconclusive

## Question
What is the exact field name and reconnect contract for `ServerEvent::Reloading`?

## Method
[description]

## Finding
- Field name: `new_socket` | `socket` | <other>
- Old socket closes after: <Nms>
- Resubscribe with `client_instance_id` reattaches: yes | no
- Sample event: `{...JSON...}`

## Plan impact
- [Update Chunk 3 step X to use field name <name>]
- [Update Chunk 3 reconnect logic to wait <N>ms after event before reconnecting]
```

- [ ] **Step 4: Commit finding**

```bash
git add docs/superpowers/spikes/2026-05-05-spike-reloading-event.md
git commit -m "spike: jcode Reloading event semantics resolved"
```

### Task 0.2: Spike — `jcode session list --json` subcommand

**Files:**
- Create: `docs/superpowers/spikes/2026-05-05-spike-session-list-cli.md`

- [ ] **Step 1: Probe subcommand existence**

```bash
~/.jcode/builds/stable/jcode session --help 2>&1 | head
~/.jcode/builds/stable/jcode session list --json 2>&1 | head -20
```

- [ ] **Step 2: Identify fallback if subcommand missing**

If `session list` does not exist, try:

```bash
~/.jcode/builds/stable/jcode resume --json
ls -la ~/.jcode/sessions/
cat ~/.jcode/sessions/<any-id>/session.json | head
```

- [ ] **Step 3: Document chosen approach**

Spike doc records: subcommand exists / fallback chosen / output schema with example.

- [ ] **Step 4: Commit + update plan**

If subcommand missing, update Chunk 11 (api/list_sessions.py) to read journal files directly.

### Task 0.3: Spike — `provider_session_id` cache warmth

**Files:**
- Create: `docs/superpowers/spikes/2026-05-05-spike-cache-warmth.md`

- [ ] **Step 1: Seed Claude Code session locally**

Run a multi-turn Claude Code conversation; note its session id under `~/.claude/`.

- [ ] **Step 2: Resume from jcode**

```bash
jcode --resume <claude-code-session-id>
```

Capture token usage from first jcode turn after resume. Compare `cache_read_input_tokens` vs `cache_creation_input_tokens`.

- [ ] **Step 3: Document outcome**

If `cache_read_input_tokens > 0`: cache stayed warm. If only `cache_creation`: cache cold (acceptable per spec §10 downgrade tolerance).

- [ ] **Step 4: Commit finding**

### Task 0.4: Spike — `jcode provider add --json` error coverage

**Files:**
- Create: `docs/superpowers/spikes/2026-05-05-spike-provider-add-errors.md`

- [ ] **Step 1: Enumerate failure modes**

```bash
# Collision
echo "key1" | jcode provider add test --base-url https://x --model y --api-key-stdin --json
echo "key2" | jcode provider add test --base-url https://x --model y --api-key-stdin --json

# Bad URL
echo "k" | jcode provider add bad --base-url not-a-url --model y --api-key-stdin --json

# Missing model
echo "k" | jcode provider add nm --base-url https://x --api-key-stdin --json

# Network error (use unreachable host with reachability validator if any)
echo "k" | jcode provider add net --base-url https://0.0.0.0:1 --model y --api-key-stdin --json
```

- [ ] **Step 2: Capture exit codes + JSON error shapes**

- [ ] **Step 3: Document failure-mode → exit-code map**

- [ ] **Step 4: Commit**

### Task 0.5: Spike — WebUI `x-extension` breakpoints fit jcode `SidePanel*` events

**Files:**
- Create: `docs/superpowers/spikes/2026-05-05-spike-side-panel-breakpoint.md`

- [ ] **Step 1: Enumerate breakpoints**

```bash
grep -rn '<x-extension' /Users/lazy/Desktop/agent-zero/webui/ | head -50
```

- [ ] **Step 2: Match to jcode SidePanel event payloads**

Read `jcode/crates/jcode-side-panel-types/src/lib.rs` to inventory event payload shapes. Map each to the closest A0 breakpoint, or note that a custom side-panel surface (not breakpoint-based) is needed.

- [ ] **Step 3: Document mapping or recommend custom surface**

- [ ] **Step 4: Commit**

### Task 0.6: Spike — gateway disable via `JCODE_CONFIG` overlay

**Files:**
- Create: `docs/superpowers/spikes/2026-05-05-spike-gateway-config-overlay.md`

- [ ] **Step 1: Test overlay**

```bash
mkdir -p /tmp/jcode-overlay
cat > /tmp/jcode-overlay/jcode-config.toml <<EOF
[gateway]
enabled = false
EOF
JCODE_CONFIG=/tmp/jcode-overlay/jcode-config.toml jcode --socket /tmp/test.sock serve --owner-pid $$ &
sleep 2
lsof -i -P | grep -i jcode
# Verify no 7643/tcp or any TCP listen
```

- [ ] **Step 2: Document whether overlay works**

If overlay honored: document. If not, identify alternative (config in `~/.jcode/config.toml` global, or fork issue upstream).

- [ ] **Step 3: Commit**

### Task 0.7: Spike — `_functions/<module>/<qualname>` extension paths (skip if no intercept needed)

**Files:**
- Create: `docs/superpowers/spikes/2026-05-05-spike-functions-extension-paths.md`

- [ ] **Step 1: Confirm no v1 interception needed**

Per spec §5.7, v1 doesn't intercept any A0 internal call sites. Mark spike as **skipped for v1**, recorded for v2 reference.

- [ ] **Step 2: Commit a 3-line "skipped, see §5.7" placeholder**

### Task 0.8: Roll up spike findings into plan addenda

**Files:**
- Modify: `docs/superpowers/plans/2026-05-05-jcode-harness-plugin.md` (this file)

- [ ] **Step 1: Re-read all 7 spike docs**

- [ ] **Step 2: Append "Spike Findings Addendum" section to plan**

Update each chunk's tasks where a spike finding changes the approach (e.g., if `session list` doesn't exist, Chunk 11.1 changes to journal-file reader).

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/plans/2026-05-05-jcode-harness-plugin.md
git commit -m "plan: roll up Chunk 0 spike findings into plan addenda"
```

---

## Chunk 1: Scaffolding & manifest

### Task 1.1: Create plugin directory tree

**Files:**
- Create: empty package skeleton

- [ ] **Step 1: Create directories**

```bash
mkdir -p usr/plugins/jcode_harness/{helpers,tools,api,agents/jcode_coder,webui,tests/unit,tests/integration,tests/fixtures/protocol,tests/webui,tests/perf,tests/security}
mkdir -p usr/plugins/jcode_harness/extensions/python/{agent_init,monologue_start}
mkdir -p usr/plugins/jcode_harness/extensions/webui/side-panel-start
mkdir -p usr/plugins/jcode_harness/extensions/webui/sidebar-quick-actions-main-start
```

- [ ] **Step 2: Add `__init__.py` to all Python dirs**

```bash
touch usr/plugins/jcode_harness/{helpers,tools,api,tests,tests/unit,tests/integration,tests/webui,tests/perf,tests/security}/__init__.py
```

- [ ] **Step 3: Commit**

```bash
git add usr/plugins/jcode_harness/
git commit -m "feat(jcode_harness): scaffold plugin directory tree"
```

### Task 1.2: Write `plugin.yaml` manifest

**Files:**
- Create: `usr/plugins/jcode_harness/plugin.yaml`

- [ ] **Step 1: Author manifest**

```yaml
name: jcode_harness
title: jcode Coding Harness
description: Embeds the jcode coding agent (memory graph, skills, swarm, 28 tools) into Agent Zero.
version: 0.1.0
settings_sections:
  - agent
  - developer
  - external
per_project_config: true
per_agent_config: true
always_enabled: false
```

- [ ] **Step 2: Validate against AGENTS.plugins.md schema**

Cross-check fields against `docs/agents/AGENTS.plugins.md` §2 manifest reference. Confirm:
- `name` matches dir name + regex `^[a-z0-9_]+$`
- `settings_sections` values are valid (`agent`, `external`, `mcp`, `developer`, `backup`)

- [ ] **Step 3: Commit**

```bash
git add usr/plugins/jcode_harness/plugin.yaml
git commit -m "feat(jcode_harness): add plugin.yaml manifest"
```

### Task 1.3: Write `default_config.yaml`

**Files:**
- Create: `usr/plugins/jcode_harness/default_config.yaml`

- [ ] **Step 1: Author config schema (matches spec §5.10)**

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
min_jcode_version: "0.11.4"
```

- [ ] **Step 2: Commit**

```bash
git add usr/plugins/jcode_harness/default_config.yaml
git commit -m "feat(jcode_harness): add default_config.yaml"
```

### Task 1.4: Add LICENSE + minimal README + .gitignore entry

**Files:**
- Create: `usr/plugins/jcode_harness/LICENSE` (Apache-2.0)
- Create: `usr/plugins/jcode_harness/README.md` (stub)
- Modify: `.gitignore` (add `usr/plugins/jcode_harness/config.json`)

- [ ] **Step 1: Drop in Apache-2.0 LICENSE**

Copy standard Apache-2.0 text into LICENSE.

- [ ] **Step 2: Stub README**

```markdown
# jcode_harness

Agent Zero plugin: embedded jcode coding-agent harness with memory graph, skills, swarm, and 28 native tools.

## Status

Pre-release. See `docs/superpowers/specs/2026-05-05-jcode-harness-plugin-design.md`.

## Install

(filled in by Chunk 13)
```

- [ ] **Step 3: Add config.json to .gitignore (per spec §8.2)**

```
# jcode_harness plugin local config (may contain secrets)
usr/plugins/jcode_harness/config.json
```

- [ ] **Step 4: Commit**

```bash
git add usr/plugins/jcode_harness/{LICENSE,README.md} .gitignore
git commit -m "feat(jcode_harness): LICENSE + README stub + gitignore"
```

---

## Chunk 2: Wire protocol codec + golden fixtures

Goal: pure-Python dataclasses for all `Request` and `ServerEvent` variants in `jcode/crates/jcode-protocol/src/lib.rs`. Round-trip verified by golden NDJSON fixtures captured from a real daemon.

### Task 2.1: Write Request/ServerEvent dataclasses

**Files:**
- Create: `usr/plugins/jcode_harness/helpers/protocol.py`
- Test: `usr/plugins/jcode_harness/tests/unit/test_protocol_codec.py`

- [ ] **Step 1: Write failing tests for each Request variant**

```python
# tests/unit/test_protocol_codec.py
import pytest
from usr.plugins.jcode_harness.helpers.protocol import (
    Request, Subscribe, Message, SoftInterrupt, Cancel, BackgroundTool,
    StdinResponse, ResumeSession, Ping, encode_request, decode_event,
)

def test_subscribe_round_trip():
    req = Subscribe(working_dir="/tmp/x", target_session_id=None,
                    client_instance_id="abc", allow_session_takeover=False)
    line = encode_request(req)
    assert b'"type":"subscribe"' in line
    assert b'"working_dir":"/tmp/x"' in line
    assert b'"client_instance_id":"abc"' in line
    assert b'"allow_session_takeover":false' in line
    assert line.endswith(b"\n")

def test_message_round_trip():
    req = Message(id=1, content="hello", images=[])
    line = encode_request(req)
    assert b'"type":"message"' in line
    assert b'"content":"hello"' in line

def test_soft_interrupt_round_trip():
    req = SoftInterrupt(id=2, content="redirect", urgent=False)
    line = encode_request(req)
    assert b'"type":"soft_interrupt"' in line
```

- [ ] **Step 2: Run tests; expect ImportError**

```bash
pytest usr/plugins/jcode_harness/tests/unit/test_protocol_codec.py -v
# Expected: ImportError on `helpers.protocol`
```

- [ ] **Step 3: Implement `helpers/protocol.py` Request side**

```python
# helpers/protocol.py
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Any, Literal
import json

# --- Request types (mirrors jcode/crates/jcode-protocol/src/lib.rs Request enum) ---

@dataclass
class Subscribe:
    working_dir: str
    target_session_id: str | None
    client_instance_id: str
    allow_session_takeover: bool = False
    type: Literal["subscribe"] = "subscribe"

@dataclass
class Message:
    id: int
    content: str
    images: list[str] = field(default_factory=list)
    system_reminder: str | None = None
    type: Literal["message"] = "message"

@dataclass
class SoftInterrupt:
    id: int
    content: str
    urgent: bool = False
    type: Literal["soft_interrupt"] = "soft_interrupt"

@dataclass
class CancelSoftInterrupts:
    type: Literal["cancel_soft_interrupts"] = "cancel_soft_interrupts"

@dataclass
class Cancel:
    type: Literal["cancel"] = "cancel"

@dataclass
class BackgroundTool:
    tool_id: str
    type: Literal["background_tool"] = "background_tool"

@dataclass
class StdinResponse:
    request_id: str
    input: str
    type: Literal["stdin_response"] = "stdin_response"

@dataclass
class ResumeSession:
    session_id: str
    client_instance_id: str
    allow_session_takeover: bool = False
    type: Literal["resume_session"] = "resume_session"

@dataclass
class GetHistory:
    type: Literal["get_history"] = "get_history"

@dataclass
class Ping:
    type: Literal["ping"] = "ping"

# Comm* (swarm) requests
@dataclass
class CommMessage:
    target: str  # session id or "broadcast"
    content: str
    type: Literal["comm_message"] = "comm_message"

@dataclass
class CommShare:
    paths: list[str]
    type: Literal["comm_share"] = "comm_share"

@dataclass
class CommRead:
    paths: list[str]
    type: Literal["comm_read"] = "comm_read"

# union
Request = (
    Subscribe | Message | SoftInterrupt | CancelSoftInterrupts | Cancel |
    BackgroundTool | StdinResponse | ResumeSession | GetHistory | Ping |
    CommMessage | CommShare | CommRead
)

def encode_request(req: Request) -> bytes:
    return (json.dumps(asdict(req), separators=(",", ":")) + "\n").encode()
```

- [ ] **Step 4: Run Request tests; expect PASS**

- [ ] **Step 5: Add ServerEvent decoder**

Tests first:

```python
def test_text_delta_decode():
    line = b'{"type":"text_delta","text":"hello"}\n'
    ev = decode_event(line)
    assert ev.type == "text_delta"
    assert ev.text == "hello"

def test_unknown_event_passes_through():
    line = b'{"type":"future_variant","x":42}\n'
    ev = decode_event(line)
    assert ev.type == "unknown"
    assert ev.raw["type"] == "future_variant"
    assert ev.raw["x"] == 42

def test_session_id_event():
    line = b'{"type":"session_id","session_id":"fox"}\n'
    ev = decode_event(line)
    assert ev.session_id == "fox"
```

Implementation:

```python
@dataclass
class ServerEvent:
    type: str

@dataclass
class TextDelta(ServerEvent):
    text: str
    type: Literal["text_delta"] = "text_delta"

@dataclass
class ToolStart(ServerEvent):
    id: str
    name: str
    type: Literal["tool_start"] = "tool_start"

@dataclass
class ToolInput(ServerEvent):
    id: str
    delta: str
    type: Literal["tool_input"] = "tool_input"

@dataclass
class ToolExec(ServerEvent):
    id: str
    name: str
    type: Literal["tool_exec"] = "tool_exec"

@dataclass
class ToolDone(ServerEvent):
    id: str
    name: str
    output: str | None = None
    error: str | None = None
    type: Literal["tool_done"] = "tool_done"

@dataclass
class MessageEnd(ServerEvent):
    type: Literal["message_end"] = "message_end"

@dataclass
class Done(ServerEvent):
    id: int
    type: Literal["done"] = "done"

@dataclass
class SessionId(ServerEvent):
    session_id: str
    type: Literal["session_id"] = "session_id"

@dataclass
class History(ServerEvent):
    messages: list[dict]
    images: list[dict] = field(default_factory=list)
    mcp_servers: list[dict] = field(default_factory=list)
    skills: list[dict] = field(default_factory=list)
    available_models: list[dict] = field(default_factory=list)
    total_tokens: dict = field(default_factory=dict)
    all_sessions: list[dict] = field(default_factory=list)
    server_version: str = ""
    server_name: str = ""
    server_icon: str = ""
    activity: dict = field(default_factory=dict)
    side_panel: dict | None = None
    type: Literal["history"] = "history"

@dataclass
class TokenUsage(ServerEvent):
    input: int
    output: int
    cache_read_input: int = 0
    cache_creation_input: int = 0
    type: Literal["token_usage"] = "token_usage"

@dataclass
class MemoryInjected(ServerEvent):
    count: int
    prompt: str
    prompt_chars: int
    computed_age_ms: int
    type: Literal["memory_injected"] = "memory_injected"

@dataclass
class Compaction(ServerEvent):
    trigger: str
    pre_tokens: int
    post_tokens: int
    messages_dropped: int
    messages_compacted: int
    summary_chars: int
    cache_cold: bool = False
    type: Literal["compaction"] = "compaction"

@dataclass
class Reloading(ServerEvent):
    new_socket: str  # field name to be confirmed by Spike 0.1
    type: Literal["reloading"] = "reloading"

@dataclass
class Interrupted(ServerEvent):
    type: Literal["interrupted"] = "interrupted"

@dataclass
class StdinRequest(ServerEvent):
    request_id: str
    prompt: str
    is_password: bool = False
    tool_call_id: str | None = None
    type: Literal["stdin_request"] = "stdin_request"

@dataclass
class SoftInterruptInjected(ServerEvent):
    content: str
    point: str  # B|C|D
    tools_skipped: int = 0
    type: Literal["soft_interrupt_injected"] = "soft_interrupt_injected"

@dataclass
class SwarmStatus(ServerEvent):
    members: list[dict]
    type: Literal["swarm_status"] = "swarm_status"

@dataclass
class CommReceived(ServerEvent):
    sender: str
    content: str
    type: Literal["comm_message"] = "comm_message"

# Generated image, side panel updates, etc.
@dataclass
class GeneratedImage(ServerEvent):
    id: str
    path: str
    revised_prompt: str | None = None
    type: Literal["generated_image"] = "generated_image"

@dataclass
class SidePanelUpdate(ServerEvent):
    payload: dict
    type: Literal["side_panel"] = "side_panel"

@dataclass
class Pong(ServerEvent):
    type: Literal["pong"] = "pong"

@dataclass
class UnknownEvent(ServerEvent):
    raw: dict
    type: Literal["unknown"] = "unknown"

# discriminator dispatch
_EVENT_REGISTRY = {
    "text_delta": TextDelta,
    "tool_start": ToolStart,
    "tool_input": ToolInput,
    "tool_exec": ToolExec,
    "tool_done": ToolDone,
    "message_end": MessageEnd,
    "done": Done,
    "session_id": SessionId,
    "history": History,
    "token_usage": TokenUsage,
    "memory_injected": MemoryInjected,
    "compaction": Compaction,
    "reloading": Reloading,
    "interrupted": Interrupted,
    "stdin_request": StdinRequest,
    "soft_interrupt_injected": SoftInterruptInjected,
    "swarm_status": SwarmStatus,
    "comm_message": CommReceived,
    "generated_image": GeneratedImage,
    "side_panel": SidePanelUpdate,
    "pong": Pong,
}

def decode_event(line: bytes) -> ServerEvent:
    obj = json.loads(line)
    cls = _EVENT_REGISTRY.get(obj.get("type"))
    if cls is None:
        return UnknownEvent(raw=obj, type="unknown")
    # filter to fields the dataclass accepts
    field_names = {f.name for f in cls.__dataclass_fields__.values()}
    kwargs = {k: v for k, v in obj.items() if k in field_names}
    return cls(**kwargs)
```

- [ ] **Step 6: Run all codec tests; expect PASS**

```bash
pytest usr/plugins/jcode_harness/tests/unit/test_protocol_codec.py -v
```

- [ ] **Step 7: Commit**

```bash
git add usr/plugins/jcode_harness/helpers/protocol.py \
        usr/plugins/jcode_harness/tests/unit/test_protocol_codec.py
git commit -m "feat(jcode_harness): protocol codec for Request + ServerEvent"
```

### Task 2.2: Capture golden NDJSON fixtures from real daemon

**Files:**
- Create: `usr/plugins/jcode_harness/tests/fixtures/protocol/*.jsonl`
- Create: `scripts/capture_jcode_fixtures.sh`

- [ ] **Step 1: Write capture script**

```bash
#!/usr/bin/env bash
# scripts/capture_jcode_fixtures.sh
# Captures NDJSON event traces from a real jcode serve daemon for golden fixtures.
set -euo pipefail
SOCK=$(mktemp -u --suffix=.sock)
~/.jcode/builds/stable/jcode --socket "$SOCK" serve --owner-pid $$ &
DAEMON=$!
trap "kill $DAEMON 2>/dev/null; rm -f $SOCK" EXIT
sleep 1

capture () {
    local name=$1
    local script=$2
    socat -u UNIX-CONNECT:"$SOCK" - <<<"$script" \
      > "usr/plugins/jcode_harness/tests/fixtures/protocol/${name}.jsonl"
}

# subscribe handshake
capture subscribe_handshake '{"type":"subscribe","working_dir":"/tmp","target_session_id":null,"client_instance_id":"fix-1","allow_session_takeover":false}'

# simple message → wait for done
capture simple_message '{"type":"subscribe","working_dir":"/tmp","target_session_id":null,"client_instance_id":"fix-2","allow_session_takeover":false}
{"type":"message","id":1,"content":"echo hi","images":[]}'

# tool call
capture tool_call '{"type":"subscribe","working_dir":"/tmp","target_session_id":null,"client_instance_id":"fix-3","allow_session_takeover":false}
{"type":"message","id":1,"content":"run ls in this dir","images":[]}'

# soft interrupt
capture soft_interrupt '{"type":"subscribe","working_dir":"/tmp","target_session_id":null,"client_instance_id":"fix-4","allow_session_takeover":false}
{"type":"message","id":1,"content":"start a long task","images":[]}
{"type":"soft_interrupt","id":2,"content":"redirect","urgent":false}'

# (continue for memory_injection, compaction, cross_harness_resume, stdin_request)
```

- [ ] **Step 2: Run script, inspect fixtures**

```bash
bash scripts/capture_jcode_fixtures.sh
ls -la usr/plugins/jcode_harness/tests/fixtures/protocol/
head -5 usr/plugins/jcode_harness/tests/fixtures/protocol/simple_message.jsonl
```

- [ ] **Step 3: Manually trim fixtures**

For each fixture, retain only the events that exercise the codec; trim long text deltas to ≤3 examples each. Document in fixture file head comment what behavior it covers.

- [ ] **Step 4: Add fixture round-trip tests**

```python
# tests/unit/test_protocol_codec.py (append)
import json
from pathlib import Path
from usr.plugins.jcode_harness.helpers.protocol import decode_event, UnknownEvent

FIXTURES = Path(__file__).parent.parent / "fixtures" / "protocol"

@pytest.mark.parametrize("fixture", list(FIXTURES.glob("*.jsonl")))
def test_fixture_round_trip(fixture):
    """Every event in every fixture must decode to a typed dataclass (no UnknownEvent)."""
    with open(fixture, "rb") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith(b"#"):
                continue
            ev = decode_event(line + b"\n")
            assert not isinstance(ev, UnknownEvent), \
                f"Unknown event variant in {fixture.name}: {ev.raw}"
```

- [ ] **Step 5: Run; if any UnknownEvent, add the variant to protocol.py**

```bash
pytest usr/plugins/jcode_harness/tests/unit/test_protocol_codec.py::test_fixture_round_trip -v
```

- [ ] **Step 6: Commit**

```bash
git add usr/plugins/jcode_harness/tests/fixtures/protocol/ scripts/capture_jcode_fixtures.sh \
        usr/plugins/jcode_harness/tests/unit/test_protocol_codec.py \
        usr/plugins/jcode_harness/helpers/protocol.py
git commit -m "test(jcode_harness): golden NDJSON fixtures + round-trip tests"
```

---

## Chunk 3: JcodeClient

### Task 3.1: A0 instance-id helper

**Files:**
- Create: `usr/plugins/jcode_harness/helpers/instance.py`
- Test: `usr/plugins/jcode_harness/tests/unit/test_instance.py`

- [ ] **Step 1: Test**

```python
# tests/unit/test_instance.py
from usr.plugins.jcode_harness.helpers.instance import compute_instance_id

def test_instance_id_is_12_hex_chars():
    iid = compute_instance_id("/abs/path/to/agent_zero")
    assert len(iid) == 12
    assert all(c in "0123456789abcdef" for c in iid)

def test_instance_id_stable():
    a = compute_instance_id("/abs/path/to/agent_zero")
    b = compute_instance_id("/abs/path/to/agent_zero")
    assert a == b

def test_instance_id_distinguishes_paths():
    a = compute_instance_id("/checkout/dev")
    b = compute_instance_id("/checkout/prod")
    assert a != b
```

- [ ] **Step 2: Implementation**

```python
# helpers/instance.py
import hashlib
import os

def compute_instance_id(process_root: str | None = None) -> str:
    """Stable 12-hex-char id for this A0 install (per spec §4.1)."""
    if process_root is None:
        # default: parent dir of agent.py
        process_root = os.path.dirname(os.path.realpath(
            os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "agent.py")
        ))
    process_root = os.path.realpath(process_root)
    return hashlib.sha256(process_root.encode()).hexdigest()[:12]
```

- [ ] **Step 3: Run tests; expect PASS**

- [ ] **Step 4: Commit**

### Task 3.2: Path resolver

**Files:**
- Create: `usr/plugins/jcode_harness/helpers/paths.py`

- [ ] **Step 1: Test**

```python
def test_paths_under_amplihack():
    from usr.plugins.jcode_harness.helpers.paths import jcode_runtime_dir
    p = jcode_runtime_dir()
    assert "amplihack/jcode" in str(p)
    assert p.exists()  # auto-created
```

- [ ] **Step 2: Implementation**

```python
# helpers/paths.py
from pathlib import Path
import platform
from .instance import compute_instance_id

def amplihack_root() -> Path:
    if platform.system() == "Windows":
        import os
        return Path(os.environ["LOCALAPPDATA"]) / "amplihack"
    return Path.home() / ".amplihack"

def jcode_runtime_dir(instance_id: str | None = None) -> Path:
    iid = instance_id or compute_instance_id()
    p = amplihack_root() / "jcode" / iid
    p.mkdir(parents=True, exist_ok=True, mode=0o700)
    return p

def socket_path(instance_id: str | None = None) -> Path:
    return jcode_runtime_dir(instance_id) / "socket"

def pid_path(instance_id: str | None = None) -> Path:
    return jcode_runtime_dir(instance_id) / "pid"

def client_instance_persist_path(a0_ctx_id: str, instance_id: str | None = None) -> Path:
    sessions_dir = jcode_runtime_dir(instance_id) / "sessions"
    sessions_dir.mkdir(exist_ok=True, mode=0o700)
    return sessions_dir / f"{a0_ctx_id}.json"

def overlay_config_path(instance_id: str | None = None) -> Path:
    return jcode_runtime_dir(instance_id) / "jcode-config.toml"
```

- [ ] **Step 3: Commit**

### Task 3.3: Persistent client_instance_id store

**Files:**
- Create: `usr/plugins/jcode_harness/helpers/persistence.py`
- Test: `usr/plugins/jcode_harness/tests/unit/test_persistence.py`

- [ ] **Step 1: Test**

```python
def test_persist_and_load_client_id(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "usr.plugins.jcode_harness.helpers.persistence.client_instance_persist_path",
        lambda ctx_id, iid=None: tmp_path / f"{ctx_id}.json",
    )
    from usr.plugins.jcode_harness.helpers.persistence import (
        get_or_create_client_instance_id,
    )
    a = get_or_create_client_instance_id("ctx-1")
    b = get_or_create_client_instance_id("ctx-1")
    assert a == b  # stable per ctx
    c = get_or_create_client_instance_id("ctx-2")
    assert a != c
```

- [ ] **Step 2: Implementation**

```python
# helpers/persistence.py
import json
import uuid
from .paths import client_instance_persist_path

def get_or_create_client_instance_id(a0_ctx_id: str, instance_id: str | None = None) -> str:
    p = client_instance_persist_path(a0_ctx_id, instance_id)
    if p.exists():
        return json.loads(p.read_text())["client_instance_id"]
    cid = str(uuid.uuid4())
    p.write_text(json.dumps({"client_instance_id": cid}))
    p.chmod(0o600)
    return cid
```

- [ ] **Step 3: Commit**

### Task 3.4: JcodeClient — connect + subscribe + close

**Files:**
- Create: `usr/plugins/jcode_harness/helpers/jcode_client.py`
- Test: `usr/plugins/jcode_harness/tests/unit/test_jcode_client.py`

- [ ] **Step 1: Test connect/subscribe with mocked socket**

```python
import asyncio
import pytest
from usr.plugins.jcode_harness.helpers.jcode_client import JcodeClient
from usr.plugins.jcode_harness.helpers.protocol import SessionId

@pytest.mark.asyncio
async def test_subscribe_sends_correct_request(tmp_path):
    """Mock the socket; assert correct Subscribe JSON written."""
    sock = tmp_path / "test.sock"
    server_received = []
    server_done = asyncio.Event()

    async def fake_server(reader, writer):
        line = await reader.readline()
        server_received.append(line)
        writer.write(b'{"type":"session_id","session_id":"fox-1"}\n')
        await writer.drain()
        server_done.set()
        writer.close()

    server = await asyncio.start_unix_server(fake_server, path=str(sock))
    try:
        client = JcodeClient()
        await client.connect(str(sock))
        sid = await client.subscribe("/tmp", None, "cid-1", False)
        assert sid.session_id == "fox-1"
        await server_done.wait()
        sent = server_received[0].decode()
        assert '"type":"subscribe"' in sent
        assert '"client_instance_id":"cid-1"' in sent
        assert '"allow_session_takeover":false' in sent
    finally:
        server.close()
        await server.wait_closed()
```

- [ ] **Step 2: Implement minimum**

```python
# helpers/jcode_client.py
import asyncio
import json
from typing import AsyncIterator
from .protocol import (
    Subscribe, Message, SoftInterrupt, Cancel, BackgroundTool, StdinResponse,
    ResumeSession, GetHistory, Ping, CancelSoftInterrupts,
    encode_request, decode_event, ServerEvent, SessionId,
)

class JcodeClient:
    def __init__(self):
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._socket_path: str | None = None
        self._subscribed = False

    async def connect(self, socket_path: str) -> None:
        self._reader, self._writer = await asyncio.open_unix_connection(socket_path)
        self._socket_path = socket_path

    async def _send(self, req) -> None:
        assert self._writer is not None
        self._writer.write(encode_request(req))
        await self._writer.drain()

    async def _recv_until(self, predicate) -> ServerEvent:
        assert self._reader is not None
        while True:
            line = await self._reader.readline()
            if not line:
                raise ConnectionError("daemon closed connection")
            ev = decode_event(line)
            if predicate(ev):
                return ev

    async def subscribe(self, working_dir: str, target_session_id: str | None,
                        client_instance_id: str, allow_session_takeover: bool) -> SessionId:
        req = Subscribe(
            working_dir=working_dir,
            target_session_id=target_session_id,
            client_instance_id=client_instance_id,
            allow_session_takeover=allow_session_takeover,
        )
        await self._send(req)
        ev = await self._recv_until(lambda e: e.type == "session_id")
        self._subscribed = True
        return ev

    async def close(self) -> None:
        if self._writer:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except Exception:
                pass
```

- [ ] **Step 3: Run; expect PASS**

```bash
pytest usr/plugins/jcode_harness/tests/unit/test_jcode_client.py -v
```

- [ ] **Step 4: Commit**

### Task 3.5: send_message + soft_interrupt + cancel + background_tool + stdin_response

- [ ] **Step 1: Tests for each method**

(One asyncio test per method, mocking server with expected response.)

- [ ] **Step 2: Add methods to JcodeClient**

```python
async def send_message(self, content: str, images: list[bytes] = (), msg_id: int | None = None) -> int:
    msg_id = msg_id or self._next_id()
    await self._send(Message(id=msg_id, content=content,
                              images=[base64.b64encode(b).decode() for b in images]))
    return msg_id

async def soft_interrupt(self, content: str, urgent: bool = False, msg_id: int | None = None):
    msg_id = msg_id or self._next_id()
    await self._send(SoftInterrupt(id=msg_id, content=content, urgent=urgent))

async def cancel_soft_interrupts(self):
    await self._send(CancelSoftInterrupts())

async def cancel(self):
    await self._send(Cancel())

async def background_tool(self, tool_id: str):
    await self._send(BackgroundTool(tool_id=tool_id))

async def stdin_response(self, request_id: str, input: str):
    await self._send(StdinResponse(request_id=request_id, input=input))

async def resume_session(self, session_id: str, client_instance_id: str,
                         allow_session_takeover: bool = True):
    await self._send(ResumeSession(
        session_id=session_id,
        client_instance_id=client_instance_id,
        allow_session_takeover=allow_session_takeover,
    ))

async def ping(self):
    await self._send(Ping())

async def get_history(self):
    await self._send(GetHistory())

def _next_id(self) -> int:
    if not hasattr(self, "_id_counter"):
        self._id_counter = 0
    self._id_counter += 1
    return self._id_counter
```

- [ ] **Step 3: Run tests; expect PASS**

- [ ] **Step 4: Commit**

### Task 3.6: events() async generator

- [ ] **Step 1: Test event streaming**

```python
@pytest.mark.asyncio
async def test_events_iterates_until_done(tmp_path):
    """Server emits 3 text_delta then done; client iterates correctly."""
    sock = tmp_path / "ev.sock"

    async def fake(reader, writer):
        await reader.readline()  # eat subscribe
        writer.write(b'{"type":"session_id","session_id":"x"}\n')
        await writer.drain()
        for t in ("a", "b", "c"):
            writer.write(json.dumps({"type":"text_delta","text":t}).encode() + b"\n")
        writer.write(b'{"type":"done","id":1}\n')
        await writer.drain()
        writer.close()

    server = await asyncio.start_unix_server(fake, path=str(sock))
    client = JcodeClient()
    try:
        await client.connect(str(sock))
        await client.subscribe("/tmp", None, "x", False)
        events = []
        async for ev in client.events():
            events.append(ev)
            if ev.type == "done":
                break
        types = [e.type for e in events]
        assert types == ["text_delta", "text_delta", "text_delta", "done"]
    finally:
        server.close()
        await server.wait_closed()
```

- [ ] **Step 2: Implement events()**

```python
async def events(self) -> AsyncIterator[ServerEvent]:
    assert self._reader is not None
    while True:
        line = await self._reader.readline()
        if not line:
            return
        try:
            yield decode_event(line)
        except json.JSONDecodeError:
            # malformed; log + skip per spec §7.2
            continue
```

- [ ] **Step 3: Run + commit**

### Task 3.7: Reconnect with exponential backoff + Reloading handling

- [ ] **Step 1: Tests for reconnect**

Simulate socket drop, verify backoff timing (1s, 2s, 4s capped at 30s) + auto-resubscribe with same `client_instance_id`.

- [ ] **Step 2: Implement `_reconnect_loop`**

```python
async def _reconnect_loop(self, working_dir: str, client_instance_id: str,
                          target_session_id: str | None):
    delay = 1.0
    while True:
        try:
            await self.connect(self._socket_path)
            await self.subscribe(working_dir, target_session_id, client_instance_id, True)
            return
        except (ConnectionRefusedError, FileNotFoundError, ConnectionError):
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30.0)
```

- [ ] **Step 3: Handle Reloading event**

```python
async def _maybe_follow_reloading(self, ev):
    if ev.type == "reloading":
        new_socket = ev.new_socket  # field name confirmed by Spike 0.1
        await self.close()
        await asyncio.sleep(0.1)
        self._socket_path = new_socket
        await self._reconnect_loop(...)
        return True
    return False
```

- [ ] **Step 4: Wire into `events()` so iteration survives reload transparently**

- [ ] **Step 5: Run + commit**

### Task 3.8: Windows named-pipe transport

- [ ] **Step 1: Test (skip-on-non-windows)**

```python
@pytest.mark.skipif(platform.system() != "Windows", reason="Windows-only")
def test_named_pipe_connect(): ...
```

- [ ] **Step 2: Implementation in JcodeClient.connect**

```python
async def connect(self, socket_path: str):
    if platform.system() == "Windows":
        # Use pywin32 + asyncio.ProactorEventLoop pipe APIs
        from .transport_windows import open_named_pipe
        self._reader, self._writer = await open_named_pipe(socket_path)
    else:
        self._reader, self._writer = await asyncio.open_unix_connection(socket_path)
    self._socket_path = socket_path
```

- [ ] **Step 3: Stub `helpers/transport_windows.py` (mark unverified for v1; smoke test only)**

- [ ] **Step 4: Commit**

---

## Chunk 4: DaemonSupervisor

### Task 4.1: Arch detection

**Files:**
- Create: `usr/plugins/jcode_harness/helpers/arch.py`
- Test: `tests/unit/test_arch.py`

- [ ] **Step 1: Test**

```python
def test_returns_known_arch():
    from usr.plugins.jcode_harness.helpers.arch import detect_release_asset_target
    target = detect_release_asset_target()
    assert target in {"darwin-arm64", "darwin-x86_64", "linux-x86_64",
                      "linux-aarch64", "windows-x86_64"}

def test_macos_rosetta_detection(monkeypatch):
    """sysctl hw.optional.arm64 == 1 means real arm64 even if uname says x86_64."""
    monkeypatch.setattr("platform.system", lambda: "Darwin")
    monkeypatch.setattr("platform.machine", lambda: "x86_64")  # Rosetta lies
    monkeypatch.setattr(
        "subprocess.check_output",
        lambda args, **kw: b"hw.optional.arm64: 1\n",
    )
    from usr.plugins.jcode_harness.helpers.arch import detect_release_asset_target
    assert detect_release_asset_target() == "darwin-arm64"
```

- [ ] **Step 2: Implementation**

```python
import platform
import subprocess

def detect_release_asset_target() -> str:
    sys = platform.system()
    if sys == "Darwin":
        try:
            out = subprocess.check_output(["sysctl", "-n", "hw.optional.arm64"],
                                           stderr=subprocess.DEVNULL).strip()
            if out == b"1":
                return "darwin-arm64"
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass
        return "darwin-x86_64"
    if sys == "Linux":
        m = platform.machine().lower()
        if m in {"aarch64", "arm64"}:
            return "linux-aarch64"
        return "linux-x86_64"
    if sys == "Windows":
        return "windows-x86_64"
    raise RuntimeError(f"unsupported OS: {sys}")
```

- [ ] **Step 3: Commit**

### Task 4.2: Release asset downloader + SHA256 verifier

**Files:**
- Create: `usr/plugins/jcode_harness/helpers/download.py`
- Test: `tests/unit/test_download.py`

- [ ] **Step 1: Tests** — mock GitHub API + asset URL; assert SHA256 mismatch raises.

- [ ] **Step 2: Implementation**

```python
import hashlib
import tarfile
import tempfile
import urllib.request
from pathlib import Path

GITHUB_API = "https://api.github.com/repos/1jehuang/jcode/releases/latest"

def fetch_latest_release_metadata() -> dict:
    with urllib.request.urlopen(GITHUB_API, timeout=30) as r:
        return json.loads(r.read())

def pick_asset(release: dict, target: str) -> tuple[str, str]:
    """Return (asset_download_url, sha256_url)."""
    asset_url = next(a["browser_download_url"] for a in release["assets"]
                     if target in a["name"] and a["name"].endswith((".tar.gz", ".zip")))
    sha_url = next(a["browser_download_url"] for a in release["assets"]
                   if a["name"].lower() in ("sha256sums", "checksums.txt"))
    return asset_url, sha_url

def download_and_verify(asset_url: str, sha_url: str, target_path: Path) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(asset_url) as r, tempfile.NamedTemporaryFile(delete=False) as f:
        chunk = r.read(8192)
        h = hashlib.sha256()
        while chunk:
            h.update(chunk); f.write(chunk); chunk = r.read(8192)
        archive = Path(f.name)

    expected = _lookup_sha(sha_url, asset_url)
    actual = h.hexdigest()
    if actual != expected:
        archive.unlink()
        raise ValueError(f"SHA256 mismatch: expected {expected}, got {actual}")
    _extract(archive, target_path)
    archive.unlink()
    target_path.chmod(0o755)

def _lookup_sha(sha_url: str, asset_url: str) -> str:
    asset_name = asset_url.rsplit("/", 1)[-1]
    with urllib.request.urlopen(sha_url) as r:
        for line in r.read().decode().splitlines():
            sha, name = line.split(maxsplit=1)
            if name.strip() == asset_name:
                return sha
    raise ValueError(f"SHA256 for {asset_name} not found in {sha_url}")

def _extract(archive: Path, target_path: Path):
    if archive.suffix == ".gz":
        with tarfile.open(archive) as tf:
            members = [m for m in tf.getmembers() if m.name.endswith("/jcode") or m.name == "jcode"]
            if not members:
                raise ValueError("no jcode binary in archive")
            tf.extract(members[0], path=target_path.parent)
            extracted = target_path.parent / members[0].name
            extracted.rename(target_path)
    else:
        # zip path for windows-x86_64
        import zipfile
        with zipfile.ZipFile(archive) as zf:
            zf.extract("jcode.exe", path=target_path.parent)
            (target_path.parent / "jcode.exe").rename(target_path)
```

- [ ] **Step 3: Run tests + commit**

### Task 4.3: DaemonSupervisor — ensure_running, is_running, stop

**Files:**
- Create: `usr/plugins/jcode_harness/helpers/daemon.py`
- Test: `tests/unit/test_daemon_supervisor.py`

- [ ] **Step 1: Tests**

```python
@pytest.mark.asyncio
async def test_ensure_running_spawns_daemon(monkeypatch, tmp_path):
    """First ensure_running spawns daemon; second returns existing."""
    from usr.plugins.jcode_harness.helpers.daemon import DaemonSupervisor
    sup = DaemonSupervisor(jcode_binary="/bin/sleep", instance_dir=tmp_path)
    sock1 = await sup.ensure_running("/tmp/wd")
    assert sup.is_running()
    sock2 = await sup.ensure_running("/tmp/wd")
    assert sock1 == sock2  # same daemon

def test_stale_pid_file_replaced(tmp_path):
    """Foreign / dead PID → file moved to .dead.<ts>, fresh spawn."""
    pid_file = tmp_path / "pid"
    pid_file.write_text("99999999")  # almost certainly dead
    from usr.plugins.jcode_harness.helpers.daemon import DaemonSupervisor
    sup = DaemonSupervisor(jcode_binary="/bin/sleep", instance_dir=tmp_path)
    assert not sup.is_running()
    # next ensure_running should rename pid_file to .dead.<ts>
```

- [ ] **Step 2: Implementation**

```python
import asyncio
import os
import signal
import subprocess
import time
from pathlib import Path

class DaemonSupervisor:
    def __init__(self, jcode_binary: str, instance_dir: Path):
        self.jcode_binary = jcode_binary
        self.instance_dir = instance_dir
        self.pid_file = instance_dir / "pid"
        self.socket_file = instance_dir / "socket"
        self.overlay_config = instance_dir / "jcode-config.toml"
        self.log_dir = instance_dir / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True, mode=0o700)

    def is_running(self) -> bool:
        if not self.pid_file.exists() or not self.socket_file.exists():
            return False
        try:
            pid = int(self.pid_file.read_text().strip())
            os.kill(pid, 0)  # signal 0 = alive check
            return self._socket_perms_ok()
        except (ValueError, ProcessLookupError, PermissionError):
            return False

    def _socket_perms_ok(self) -> bool:
        st = self.socket_file.stat()
        return (st.st_mode & 0o777) == 0o600 and st.st_uid == os.getuid()

    async def ensure_running(self, working_dir: str) -> str:
        if self.is_running():
            return str(self.socket_file)
        # archive stale pid
        if self.pid_file.exists():
            ts = int(time.time())
            self.pid_file.rename(self.instance_dir / f"pid.dead.{ts}")
        # write overlay config to disable gateway
        self.overlay_config.write_text(
            "[gateway]\nenabled = false\n"
        )
        self.overlay_config.chmod(0o600)
        # spawn
        log_file = self.log_dir / f"jcode-{int(time.time())}.log"
        env = dict(os.environ, JCODE_CONFIG=str(self.overlay_config))
        proc = subprocess.Popen(
            [self.jcode_binary, "--socket", str(self.socket_file),
             "serve", "--owner-pid", str(os.getpid())],
            env=env,
            stdout=open(log_file, "ab"),
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        self.pid_file.write_text(str(proc.pid))
        self.pid_file.chmod(0o600)
        # wait for socket up
        for _ in range(50):  # 5s
            if self.socket_file.exists() and self._socket_perms_ok():
                return str(self.socket_file)
            await asyncio.sleep(0.1)
        raise RuntimeError(f"jcode daemon did not become ready in 5s; see {log_file}")

    def stop(self, timeout: float = 5.0):
        if not self.pid_file.exists():
            return
        try:
            pid = int(self.pid_file.read_text().strip())
            os.kill(pid, signal.SIGTERM)
            deadline = time.time() + timeout
            while time.time() < deadline:
                try:
                    os.kill(pid, 0)
                    time.sleep(0.1)
                except ProcessLookupError:
                    break
            else:
                os.kill(pid, signal.SIGKILL)
        except (ValueError, ProcessLookupError):
            pass
        finally:
            self.pid_file.unlink(missing_ok=True)
            self.socket_file.unlink(missing_ok=True)

    def health(self) -> dict:
        return {
            "running": self.is_running(),
            "pid_file": str(self.pid_file),
            "socket": str(self.socket_file),
        }

    async def restart(self, working_dir: str) -> str:
        self.stop()
        return await self.ensure_running(working_dir)
```

- [ ] **Step 3: Run + commit**

### Task 4.4: Locate jcode binary (PATH-aware)

**Files:**
- Modify: `usr/plugins/jcode_harness/helpers/daemon.py`

- [ ] **Step 1: Test**

```python
def test_locate_binary_path_first(monkeypatch):
    """Existing jcode on PATH preferred over auto-downloaded."""
    monkeypatch.setattr("shutil.which", lambda x: "/usr/local/bin/jcode")
    from usr.plugins.jcode_harness.helpers.daemon import locate_jcode_binary
    assert locate_jcode_binary() == "/usr/local/bin/jcode"

def test_locate_binary_falls_back_to_amplihack(monkeypatch, tmp_path):
    monkeypatch.setattr("shutil.which", lambda x: None)
    bin_dir = tmp_path / "builds" / "stable"
    bin_dir.mkdir(parents=True)
    (bin_dir / "jcode").write_text("#!fake")
    monkeypatch.setattr(
        "usr.plugins.jcode_harness.helpers.paths.amplihack_root",
        lambda: tmp_path.parent,
    )
    from usr.plugins.jcode_harness.helpers.daemon import locate_jcode_binary
    # checks ~/.jcode/builds/stable/jcode then amplihack
    assert "stable/jcode" in locate_jcode_binary()
```

- [ ] **Step 2: Implementation**

```python
import shutil
from pathlib import Path

def locate_jcode_binary() -> str | None:
    # 1. PATH
    p = shutil.which("jcode")
    if p:
        return p
    # 2. user's ~/.jcode/builds/stable/
    stable = Path.home() / ".jcode" / "builds" / "stable" / "jcode"
    if stable.exists() and os.access(stable, os.X_OK):
        return str(stable)
    return None
```

- [ ] **Step 3: Commit**

### Task 4.5: Health endpoint + status JSON

- [ ] **Step 1: Test `health()` shape**

- [ ] **Step 2: Add uptime + last-error tracking**

```python
def health(self) -> dict:
    pid = None
    started_at = None
    if self.pid_file.exists():
        st = self.pid_file.stat()
        started_at = st.st_mtime
        pid = int(self.pid_file.read_text().strip())
    return {
        "running": self.is_running(),
        "pid": pid,
        "started_at": started_at,
        "uptime_s": (time.time() - started_at) if started_at else None,
        "socket": str(self.socket_file),
        "last_log": str(sorted(self.log_dir.glob("*.log"))[-1]) if any(self.log_dir.iterdir()) else None,
    }
```

- [ ] **Step 3: Commit**

### Task 4.6: Notification helper

**Files:**
- Create: `usr/plugins/jcode_harness/helpers/notifications.py`

- [ ] **Step 1: Wrap A0 notification API**

```python
from python.helpers.notification import AgentNotification

def info(msg: str, title: str = "jcode"):
    AgentNotification.info(title=title, body=msg)

def success(msg: str, title: str = "jcode"):
    AgentNotification.success(title=title, body=msg)

def warning(msg: str, title: str = "jcode"):
    AgentNotification.warning(title=title, body=msg)

def error(msg: str, title: str = "jcode"):
    AgentNotification.error(title=title, body=msg)
```

- [ ] **Step 2: Commit**

---

## Chunk 5: hooks.py install path

### Task 5.1: hooks.py install() function

**Files:**
- Create: `usr/plugins/jcode_harness/hooks.py`

- [ ] **Step 1: Test** — mock fetch + verify; assert `~/.amplihack/jcode/install.json` written.

- [ ] **Step 2: Implementation**

```python
# hooks.py
from pathlib import Path
import json
import shutil
import subprocess
import time

from usr.plugins.jcode_harness.helpers.arch import detect_release_asset_target
from usr.plugins.jcode_harness.helpers.download import (
    fetch_latest_release_metadata, pick_asset, download_and_verify,
)
from usr.plugins.jcode_harness.helpers.daemon import locate_jcode_binary
from usr.plugins.jcode_harness.helpers.paths import amplihack_root
from usr.plugins.jcode_harness.helpers import notifications as notify

INSTALL_TARGET = Path.home() / ".jcode" / "builds" / "stable" / "jcode"
INSTALL_META = lambda: amplihack_root() / "jcode" / "install.json"

async def install():
    notify.info("Setting up jcode harness…")

    # 1. PATH detect
    existing = locate_jcode_binary()
    if existing:
        notify.success(f"Found existing jcode at {existing}")
        binary_path = existing
    else:
        # 2. Download release
        notify.info("Downloading jcode binary…")
        release = fetch_latest_release_metadata()
        target = detect_release_asset_target()
        asset_url, sha_url = pick_asset(release, target)
        download_and_verify(asset_url, sha_url, INSTALL_TARGET)
        binary_path = str(INSTALL_TARGET)
        notify.success(f"jcode {release['tag_name']} installed at {binary_path}")

    # 3. Smoke test
    out = subprocess.check_output([binary_path, "--version"], text=True).strip()
    notify.info(f"Smoke test: {out}")

    # 4. cargo probe
    cargo_present = shutil.which("cargo") is not None

    # 5. Provider import (idempotent)
    from usr.plugins.jcode_harness.helpers.provider_import import import_a0_providers
    imported = import_a0_providers(binary_path)
    if imported:
        notify.success(f"Imported {len(imported)} A0 providers as jcode profiles")

    # 6. Persist install meta
    meta_path = INSTALL_META()
    meta_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    meta_path.write_text(json.dumps({
        "binary_path": binary_path,
        "version": out,
        "installed_at": int(time.time()),
        "self_dev_available": cargo_present,
    }))
    meta_path.chmod(0o600)

    notify.success("jcode_harness ready")
```

- [ ] **Step 3: Run + commit**

### Task 5.2: hooks.py pre_update()

```python
async def pre_update():
    """Stop daemon before plugin code is replaced."""
    from usr.plugins.jcode_harness.helpers.instance import compute_instance_id
    from usr.plugins.jcode_harness.helpers.paths import jcode_runtime_dir
    from usr.plugins.jcode_harness.helpers.daemon import DaemonSupervisor

    iid = compute_instance_id()
    instance_dir = jcode_runtime_dir(iid)
    bin_path = locate_jcode_binary()
    if bin_path:
        sup = DaemonSupervisor(bin_path, instance_dir)
        sup.stop()
    notify.info("jcode daemon stopped for plugin update")
```

- [ ] **Step 1: Test pre_update calls stop()**
- [ ] **Step 2: Commit**

### Task 5.3: hooks.py docker awareness check

- [ ] **Step 1: Detect overlayfs home (Docker)**

```python
def _is_overlay_fs(path: Path) -> bool:
    """Heuristic: df -T reports overlay for path."""
    try:
        out = subprocess.check_output(["df", "-T", str(path)], text=True)
        return "overlay" in out.split("\n")[1].lower()
    except Exception:
        return False
```

- [ ] **Step 2: In `install()`, warn if home is on overlay**

```python
if _is_overlay_fs(Path.home()):
    notify.warning("Home directory appears to be on an ephemeral container layer. "
                   "Mount ~/.jcode and ~/.amplihack as volumes to persist state.")
```

- [ ] **Step 3: Run + commit**

### Task 5.4: Auto-update flow

- [ ] **Step 1: Test `should_auto_update()` honors config + version diff**

- [ ] **Step 2: Implementation**

```python
async def maybe_auto_update():
    config = get_plugin_config()  # reads default_config + overrides
    if not config["binary"]["auto_update"]:
        return
    meta = json.loads(INSTALL_META().read_text())
    release = fetch_latest_release_metadata()
    if release["tag_name"] == meta["version"]:
        return
    notify.info(f"Updating jcode to {release['tag_name']}…")
    target = detect_release_asset_target()
    asset_url, sha_url = pick_asset(release, target)
    # stop daemon first
    pre_update()
    download_and_verify(asset_url, sha_url, INSTALL_TARGET)
    notify.success(f"Updated to {release['tag_name']}")
```

- [ ] **Step 3: Commit**

### Task 5.5: execute.py manual cleanup

**Files:**
- Create: `usr/plugins/jcode_harness/execute.py`

- [ ] **Step 1: Implement**

```python
#!/usr/bin/env python
"""Manual cleanup invoked from plugin UI."""
import sys
import shutil
from pathlib import Path

from usr.plugins.jcode_harness.helpers.paths import jcode_runtime_dir
from usr.plugins.jcode_harness.helpers.instance import compute_instance_id
from usr.plugins.jcode_harness.helpers.daemon import DaemonSupervisor, locate_jcode_binary

def main(also_delete_user_data: bool = False) -> int:
    iid = compute_instance_id()
    instance_dir = jcode_runtime_dir(iid)
    bin_path = locate_jcode_binary()
    if bin_path:
        sup = DaemonSupervisor(bin_path, instance_dir)
        sup.stop()
        print("daemon stopped")
    if instance_dir.exists():
        shutil.rmtree(instance_dir)
        print(f"removed {instance_dir}")
    if also_delete_user_data:
        user_data = Path.home() / ".jcode"
        if user_data.exists():
            shutil.rmtree(user_data)
            print(f"removed {user_data}")
    return 0

if __name__ == "__main__":
    sys.exit(main(also_delete_user_data="--delete-user-data" in sys.argv))
```

- [ ] **Step 2: Commit**

---

## Chunk 6: Provider importer

### Task 6.1: Read A0 providers

**Files:**
- Create: `usr/plugins/jcode_harness/helpers/provider_import.py`
- Test: `tests/unit/test_provider_import.py`

- [ ] **Step 1: Test parses A0 model_providers.yaml**

```python
def test_loads_a0_providers(monkeypatch, tmp_path):
    yaml_path = tmp_path / "model_providers.yaml"
    yaml_path.write_text("""
chat:
  acme:
    name: Acme LLM
    litellm_provider: openai
    kwargs:
      api_base: https://acme.example.com/v1
""")
    monkeypatch.setattr(
        "usr.plugins.jcode_harness.helpers.provider_import._a0_yaml_path",
        lambda: yaml_path,
    )
    from usr.plugins.jcode_harness.helpers.provider_import import discover_a0_providers
    providers = discover_a0_providers()
    assert any(p["id"] == "acme" for p in providers)
```

- [ ] **Step 2: Implementation**

```python
import os
import yaml
from pathlib import Path

def _a0_yaml_path() -> Path:
    return Path(__file__).resolve().parents[4] / "conf" / "model_providers.yaml"

def discover_a0_providers() -> list[dict]:
    p = _a0_yaml_path()
    if not p.exists():
        return []
    data = yaml.safe_load(p.read_text())
    out = []
    for kind, providers in (data or {}).items():
        for pid, cfg in (providers or {}).items():
            api_base = cfg.get("kwargs", {}).get("api_base")
            if not api_base:
                continue
            out.append({
                "id": pid,
                "name": cfg.get("name", pid),
                "kind": kind,
                "api_base": api_base,
                "default_model": cfg.get("kwargs", {}).get("default_model")
                                 or _first_model_from_settings(pid),
                "api_key_env": cfg.get("kwargs", {}).get("api_key_env")
                               or f"{pid.upper()}_API_KEY",
            })
    return out

def _first_model_from_settings(pid: str) -> str | None:
    """Read A0 settings for chosen model. Stubbed for now."""
    # TODO read python/helpers/settings.py
    return None
```

- [ ] **Step 3: Commit**

### Task 6.2: jcode provider add via stdin

- [ ] **Step 1: Test that key never appears in argv**

```python
def test_provider_add_uses_stdin(monkeypatch):
    captured_argv = []
    captured_stdin = []

    def fake_run(argv, input=None, **kw):
        captured_argv.append(argv)
        captured_stdin.append(input)
        return MagicMock(returncode=0, stdout=b'{"ok":true}', stderr=b"")

    monkeypatch.setattr("subprocess.run", fake_run)
    from usr.plugins.jcode_harness.helpers.provider_import import add_jcode_profile
    add_jcode_profile("/bin/jcode", "_a0_imported_acme",
                     "https://acme/v1", "gpt-4", "SECRET_KEY_VAL")
    argv = captured_argv[0]
    assert "SECRET_KEY_VAL" not in " ".join(argv)
    assert captured_stdin[0] == "SECRET_KEY_VAL"
    assert "--api-key-stdin" in argv
    assert "--model" in argv
    assert "gpt-4" in argv
```

- [ ] **Step 2: Implementation**

```python
import subprocess
import json

PLUGIN_PROFILE_PREFIX = "_a0_imported_"

def add_jcode_profile(jcode_bin: str, profile_name: str, base_url: str,
                       model: str, api_key: str, overwrite: bool = True) -> dict:
    if not profile_name.startswith(PLUGIN_PROFILE_PREFIX):
        raise ValueError(f"plugin-managed profiles must start with {PLUGIN_PROFILE_PREFIX}")
    cmd = [
        jcode_bin, "provider", "add", profile_name,
        "--base-url", base_url, "--model", model,
        "--api-key-stdin", "--json",
    ]
    if overwrite:
        cmd.append("--overwrite")
    result = subprocess.run(cmd, input=api_key, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"jcode provider add failed: {result.stderr}")
    return json.loads(result.stdout)

def list_jcode_profiles(jcode_bin: str) -> list[dict]:
    result = subprocess.run(
        [jcode_bin, "provider", "list", "--json"],
        capture_output=True, text=True, check=True,
    )
    return json.loads(result.stdout)
```

- [ ] **Step 3: Commit**

### Task 6.3: Collision-safe import_a0_providers

- [ ] **Step 1: Test collision check**

```python
def test_collision_with_user_profile_blocks_import(monkeypatch):
    """If user has profile 'acme' (no plugin prefix), import 'acme' refuses."""
    monkeypatch.setattr(
        "usr.plugins.jcode_harness.helpers.provider_import.list_jcode_profiles",
        lambda b: [{"name": "acme", "owner": "user"}],
    )
    from usr.plugins.jcode_harness.helpers.provider_import import import_a0_providers
    # The import should skip 'acme' (or alternative-name flow)
    skipped = import_a0_providers("/bin/jcode", providers=[{"id":"acme","api_base":"x"}])
    assert "acme" in skipped["skipped"]
```

- [ ] **Step 2: Implementation**

```python
def import_a0_providers(jcode_bin: str, providers: list[dict] | None = None,
                         api_keys: dict[str, str] | None = None) -> dict:
    """Returns {imported: [...], skipped: {...reason}}."""
    if providers is None:
        providers = discover_a0_providers()
    if api_keys is None:
        api_keys = {}
        for p in providers:
            env = p["api_key_env"]
            if env in os.environ:
                api_keys[p["id"]] = os.environ[env]

    existing = list_jcode_profiles(jcode_bin)
    user_owned = {p["name"] for p in existing
                  if not p["name"].startswith(PLUGIN_PROFILE_PREFIX)}
    imported, skipped = [], {}

    for p in providers:
        if p["id"] in user_owned:
            skipped[p["id"]] = "name collision with user profile"
            continue
        if p["id"] not in api_keys:
            skipped[p["id"]] = "no API key"
            continue
        if not p.get("default_model"):
            skipped[p["id"]] = "no default model"
            continue
        try:
            add_jcode_profile(
                jcode_bin,
                f"{PLUGIN_PROFILE_PREFIX}{p['id']}",
                p["api_base"], p["default_model"], api_keys[p["id"]],
                overwrite=True,
            )
            imported.append(p["id"])
        except Exception as e:
            skipped[p["id"]] = str(e)
    return {"imported": imported, "skipped": skipped}
```

- [ ] **Step 3: Commit**

### Task 6.4: Purge imported profiles function

```python
def purge_imported_profiles(jcode_bin: str) -> list[str]:
    profs = list_jcode_profiles(jcode_bin)
    purged = []
    for p in profs:
        if p["name"].startswith(PLUGIN_PROFILE_PREFIX):
            subprocess.run([jcode_bin, "provider", "remove", p["name"], "--json"],
                            check=True)
            purged.append(p["name"])
    return purged
```

- [ ] **Step 1: Test purge**
- [ ] **Step 2: Commit**

---

## Chunk 7: Tools (7 sub-chunks)

Each tool subclasses `python.helpers.tool.Tool`. Pattern:

```python
from python.helpers.tool import Tool, Response

class JcodeXxx(Tool):
    async def execute(self, **kwargs) -> Response:
        # 1. resolve daemon
        # 2. open client
        # 3. send + stream
        # 4. return Response(message=final, break_loop=False)
```

### Task 7.1: jcode_session

**Files:**
- Create: `usr/plugins/jcode_harness/tools/jcode_session.py`

- [ ] **Step 1: Test e2e (integration tier)**

```python
@pytest.mark.asyncio
async def test_jcode_session_streams_text(real_daemon):
    """Sends a 'hello' message, expects text deltas + done."""
    from usr.plugins.jcode_harness.tools.jcode_session import JcodeSession
    tool = JcodeSession.__new__(JcodeSession)  # bypass A0 init
    tool.agent = MagicMock()
    tool.agent.config.profile = ""
    tool.agent.context.id = "test-ctx-1"
    progress = []
    tool.set_progress = AsyncMock(side_effect=lambda c: progress.append(c))
    resp = await tool.execute(task="say hello")
    assert any("hello" in p.lower() for p in progress)
    assert resp.message
```

- [ ] **Step 2: Implementation**

```python
from python.helpers.tool import Tool, Response
from usr.plugins.jcode_harness.helpers.daemon import DaemonSupervisor, locate_jcode_binary
from usr.plugins.jcode_harness.helpers.jcode_client import JcodeClient
from usr.plugins.jcode_harness.helpers.paths import jcode_runtime_dir
from usr.plugins.jcode_harness.helpers.persistence import get_or_create_client_instance_id

class JcodeSession(Tool):
    async def execute(self, task: str = "", working_dir: str | None = None,
                       resume_session_id: str | None = None, **kw) -> Response:
        wd = working_dir or os.getcwd()
        bin_path = locate_jcode_binary()
        if not bin_path:
            return Response(message="jcode binary not installed", break_loop=False)

        sup = DaemonSupervisor(bin_path, jcode_runtime_dir())
        sock = await sup.ensure_running(wd)

        client_instance_id = get_or_create_client_instance_id(self.agent.context.id)
        client = JcodeClient()
        await client.connect(sock)
        try:
            await client.subscribe(wd, resume_session_id, client_instance_id, True)
            msg_id = await client.send_message(task)
            final_text = []
            async for ev in client.events():
                if ev.type == "text_delta":
                    final_text.append(ev.text)
                    await self.set_progress("".join(final_text))
                elif ev.type == "tool_start":
                    await self.set_progress(f"running tool: {ev.name}")
                elif ev.type == "memory_injected":
                    pass  # surface via side panel; no inline noise
                elif ev.type == "compaction" and getattr(ev, "cache_cold", False):
                    from usr.plugins.jcode_harness.helpers import notifications as notify
                    notify.warning(f"Cache went cold this turn (extra ~{ev.pre_tokens - ev.cache_creation_input or 0} tokens)")
                elif ev.type == "done" and ev.id == msg_id:
                    break
                elif ev.type == "interrupted":
                    break
            return Response(message="".join(final_text), break_loop=False)
        finally:
            await client.close()
```

- [ ] **Step 3: Commit**

### Task 7.2: jcode_grep

**Files:**
- Create: `usr/plugins/jcode_harness/tools/jcode_grep.py`

- [ ] **Step 1: Test**
- [ ] **Step 2: Implementation — short-lived session that calls agentgrep**

```python
class JcodeGrep(Tool):
    async def execute(self, pattern: str, path: str = ".", **kw) -> Response:
        # Open ephemeral session, invoke agentgrep tool via Message that ONLY calls agentgrep
        wd = os.path.abspath(path)
        bin_path = locate_jcode_binary()
        if not bin_path:
            return Response(message="jcode not installed", break_loop=False)
        sup = DaemonSupervisor(bin_path, jcode_runtime_dir())
        sock = await sup.ensure_running(wd)
        client = JcodeClient()
        await client.connect(sock)
        try:
            await client.subscribe(wd, None, str(uuid.uuid4()), False)
            await client.send_message(f"Use the agentgrep tool to search for: {pattern}")
            output = []
            async for ev in client.events():
                if ev.type == "tool_done" and ev.name == "agentgrep":
                    output.append(ev.output or "")
                elif ev.type == "done":
                    break
            return Response(message="\n".join(output), break_loop=False)
        finally:
            await client.close()
```

- [ ] **Step 3: Commit**

### Task 7.3: jcode_memory

```python
class JcodeMemory(Tool):
    async def execute(self, action: str, query: str = "", scope: str = "project",
                       content: str = "", **kw) -> Response:
        """action: remember | recall | search | forget | tag | link"""
        wd = os.getcwd()
        sock = await DaemonSupervisor(locate_jcode_binary(), jcode_runtime_dir()).ensure_running(wd)
        client = JcodeClient()
        await client.connect(sock)
        try:
            await client.subscribe(wd, None, str(uuid.uuid4()), False)
            prompt = self._memory_prompt(action, query, scope, content)
            await client.send_message(prompt)
            output = []
            async for ev in client.events():
                if ev.type == "tool_done" and ev.name == "memory_manage":
                    output.append(ev.output or "")
                elif ev.type == "done":
                    break
            return Response(message="\n".join(output), break_loop=False)
        finally:
            await client.close()

    @staticmethod
    def _memory_prompt(action, query, scope, content):
        return (f"Use the memory_manage tool with action={action}, "
                f"scope={scope}, query={query!r}, content={content!r}. Return raw output.")
```

- [ ] **Step 1: Test all 6 actions**
- [ ] **Step 2: Commit**

### Task 7.4: jcode_skill

Similar wrapper around `skill_manage` tool.

```python
class JcodeSkill(Tool):
    async def execute(self, action: str, name: str = "", **kw) -> Response:
        # Same pattern as jcode_memory; routes to skill_manage tool
        ...
```

- [ ] Tests + commit.

### Task 7.5: jcode_resume

```python
class JcodeResume(Tool):
    async def execute(self, session_id: str | None = None, **kw) -> Response:
        bin_path = locate_jcode_binary()
        if session_id is None:
            # list mode (subprocess fallback per Spike 0.2)
            result = subprocess.run([bin_path, "session", "list", "--json"],
                                     capture_output=True, text=True, check=True)
            sessions = json.loads(result.stdout)
            return Response(
                message="\n".join(f"{s['id']} ({s['provider_key']}): {s['title']}"
                                   for s in sessions),
                break_loop=False,
            )
        # resume mode
        wd = os.getcwd()
        sock = await DaemonSupervisor(bin_path, jcode_runtime_dir()).ensure_running(wd)
        client = JcodeClient()
        await client.connect(sock)
        try:
            cid = get_or_create_client_instance_id(self.agent.context.id)
            await client.resume_session(session_id, cid, allow_session_takeover=True)
            await client.subscribe(wd, session_id, cid, True)
            history = await client._recv_until(lambda e: e.type == "history")
            return Response(message=f"Resumed session {session_id}: {len(history.messages)} messages",
                             break_loop=False)
        finally:
            await client.close()
```

- [ ] Tests + commit.

### Task 7.6: jcode_swarm_msg

```python
class JcodeSwarmMsg(Tool):
    async def execute(self, action: str, target: str = "", content: str = "",
                       paths: list[str] = (), **kw) -> Response:
        """action: dm | broadcast | share | read"""
        client = await self._connect()  # helper
        try:
            if action in ("dm", "broadcast"):
                t = target if action == "dm" else "broadcast"
                await client._send(CommMessage(target=t, content=content))
            elif action == "share":
                await client._send(CommShare(paths=list(paths)))
            elif action == "read":
                await client._send(CommRead(paths=list(paths)))
            return Response(message=f"swarm {action} sent", break_loop=False)
        finally:
            await client.close()
```

- [ ] Tests + commit.

### Task 7.7: jcode_self_dev (gated)

```python
class JcodeSelfDev(Tool):
    async def execute(self, task: str, **kw) -> Response:
        if not shutil.which("cargo"):
            return Response(
                message="Self-dev requires Rust toolchain. Install from https://rustup.rs",
                break_loop=False,
            )
        # behaves like jcode_session but routes prompt to selfdev session
        prompt = f"Enter selfdev mode and: {task}"
        # delegate to JcodeSession.execute(task=prompt)
        return await JcodeSession().execute(task=prompt)

    @classmethod
    def discover(cls):
        """A0 tool discovery hook — return None if Rust absent."""
        if not shutil.which("cargo"):
            return None
        return cls
```

- [ ] **Test absent-cargo path returns clean error**
- [ ] **Commit**

---

## Chunk 8: Extensions (Python)

### Task 8.1: agent_init/jcode_register.py

**Files:**
- Create: `usr/plugins/jcode_harness/extensions/python/agent_init/jcode_register.py`

```python
"""Register jcode tools and pre-warm daemon on agent init."""
from python.helpers.extension import Extension

class JcodeRegister(Extension):
    async def execute(self, **kw):
        agent = kw.get("agent")
        # tools auto-discovered by A0; nothing to register manually
        # pre-warm daemon optional based on profile
        if getattr(agent.config, "profile", "") == "jcode_coder":
            from usr.plugins.jcode_harness.helpers.daemon import (
                DaemonSupervisor, locate_jcode_binary,
            )
            from usr.plugins.jcode_harness.helpers.paths import jcode_runtime_dir
            bin_path = locate_jcode_binary()
            if bin_path:
                sup = DaemonSupervisor(bin_path, jcode_runtime_dir())
                if not sup.is_running():
                    import asyncio
                    asyncio.create_task(sup.ensure_running(os.getcwd()))
```

- [ ] Tests + commit.

### Task 8.2: monologue_start/jcode_warmup.py

```python
"""Warm-up extension for jcode_coder profile (no loop short-circuit)."""
from python.helpers.extension import Extension

class JcodeWarmup(Extension):
    async def execute(self, loop_data=None, **kw):
        agent = self.agent
        if getattr(agent.config, "profile", "") != "jcode_coder":
            return
        from usr.plugins.jcode_harness.helpers.daemon import (
            DaemonSupervisor, locate_jcode_binary,
        )
        from usr.plugins.jcode_harness.helpers.paths import jcode_runtime_dir
        bin_path = locate_jcode_binary()
        if not bin_path:
            return
        sup = DaemonSupervisor(bin_path, jcode_runtime_dir())
        if not sup.is_running():
            await sup.ensure_running(os.getcwd())
```

- [ ] Tests + commit.

---

## Chunk 9: WebUI

### Task 9.1: webui/main.html — daemon status + session list

**Files:**
- Create: `usr/plugins/jcode_harness/webui/main.html`
- Create: `usr/plugins/jcode_harness/webui/main.js`

```html
<!-- main.html -->
<div x-data="jcodeMain()" x-init="init()">
  <h2>jcode Harness</h2>

  <section class="daemon-status">
    <h3>Daemon</h3>
    <div x-text="daemon.running ? 'Running (PID ' + daemon.pid + ')' : 'Stopped'"></div>
    <div x-show="daemon.running" x-text="'Uptime: ' + daemon.uptime_s + 's'"></div>
    <button @click="restartDaemon()" x-show="daemon.running">Restart</button>
    <button @click="startDaemon()" x-show="!daemon.running">Start</button>
  </section>

  <section class="sessions">
    <h3>Resumable Sessions</h3>
    <button @click="refreshSessions()">Refresh</button>
    <template x-for="s in sessions" :key="s.id">
      <div class="session-row">
        <span class="provider-badge" x-text="s.provider_key"></span>
        <span x-text="s.title || s.id"></span>
        <span x-text="s.updated_at"></span>
        <button @click="resumeSession(s.id)">Resume</button>
      </div>
    </template>
  </section>

  <section class="providers">
    <h3>Providers</h3>
    <button @click="oauthLogin('claude')">Login with Claude (OAuth)</button>
    <button @click="oauthLogin('openai')">Login with OpenAI (OAuth)</button>
    <button @click="oauthLogin('gemini')">Login with Gemini (OAuth)</button>
    <button @click="purgeImported()">Purge imported A0 keys</button>
  </section>
</div>
```

```javascript
// main.js
window.jcodeMain = function() {
  return {
    daemon: { running: false },
    sessions: [],
    async init() { await this.refresh(); },
    async refresh() {
      const r1 = await fetch('/api/plugins/jcode_harness/daemon_status');
      this.daemon = await r1.json();
      await this.refreshSessions();
    },
    async refreshSessions() {
      const r = await fetch('/api/plugins/jcode_harness/list_sessions');
      this.sessions = (await r.json()).sessions || [];
    },
    async resumeSession(id) {
      const r = await fetch('/api/plugins/jcode_harness/resume_session', {
        method: 'POST',
        body: JSON.stringify({ session_id: id }),
      });
      const d = await r.json();
      $store.notificationStore.frontendSuccess(`Resumed ${id}`);
    },
    async oauthLogin(provider) {
      const r = await fetch('/api/plugins/jcode_harness/login_provider', {
        method: 'POST',
        body: JSON.stringify({ provider }),
      });
      const d = await r.json();
      window.open(d.auth_url, '_blank');
    },
    async purgeImported() {
      const r = await fetch('/api/plugins/jcode_harness/purge_imported_profiles', {method:'POST'});
      const d = await r.json();
      $store.notificationStore.frontendSuccess(`Purged ${d.purged.length} profiles`);
    },
    async restartDaemon() { /* TODO */ },
    async startDaemon() { /* TODO */ },
  };
};
```

- [ ] Tests via Playwright + commit.

### Task 9.2: webui/config.html

Settings UI bound to `default_config.yaml` schema. Per AGENTS.plugins.md §4 use `config.*` and `context.*` bindings.

- [ ] Implement + commit.

### Task 9.3: side-panel-start extension (jcode SidePanel events)

Per Spike 0.5, decide breakpoint vs custom surface. Implement.

- [ ] Tests + commit.

### Task 9.4: sidebar-quick-actions-main-start

"New jcode session" + "Resume" buttons.

- [ ] Tests + commit.

### Task 9.5: Notification integration

Confirm all errors surface through `notificationStore.frontendError/Success/Warning`. Add lint rule (grep for inline error divs).

- [ ] Commit.

---

## Chunk 10: Profile + execute.py cleanup

### Task 10.1: agents/jcode_coder/agent.yaml

Already specified in spec §5.9. Just commit the file.

- [ ] Commit.

### Task 10.2: execute.py cleanup test

- [ ] **Step 1: Test cleanup removes only ~/.amplihack/jcode/<id>/, not ~/.jcode/**
- [ ] **Step 2: Test --delete-user-data flag removes ~/.jcode/ when set**
- [ ] **Commit**

---

## Chunk 11: API handlers

### Task 11.1: api/list_sessions.py

```python
from python.helpers.api import ApiHandler
import subprocess, json

from usr.plugins.jcode_harness.helpers.daemon import locate_jcode_binary

class ListSessions(ApiHandler):
    async def handle(self, request):
        bin_path = locate_jcode_binary()
        if not bin_path:
            return {"sessions": [], "error": "jcode not installed"}
        try:
            out = subprocess.check_output([bin_path, "session", "list", "--json"], text=True)
            return {"sessions": json.loads(out)}
        except subprocess.CalledProcessError as e:
            return {"sessions": [], "error": str(e)}
```

- [ ] Test + commit.

### Task 11.2: api/resume_session.py

- [ ] Implementation + commit.

### Task 11.3: api/login_provider.py

```python
class LoginProvider(ApiHandler):
    async def handle(self, request):
        body = await request.json()
        provider = body["provider"]
        bin_path = locate_jcode_binary()
        out = subprocess.check_output(
            [bin_path, "login", "--provider", provider, "--print-auth-url", "--json"],
            text=True,
        )
        data = json.loads(out)
        return {"auth_url": data.get("auth_url"), "user_code": data.get("user_code")}
```

- [ ] Test + commit.

### Task 11.4: api/daemon_status.py

```python
class DaemonStatus(ApiHandler):
    async def handle(self, request):
        from usr.plugins.jcode_harness.helpers.daemon import (
            DaemonSupervisor, locate_jcode_binary,
        )
        from usr.plugins.jcode_harness.helpers.paths import jcode_runtime_dir
        bin_path = locate_jcode_binary()
        if not bin_path:
            return {"running": False, "error": "binary not installed"}
        sup = DaemonSupervisor(bin_path, jcode_runtime_dir())
        return sup.health()
```

- [ ] Test + commit.

### Task 11.5: api/purge_imported_profiles.py

```python
class PurgeImported(ApiHandler):
    async def handle(self, request):
        from usr.plugins.jcode_harness.helpers.provider_import import purge_imported_profiles
        from usr.plugins.jcode_harness.helpers.daemon import locate_jcode_binary
        purged = purge_imported_profiles(locate_jcode_binary())
        return {"purged": purged}
```

- [ ] Test + commit.

---

## Chunk 12: Integration & acceptance tests

### Task 12.1: conftest.py spawns real daemon for integration tier

```python
# tests/integration/conftest.py
import asyncio, os, shutil
import pytest
import pytest_asyncio
from pathlib import Path
import subprocess, time

@pytest_asyncio.fixture
async def real_daemon(tmp_path):
    bin_path = shutil.which("jcode") or str(Path.home() / ".jcode/builds/stable/jcode")
    if not Path(bin_path).exists():
        pytest.skip("jcode binary not available")
    sock = tmp_path / "test.sock"
    overlay = tmp_path / "config.toml"
    overlay.write_text("[gateway]\nenabled = false\n")
    proc = subprocess.Popen(
        [bin_path, "--socket", str(sock), "serve", "--owner-pid", str(os.getpid())],
        env={**os.environ, "JCODE_CONFIG": str(overlay)},
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    deadline = time.time() + 5
    while not sock.exists() and time.time() < deadline:
        await asyncio.sleep(0.1)
    yield {"socket": str(sock), "pid": proc.pid}
    proc.terminate()
    proc.wait(timeout=5)
```

- [ ] Commit.

### Task 12.2: Lifecycle integration tests

Per spec §9.3 critical-test-cases list. One test file per area.

- [ ] Implement + commit per file.

### Task 12.3: Performance benchmarks (`tests/perf/`)

Per spec §6.4 / §9.4 targets:
- TTFT <500ms warm
- Daemon boot <2s M1 / <4s Linux x86_64
- RAM <200MB total, ~12MB/session
- jcode_grep <150ms p50 / <300ms p99

- [ ] Implement using `pytest-benchmark` + commit.

### Task 12.4: Security smoke tests

```python
def test_no_keys_in_ps_output_after_provider_import():
    """Run import; immediately check ps -E aux on macOS / /proc on Linux."""
    ...

def test_socket_perms_0600():
    ...

def test_uninstall_leaves_jcode_user_data():
    ...
```

- [ ] Implement + commit.

### Task 12.5: WebUI tests (Playwright)

- [ ] main.html loads, daemon status updates
- [ ] Resume button kicks off session
- [ ] OAuth login button opens new tab
- [ ] Settings save/load round-trips

### Task 12.6: Acceptance gate

Run full suite; checklist against spec §10:

- [ ] All 7 tools work with real daemon
- [ ] Cross-harness resume works for at least 4 source harnesses
- [ ] Memory + skills function
- [ ] Swarm messaging works between two A0 instances
- [ ] Self-dev gracefully degrades without Rust
- [ ] Performance targets met
- [ ] Security checks pass
- [ ] Plugin installs in <30s
- [ ] Plugin uninstalls cleanly

---

## Chunk 13: Docs + plugin index prep

### Task 13.1: README.md

User-facing install instructions (1 page). Sections: Install, Quick Start (5-step), Provider Login, Cross-harness Resume, Settings reference, Troubleshooting.

- [ ] Write + commit.

### Task 13.2: Troubleshooting guide

`docs/agents/plugins/jcode_harness/troubleshooting.md`. Cover: daemon won't start, login flows, missing binary, cache cold warnings, Rust toolchain for self-dev, Docker volume mounts.

- [ ] Write + commit.

### Task 13.3: Settings reference

`docs/agents/plugins/jcode_harness/settings.md`. Document each `default_config.yaml` field.

- [ ] Write + commit.

### Task 13.4: Plugin Index `index.yaml` (separate community PR)

```yaml
title: jcode Coding Harness
description: Embeds jcode coding agent (memory graph, skills, swarm, 28 tools) into Agent Zero.
github: https://github.com/<owner>/jcode_harness
tags:
  - tools
  - coding
  - agent
  - memory
screenshots:
  - <screenshot URLs>
```

- [ ] File separately to `agent0ai/a0-plugins`. Not committed to A0 repo. Mark task complete when PR opened.

---

## Done criteria

All chunks committed. Acceptance gate (12.6) green. Plugin manifest validates against AGENTS.plugins.md. README + LICENSE present. Plugin Index PR open.

After done, hand off to user for live walkthrough.
