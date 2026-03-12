# QMD Plugin for Agent Zero — Design Spec

**Date:** 2026-03-12
**Status:** Approved
**Branch:** `qmd_plugin`

---

## Overview

The QMD plugin integrates [QMD (Query Markup Documents)](https://github.com/tobi/qmd) into Agent Zero as a first-class knowledge search capability. QMD provides hybrid on-device search combining BM25 full-text search, vector semantic search, and LLM re-ranking — all running locally via GGUF models.

The plugin gives Agent Zero agents the ability to search markdown notes, documentation, meeting transcripts, and any markdown knowledge base indexed by QMD.

---

## Decisions

| Dimension | Choice | Rationale |
|-----------|--------|-----------|
| Integration mode | SDK-based | Full SDK control vs. CLI or MCP |
| Python↔Node.js bridge | Persistent subprocess (stdin/stdout) | Keep models warm, own lifecycle, no ports |
| Bridge protocol | Line-delimited JSON-RPC 2.0 | Standardized, framing-free, same as MCP stdio |
| Scope | Tiered access | Search always on; management gated by config |
| Auto-configuration | Auto-index project directory | High-value default, no filesystem over-reach |
| Subprocess lifecycle | Lazy start, alive for session | No cost if unused; no restart penalty once started |
| WebUI | Config UI only | Focused; users can use QMD CLI directly |

---

## File Structure

```
usr/plugins/qmd/
├── plugin.yaml
├── default_config.yaml
├── initialize.py
├── bridge/
│   ├── package.json
│   └── bridge.js
├── helpers/
│   └── qmd_client.py
├── tools/
│   ├── qmd_search.py
│   ├── qmd_get.py
│   ├── qmd_status.py
│   └── qmd_manage.py
├── extensions/
│   └── python/
│       ├── system_prompt/
│       │   └── _20_qmd_prompt.py
│       └── agent_init/
│           └── _30_qmd_auto_index.py
├── prompts/
│   └── qmd_tools.md
├── api/
│   └── qmd_status_api.py
└── webui/
    └── config.html
```

---

## Component Designs

### 1. Bridge (`bridge/bridge.js`)

A Node.js script that imports the `@tobilu/qmd` SDK, creates a `QMDStore`, and processes line-delimited JSON-RPC requests from stdin.

**Startup sequence:**
1. Read `QMD_DB_PATH` env var (defaults to QMD's own default: `~/.cache/qmd/index.sqlite`)
2. Call `createStore({ dbPath })` — opens SQLite, prepares FTS/vector indexes
3. Write `{"ready":true}\n` to stdout
4. Enter readline loop

**Protocol:** JSON-RPC 2.0, line-delimited
Request: `{"jsonrpc":"2.0","id":N,"method":"...","params":{...}}\n`
Response: `{"jsonrpc":"2.0","id":N,"result":{...}}\n`
Error: `{"jsonrpc":"2.0","id":N,"error":{"code":-32000,"message":"..."}}\n`

**Methods exposed:**

| Method | Gated | Description |
|--------|-------|-------------|
| `ping` | No | Health check |
| `query` | No | Hybrid search: expansion + BM25 + vector + reranking |
| `search` | No | BM25 keyword search only |
| `vsearch` | No | Vector similarity search only |
| `get` | No | Retrieve document by path or `#docid` |
| `multi_get` | No | Batch retrieve by glob or comma-separated list |
| `status` | No | Index health + collection list |
| `collection_list` | No | List collections |
| `context_list` | No | List contexts |
| `collection_add` | Yes | Add directory as collection |
| `collection_remove` | Yes | Remove collection |
| `context_add` | Yes | Add context metadata to path |
| `context_remove` | Yes | Remove context |
| `update` | Yes | Re-index filesystem |
| `embed` | Yes | Generate/refresh vector embeddings |

**Shutdown:** On `SIGTERM` or stdin close → `store.close()` then `process.exit(0)`

**Bridge package.json:**
```json
{
  "name": "agent-zero-qmd-bridge",
  "version": "1.0.0",
  "type": "module",
  "dependencies": { "@tobilu/qmd": "latest" },
  "engines": { "node": ">=22" }
}
```

---

### 2. Python Client (`helpers/qmd_client.py`)

Singleton async client per agent session. Manages subprocess lifecycle and serializes JSON-RPC calls.

**Interface:**
```python
class QMDClient:
    async def start(self, db_path: str = None) -> None
    async def stop(self) -> None
    async def call(self, method: str, params: dict = None, gated: bool = False) -> dict
    def is_running(self) -> bool
```

**Lifecycle:**
- Stored per-agent via `agent.set_data("qmd_client", client)`
- Created lazily on first tool call
- `start()` spawns `node bridge/bridge.js`, awaits `{"ready":true}` (30s timeout)
- `call()` uses `asyncio.Lock` — one request at a time
- Auto-respawn if subprocess dies mid-session
- `stop()` closes stdin, waits for clean exit

**Timeouts:**
- `query`, `embed`: 60s
- `get`, `status`, `ping`, management: 10s

**Gating:** `call(..., gated=True)` checks plugin config for `management_enabled`; returns error string if disabled.

---

### 3. Agent Tools

#### `qmd_search.py`
Search across indexed collections.

Parameters:
- `mode`: `"query"` (default, best quality) | `"search"` (BM25 only, fast) | `"vsearch"` (vector only)
- `q`: query string — plain text or QMD query syntax (`lex:`, `vec:`, `hyde:`, `intent:`)
- `collections`: optional list to restrict search
- `limit`: number of results (default 5, max 10)
- `min_score`: float threshold (default 0.0)
- `intent`: disambiguation context string
- `explain`: include score traces

Response: formatted results — title, path, docid, score, snippet, context. Snippets capped at 500 chars.

#### `qmd_get.py`
Retrieve document content.

Parameters:
- `path`: file path or `#docid` (for single get)
- `pattern`: glob or comma-separated list (for multi-get; explicit, not auto-detected)
- `full`: return full content (default false)
- `line_numbers`: add line numbers (default false)
- `from_line`: start line
- `max_lines`: cap (default 200)
- `max_bytes`: for multi-get, skip files over this size (default 10240)

The agent provides either `path` (single get) or `pattern` (multi-get) — explicit parameters rather than auto-detection from string contents. This avoids misclassifying file paths that legitimately contain commas.

#### `qmd_status.py`
No parameters. Returns collection names, document counts, embedding coverage, index health, subprocess state.

#### `qmd_manage.py` _(gated)_
Parameters:
- `action`: `"collection_add"` | `"collection_remove"` | `"context_add"` | `"context_remove"` | `"update"` | `"embed"`
- Action-specific: `name`, `path`, `mask`, `text`, `force`, `pull`

All actions blocked (with clear message) if `management_enabled` is false.

---

### 4. Extensions

#### `extensions/python/system_prompt/_20_qmd_prompt.py`
Appends `prompts/qmd_tools.md` to the agent's system prompt. The template is rendered with a dynamically injected list of available QMD collections (fetched from bridge, cached 10 minutes). Teaches the agent:
- When to use each search mode
- QMD query syntax (`lex:`, `vec:`, `hyde:`, `intent:`)
- The search → get pattern (search returns docids, then `get #docid` for full content)

#### `extensions/python/agent_init/_30_qmd_auto_index.py`
Fires once per agent context. If `auto_index_project` is enabled:
1. Check if a collection for `agent.get_data("cwd")` exists
2. If not → `collection_add` that path
3. If embeddings are stale → fire `embed()` as a `DeferredTask` (non-blocking):
   ```python
   from helpers.defer import DeferredTask
   async def run_embed():
       await client.call("embed", {})
   DeferredTask().start_task(run_embed)  # pass callable, not run_embed()
   ```
4. Set `agent.set_data("qmd_auto_indexed", True)` to skip on re-init

Guard: skip for sub-agents (`if self.agent.number != 0: return`) — auto-indexing is a root-agent concern only.

Skipped entirely if `management_enabled` is false.

---

### 5. Configuration

#### `default_config.yaml`
```yaml
management_enabled: false
auto_index_project: true
db_path: ""
bridge_startup_timeout: 30
request_timeout_search: 60
request_timeout_default: 10
```

#### `plugin.yaml`
```yaml
title: QMD Knowledge Search
description: Local hybrid search for markdown notes, docs, and knowledge bases. BM25 + vector + LLM reranking, fully on-device.
version: 1.0.0
settings_sections:
  - agent
per_project_config: false
always_enabled: false
```

Note: Node.js >= 22 is a runtime requirement enforced in `initialize.py` (not a plugin.yaml field — no such field exists in the A0 manifest schema).

#### `webui/config.html`
Settings panel fields:
- Management access toggle (`management_enabled`)
- Auto-index project toggle (`auto_index_project`)
- Database path text field (placeholder: `~/.cache/qmd/index.sqlite`)
- Status card: subprocess state + collection count (via `api/qmd_status_api.py`)

#### `api/status.py`
Route: `GET /api/plugins/qmd/status` (file must be named `status.py` to produce this URL)

The handler must override `get_methods()` to accept GET requests (default is POST):
```python
@classmethod
def get_methods(cls) -> list[str]:
    return ["GET"]
```

To access the `QMDClient` from a stateless Flask handler, use the `use_context(ctxid)` pattern:
```python
async def process(self, input: dict, request: Request):
    ctxid = input.get("ctxid", "")
    context = self.use_context(ctxid) if ctxid else None
    agent = context.streaming_agent if context else None
    client = agent.get_data("qmd_client") if agent else None
    running = client.is_running() if client else False
    # ... return status
```

The config UI passes `ctxid` in the request body identifying the current agent session.
Returns: `{running: bool, collections: [...], subprocess_pid: int|null}`

---

### 6. Initialization (`initialize.py`)

Follows A0 convention: defines a `main() -> int` function, returns 0 on success, non-zero on failure.

```python
def main() -> int:
    # 1. Verify node >= 22
    # 2. cd bridge/ && npm install
    # 3. node bridge.js --selftest
    # 4. print success message
    return 0

if __name__ == "__main__":
    import sys
    sys.exit(main())
```

Steps:
1. Verify `node --version` >= 22 (print install instructions and return 1 if missing)
2. `cd bridge/ && npm install` (installs `@tobilu/qmd`)
3. Run `node bridge.js --selftest` (bridge starts, calls ping, exits cleanly)
4. Print: "QMD bridge ready. Run `qmd embed` to generate embeddings for your collections."

**npm package:** `@tobilu/qmd` (confirmed — this is the published npm package name for `github.com/tobi/qmd`).

---

## Data Flow

```
Agent                     qmd_client.py              bridge.js             QMD SDK
  │                            │                          │                    │
  │── call qmd_search ────────►│                          │                    │
  │                            │── spawn subprocess ─────►│                    │
  │                            │◄─ {"ready":true} ────────│                    │
  │                            │── {"method":"query"} ───►│                    │
  │                            │                          │── store.search() ─►│
  │                            │                          │◄─ results ──────────│
  │                            │◄─ {"result":{items}} ────│                    │
  │◄── formatted results ──────│                          │                    │
```

---

## Error Handling

| Scenario | Behavior |
|----------|----------|
| Node.js not installed | `initialize.py` fails with install instructions |
| Bridge startup timeout | Clear error: "QMD not installed. Run plugin initialization." |
| Subprocess dies mid-session | Auto-respawn on next `call()` |
| Management op while disabled | Error: "Management operations are disabled. Enable in plugin settings." |
| QMD not installed (no index) | `status` returns empty collections; agent is guided to run setup |
| `embed` on large collection | Non-blocking via `DeferredTask`; agent unblocked immediately |

---

## Out of Scope

- WebUI search interface (users can use QMD CLI)
- Multi-index support (one SQLite db per plugin instance)
- QMD installation management (users install `@tobilu/qmd` separately or via initialize.py)
- Authentication / access control for the QMD index
