# EdgeQuake Plugin for Agent Zero

## Overview

A plugin integrating EdgeQuake (graph-enhanced RAG framework) into Agent Zero's plugin system. Provides the agent with knowledge graph-powered document ingestion, hybrid retrieval queries, and entity exploration.

Three phases: agent tools + settings (Phase 1), user-facing UI (Phase 2), and pipeline integration (Phase 3).

---

## Plugin Structure

```
plugins/edgequake/
├── helpers/
│   └── edgequake_client.py
├── tools/
│   └── edgequake.py
├── api/
│   └── edgequake_settings.py
├── extensions/
│   ├── python/                              # Phase 3
│   │   ├── monologue_end/
│   │   │   └── edgequake_index.py
│   │   └── message_loop_prompts_after/
│   │       └── edgequake_recall.py
│   └── webui/
│       └── sidebar-quick-actions-main-start/
│           └── edgequake-button.html
├── webui/
│   ├── edgequake-settings.html
│   ├── documents/                           # Phase 2
│   │   ├── documents-modal.html
│   │   └── documents-store.js
│   ├── graph/                               # Phase 2
│   │   ├── graph-modal.html
│   │   └── graph-store.js
│   └── query/                               # Phase 2
│       ├── query-modal.html
│       └── query-store.js
└── prompts/
    └── agent.system.tool.edgequake.md
```

---

## Phase 1: Agent Tools + Settings (Implementation Spec)

### Design Decisions

- **Single tool with method routing** — matches A0's convention (skills_tool, code_execution_tool). One tool entry, six methods.
- **Settings tab in A0's settings modal** — no env var fallback, settings UI only. Keeps configuration discoverable.
- **Graceful degradation** — tool returns helpful Response when not configured rather than raising errors.
- **Cached client** — SDK client instantiated once and reused. Cache invalidated when settings change.

### File 1: `helpers/edgequake_client.py`

Shared SDK client factory used by all other plugin files.

**Exports:**

| Function | Signature | Purpose |
|----------|-----------|---------|
| `get_edgequake_settings` | `() -> dict` | Read EdgeQuake config from A0 settings |
| `get_edgequake_client` | `() -> EdgeQuake \| None` | Cached client factory. Returns `None` if `api_key` missing |
| `test_connection` | `(client: EdgeQuake) -> dict` | Calls `client.health()`, returns status dict |

**Settings keys:**

| Key | Required | Default |
|-----|----------|---------|
| `edgequake_base_url` | Yes | `http://localhost:8080` |
| `edgequake_api_key` | Yes | *(none)* |
| `edgequake_workspace_id` | No | *(none)* |
| `edgequake_tenant_id` | No | *(none)* |
| `edgequake_timeout` | No | `30` |

**Caching strategy:**

- Module-level `_cached_client` and `_cached_hash` variables
- `_settings_hash(settings) -> str` computes a hash of config values
- On each `get_edgequake_client()` call, compare current hash to cached hash
- If mismatch, discard old client and create new one
- If `api_key` is empty/missing, return `None` (no client)

### File 2: `tools/edgequake.py`

Single `Tool` subclass with method-based routing.

**Class:** `EdgequakeTool(Tool)`

**Method routing in `execute()`:**

| Method | Args | SDK Call | Response Format |
|--------|------|----------|-----------------|
| `query` | `query` (required), `mode` (optional, default: `hybrid`) | `client.query.execute(query=query, mode=mode)` | Answer text with sources |
| `upload` | `content` (required), `title` (optional) | `client.documents.upload(content=content, title=title)` | Document ID and processing status |
| `list_documents` | `page` (optional), `limit` (optional) | `client.documents.list(page=page, limit=limit)` | Formatted document table |
| `search_entities` | `keyword` (required) | `client.graph.search(keyword=keyword)` | Entity names, types, and relationships |
| `graph_stats` | *(none)* | `client.graph.get()` | Entity count, relationship count, label summary |
| `health` | *(none)* | `client.health()` | Status, version, storage mode, provider |

**Execution flow:**

1. Call `get_edgequake_client()`
2. If `None`: return `Response(message="EdgeQuake is not configured. The user needs to set it up in Settings > EdgeQuake with a server URL and API key.")`
3. Route to method handler based on `self.method`
4. Wrap SDK call in try/except:
   - Connection errors: `"EdgeQuake server is unreachable at {url}. Check that the server is running."`
   - Auth errors: `"EdgeQuake authentication failed. The API key may be invalid."`
   - Timeout errors: `"EdgeQuake request timed out. The server may be overloaded."`
   - Generic errors: `"EdgeQuake error: {str(e)}"`
5. Format successful result into readable text
6. Return `Response(message=formatted_result)`

**Logging:** Each method calls `self.set_progress(f"EdgeQuake: {action}...")` before the SDK call for visibility in A0's process group UI.

### File 3: `prompts/agent.system.tool.edgequake.md`

```markdown
## Tool: edgequake

Knowledge graph-powered RAG system. Use for deep research,
document ingestion, and entity exploration.

### When to use
- User asks a knowledge-intensive question and you need
  richer context than conversation history provides
- User wants to store documents/knowledge for future retrieval
- User asks about relationships between concepts, people,
  or entities
- User wants to explore what's in the knowledge base

### Methods

**query** — Search the knowledge graph
- query: (required) the question to ask
- mode: (optional) naive|local|global|hybrid|mix|bypass
  (default: hybrid)

**upload** — Ingest a document into the knowledge graph
- content: (required) text content to ingest
- title: (optional) document title

**list_documents** — List ingested documents
- page: (optional) page number
- limit: (optional) results per page

**search_entities** — Find entities in the knowledge graph
- keyword: (required) search term

**graph_stats** — Get knowledge graph overview statistics

**health** — Check EdgeQuake connection status
```

### File 4: `api/edgequake_settings.py`

API handler for settings read/write and connection testing.

**Class:** `EdgequakeSettings(ApiHandler)`

**Auth:** `requires_auth() = True`, `requires_csrf() = True`

**Method:** POST only (default)

**`process()` routes on `input["action"]`:**

| Action | Input | Behavior | Response |
|--------|-------|----------|----------|
| `load` | *(none)* | Read settings from A0 settings store | `{ settings: { base_url, api_key (masked), workspace_id, tenant_id, timeout } }` |
| `save` | `settings: { ... }` | Validate required fields, persist to settings store, invalidate client cache | `{ success: true }` or `{ error: "..." }` |
| `test` | `settings: { ... }` | Create temporary client from provided values (not saved), call `test_connection()` | `{ status, version, storage_mode, llm_provider_name }` or `{ error: "..." }` |

**Note on `test`:** Uses the provided settings values directly (not the saved ones) so users can test before committing. This means creating a one-off `EdgeQuake` client instance that is not cached.

**API key masking on `load`:** Returns `api_key` as `"••••" + last_4_chars` for display. The full key is only written, never read back through the API.

### File 5: `webui/edgequake-settings.html`

Alpine component for the settings tab.

**Store:** `edgequakeSettings` via `createStore()`

**Store shape:**

```javascript
{
  base_url: "http://localhost:8080",
  api_key: "",
  workspace_id: "",
  tenant_id: "",
  timeout: 30,
  connection_status: null,   // null | "testing" | "connected" | "error"
  connection_info: "",       // status detail text
  loading: false,

  async load() { ... },      // GET settings on tab open
  async save() { ... },      // POST save
  async testConnection() { ... },  // POST test
  destroy() { ... }          // Reset transient state
}
```

**UI layout:**

- Uses A0's `.field` / `.field-control` pattern
- Four input fields: Server URL, API Key (password + toggle), Workspace ID, Tenant ID
- Timeout as number input
- "Test Connection" button with status indicator (green dot = connected, red = error, spinner = testing)
- Footer with Save / Cancel buttons using `.btn.btn-ok` and `.btn.btn-cancel`

**Lifecycle:**

- `x-create="$store.edgequakeSettings.load()"` — load settings on mount
- `x-destroy="$store.edgequakeSettings.destroy()"` — clear transient state

### File 6: `extensions/webui/sidebar-quick-actions-main-start/edgequake-button.html`

Sidebar entry point.

```html
<div x-data>
  <button
    x-move-after=".config-button#dashboard"
    class="config-button"
    id="edgequake"
    @click="openModal('settings/settings.html');
           setTimeout(() => scrollModal('edgequake'), 100)"
    title="EdgeQuake">
    <span class="material-symbols-outlined">hub</span>
  </button>
</div>
```

Follows A0-PLUGINS.md baseline: root `x-data` + explicit `x-move-after` directive.

---

## Phase 2: User-Facing UI (Design Only)

### Document Browser Modal

**Path:** `webui/documents/documents-modal.html`

- Paginated table: title, status (Processing/Completed/Failed), date, entity count
- Upload: text paste or file drop → `client.documents.upload()`
- Delete with `$confirmClick` confirmation
- Row click → entity/relationship detail view
- Store: `edgequakeDocuments` — handles pagination, upload, delete, polling for processing status

### Knowledge Graph Explorer Modal

**Path:** `webui/graph/graph-modal.html`

- Search bar for entity lookup via `client.graph.search()`
- Entity detail panel: name, type, description, connected entities
- Relationship list: source → relationship → target
- Initial version uses list/tree view; future enhancement could add Sigma.js graph visualization
- Store: `edgequakeGraph` — handles search, entity detail loading, neighborhood traversal

### Query Playground Modal

**Path:** `webui/query/query-modal.html`

- Text input for ad-hoc queries (outside agent conversation)
- Mode selector dropdown: naive, local, global, hybrid, mix, bypass
- Streaming response display via SSE (`client.query.stream()`)
- Query history (session-scoped, stored in Alpine store)
- Store: `edgequakeQuery` — handles query execution, mode selection, streaming

### Sidebar Changes in Phase 2

The single sidebar button evolves into a dropdown menu:
- Settings (opens settings tab)
- Documents (opens document browser modal)
- Graph (opens graph explorer modal)
- Query (opens query playground modal)

---

## Phase 3: Pipeline Integration (Design Only)

### Conversation Indexing Extension

**Path:** `extensions/python/monologue_end/edgequake_index.py`

**Hook:** `monologue_end` — fires after agent completes a response.

**Behavior:**
- Extracts the conversation turn (user message + agent response)
- Buffers turns; flushes to `client.documents.upload()` every N turns or on conversation end
- Tags uploaded documents with metadata: `source: "a0-conversation"`, `context_id`, `timestamp`
- Deduplicates by content hash to avoid re-uploading identical turns
- Configurable via settings: enable/disable toggle, batch size, content filter

**Guard rails:**
- Only fires if EdgeQuake is configured and healthy
- Skips if auto-indexing is disabled in settings
- Non-blocking: failures are logged but don't interrupt the agent

### Knowledge Recall Extension

**Path:** `extensions/python/message_loop_prompts_after/edgequake_recall.py`

**Hook:** `message_loop_prompts_after` — enriches agent context before LLM call.

**Behavior:**
- Takes the current user message
- Runs `client.query.execute(query=user_message, mode="hybrid")`
- Injects relevant results into the agent's prompt as additional context
- Results appear as a `hint` log type in the process group UI

**Guard rails:**
- Only fires if EdgeQuake is configured and healthy
- 3-second timeout to avoid blocking the agent loop
- Skips if recall is disabled in settings
- Caches recent queries to avoid duplicate lookups within same conversation turn

### Settings Additions for Phase 3

| Key | Type | Default | Purpose |
|-----|------|---------|---------|
| `edgequake_auto_index` | bool | `false` | Enable conversation indexing |
| `edgequake_index_batch_size` | int | `5` | Turns to buffer before upload |
| `edgequake_auto_recall` | bool | `false` | Enable knowledge recall |
| `edgequake_recall_timeout` | int | `3` | Recall query timeout (seconds) |

### File Watcher (Future Consideration)

A directory watcher that auto-ingests new files. Not spec'd in detail — listed as a natural evolution if users want to feed external documents into the knowledge graph without manual upload.

---

## Dependencies

- `edgequake-sdk` Python package (`pip install edgequake-sdk`)
- EdgeQuake server running and accessible (user's responsibility)

---

## Key Design Principles

1. **Graceful degradation** — plugin never crashes the agent. Missing config, unreachable server, and SDK errors all produce helpful messages.
2. **Convention compliance** — follows A0 plugin conventions exactly (directory structure, Tool/ApiHandler subclasses, x-component patterns, Alpine store patterns).
3. **Incremental delivery** — Phase 1 is fully functional standalone. Phases 2 and 3 add capabilities without modifying Phase 1 code.
4. **Opt-in everything** — Phase 3 pipeline features are disabled by default and toggled via settings.
5. **No env var dependency** — all configuration through A0's settings UI.
