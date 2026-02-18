# EdgeQuake Plugin Phase 1 — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a fully functional EdgeQuake plugin for Agent Zero that gives the agent knowledge graph-powered RAG tools and provides users with a settings UI for connection configuration.

**Architecture:** Plugin lives in `plugins/edgequake/` following A0's convention-over-configuration model. A single tool with method routing exposes six EdgeQuake SDK operations. A plugin-owned modal handles connection settings, stored in a plugin-managed JSON file. A sidebar button provides the entry point.

**Tech Stack:** Python (Tool/ApiHandler subclasses), EdgeQuake Python SDK (`edgequake-sdk`), Alpine.js + `createStore()` for frontend, A0's stacked modal system.

**Design Doc:** `docs/plans/2026-02-18-edgequake-plugin-design.md`

---

## Prerequisite: SDK Dependency

Before starting, install the EdgeQuake SDK:

```bash
pip install edgequake-sdk
```

If unavailable (not yet published), the implementation uses a mock-friendly pattern so the tool gracefully reports the missing dependency rather than crashing.

---

### Task 1: Plugin Directory Scaffolding

**Files:**
- Create: `plugins/edgequake/helpers/__init__.py`
- Create: `plugins/edgequake/tools/__init__.py`
- Create: `plugins/edgequake/api/__init__.py`

**Step 1: Create directory structure**

```bash
mkdir -p plugins/edgequake/helpers
mkdir -p plugins/edgequake/tools
mkdir -p plugins/edgequake/api
mkdir -p plugins/edgequake/webui
mkdir -p plugins/edgequake/prompts
mkdir -p plugins/edgequake/extensions/webui/sidebar-quick-actions-main-start
touch plugins/edgequake/helpers/__init__.py
touch plugins/edgequake/tools/__init__.py
touch plugins/edgequake/api/__init__.py
```

**Step 2: Verify structure**

```bash
find plugins/edgequake -type f | sort
```

Expected:

```
plugins/edgequake/api/__init__.py
plugins/edgequake/helpers/__init__.py
plugins/edgequake/tools/__init__.py
```

**Step 3: Commit**

```bash
git add plugins/edgequake/
git commit -m "feat(edgequake): scaffold plugin directory structure"
```

---

### Task 2: Client Helper (`helpers/edgequake_client.py`)

**Files:**
- Create: `plugins/edgequake/helpers/edgequake_client.py`

This is the shared foundation. All other files depend on it.

**Step 1: Write the client helper**

```python
"""
EdgeQuake SDK client factory.

Reads plugin settings from a JSON file, constructs a cached EdgeQuake client,
and provides a connection test helper.
"""

import hashlib
import json
import os
from typing import Any

from python.helpers.files import get_abs_path
from python.helpers.print_style import PrintStyle

# Settings file path (plugin-owned, not in core settings)
SETTINGS_FILE = get_abs_path("plugins/edgequake/settings.json")

# Default settings
DEFAULTS: dict[str, Any] = {
    "base_url": "http://localhost:8080",
    "api_key": "",
    "workspace_id": "",
    "tenant_id": "",
    "timeout": 30,
}

# Cached client state
_cached_client = None
_cached_hash = ""


def _settings_hash(settings: dict) -> str:
    """Compute a hash of settings values for cache invalidation."""
    raw = json.dumps(settings, sort_keys=True)
    return hashlib.md5(raw.encode()).hexdigest()


def get_edgequake_settings() -> dict[str, Any]:
    """Read EdgeQuake settings from the plugin settings file."""
    settings = dict(DEFAULTS)
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f:
                stored = json.load(f)
            settings.update(stored)
        except Exception as e:
            PrintStyle.error(f"EdgeQuake: failed to read settings: {e}")
    return settings


def save_edgequake_settings(settings: dict[str, Any]) -> None:
    """Write EdgeQuake settings to the plugin settings file."""
    global _cached_client, _cached_hash
    os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f, indent=2)
    # Invalidate cache so next get_edgequake_client() rebuilds
    _cached_client = None
    _cached_hash = ""


def get_edgequake_client():
    """
    Get a cached EdgeQuake SDK client.

    Returns None if:
    - api_key is not configured
    - edgequake-sdk is not installed
    """
    global _cached_client, _cached_hash

    try:
        from edgequake import EdgeQuake
    except ImportError:
        return None

    settings = get_edgequake_settings()
    api_key = settings.get("api_key", "").strip()
    if not api_key:
        return None

    current_hash = _settings_hash(settings)
    if _cached_client is not None and current_hash == _cached_hash:
        return _cached_client

    kwargs: dict[str, Any] = {
        "base_url": settings.get("base_url", DEFAULTS["base_url"]),
        "api_key": api_key,
        "timeout": int(settings.get("timeout", DEFAULTS["timeout"])),
    }
    workspace_id = settings.get("workspace_id", "").strip()
    if workspace_id:
        kwargs["workspace_id"] = workspace_id
    tenant_id = settings.get("tenant_id", "").strip()
    if tenant_id:
        kwargs["tenant_id"] = tenant_id

    _cached_client = EdgeQuake(**kwargs)
    _cached_hash = current_hash
    return _cached_client


def test_connection(settings: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Test connection to EdgeQuake server.

    If settings are provided, creates a temporary client from those values
    (for testing before saving). Otherwise uses the cached client.

    Returns a dict with status info or an error message.
    """
    try:
        from edgequake import EdgeQuake
    except ImportError:
        return {"error": "edgequake-sdk is not installed. Run: pip install edgequake-sdk"}

    if settings is not None:
        api_key = settings.get("api_key", "").strip()
        if not api_key:
            return {"error": "API key is required"}
        kwargs: dict[str, Any] = {
            "base_url": settings.get("base_url", DEFAULTS["base_url"]),
            "api_key": api_key,
            "timeout": int(settings.get("timeout", DEFAULTS["timeout"])),
        }
        workspace_id = settings.get("workspace_id", "").strip()
        if workspace_id:
            kwargs["workspace_id"] = workspace_id
        tenant_id = settings.get("tenant_id", "").strip()
        if tenant_id:
            kwargs["tenant_id"] = tenant_id
        client = EdgeQuake(**kwargs)
    else:
        client = get_edgequake_client()
        if client is None:
            return {"error": "EdgeQuake is not configured"}

    try:
        health = client.health()
        return {
            "status": getattr(health, "status", "unknown"),
            "version": getattr(health, "version", "unknown"),
            "storage_mode": getattr(health, "storage_mode", "unknown"),
            "llm_provider_name": getattr(health, "llm_provider_name", "unknown"),
        }
    except Exception as e:
        return {"error": f"Connection failed: {str(e)}"}
```

**Step 2: Verify the file loads without import errors**

```bash
cd /Users/lazy/agent-zero-dev
python -c "import plugins.edgequake.helpers.edgequake_client as ec; print('OK:', list(ec.DEFAULTS.keys()))"
```

Expected: `OK: ['base_url', 'api_key', 'workspace_id', 'tenant_id', 'timeout']`

Note: If this fails due to Python path issues with the A0 project structure, adjust the import. The plugin discovery system from PR #998 handles path resolution at runtime, but for standalone testing you may need: `PYTHONPATH=. python -c "..."`.

**Step 3: Commit**

```bash
git add plugins/edgequake/helpers/edgequake_client.py
git commit -m "feat(edgequake): add SDK client helper with caching and connection test"
```

---

### Task 3: Tool Prompt (`prompts/agent.system.tool.edgequake.md`)

**Files:**
- Create: `plugins/edgequake/prompts/agent.system.tool.edgequake.md`

**Step 1: Write the prompt**

```markdown
## Tool: edgequake

Knowledge graph-powered RAG system. Use for deep research, document ingestion, and entity exploration.

### When to use
- User asks a knowledge-intensive question and you need richer context than conversation history provides
- User wants to store documents or knowledge for future retrieval
- User asks about relationships between concepts, people, or entities
- User wants to explore what is in the knowledge base

### Methods

**query** — Search the knowledge graph
- query: (required) the question to ask
- mode: (optional) naive|local|global|hybrid|mix|bypass (default: hybrid)

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

**Step 2: Commit**

```bash
git add plugins/edgequake/prompts/agent.system.tool.edgequake.md
git commit -m "feat(edgequake): add agent tool prompt"
```

---

### Task 4: Agent Tool (`tools/edgequake.py`)

**Files:**
- Create: `plugins/edgequake/tools/edgequake.py`

**Context:** This follows the pattern from `python/tools/skills_tool.py` — a `Tool` subclass with `execute()` that routes on `self.method`. Each method is a thin wrapper around an EdgeQuake SDK call.

**Step 1: Write the tool**

```python
"""
EdgeQuake tool for Agent Zero.

Single tool with method-based routing for knowledge graph operations:
query, upload, list_documents, search_entities, graph_stats, health.
"""

from python.helpers.tool import Tool, Response


class EdgequakeTool(Tool):

    async def execute(self, **kwargs) -> Response:
        method = (
            (kwargs.get("method") or self.args.get("method") or self.method or "")
            .strip()
            .lower()
        )

        try:
            if method == "query":
                return await self._query(**kwargs)
            elif method == "upload":
                return await self._upload(**kwargs)
            elif method == "list_documents":
                return await self._list_documents(**kwargs)
            elif method == "search_entities":
                return await self._search_entities(**kwargs)
            elif method == "graph_stats":
                return await self._graph_stats(**kwargs)
            elif method == "health":
                return await self._health(**kwargs)
            else:
                return Response(
                    message="Error: missing or invalid 'method'. Supported: query, upload, list_documents, search_entities, graph_stats, health.",
                    break_loop=False,
                )
        except Exception as e:
            return Response(
                message=f"EdgeQuake error: {str(e)}",
                break_loop=False,
            )

    def _get_client(self):
        """Get EdgeQuake client, returning (client, error_response) tuple."""
        from plugins.edgequake.helpers.edgequake_client import get_edgequake_client

        client = get_edgequake_client()
        if client is None:
            return None, Response(
                message="EdgeQuake is not configured. The user needs to set it up via the EdgeQuake button in the sidebar (hub icon) with a server URL and API key.",
                break_loop=False,
            )
        return client, None

    async def _query(self, **kwargs) -> Response:
        client, err = self._get_client()
        if err:
            return err

        query = str(kwargs.get("query") or self.args.get("query") or "").strip()
        if not query:
            return Response(message="Error: 'query' is required.", break_loop=False)

        mode = str(kwargs.get("mode") or self.args.get("mode") or "hybrid").strip().lower()
        valid_modes = ("naive", "local", "global", "hybrid", "mix", "bypass")
        if mode not in valid_modes:
            mode = "hybrid"

        self.set_progress(f"Querying EdgeQuake ({mode} mode)...")

        try:
            result = client.query.execute(query=query, mode=mode)
            answer = getattr(result, "answer", str(result))
            return Response(message=answer, break_loop=False)
        except Exception as e:
            return self._handle_sdk_error(e, "query")

    async def _upload(self, **kwargs) -> Response:
        client, err = self._get_client()
        if err:
            return err

        content = str(kwargs.get("content") or self.args.get("content") or "").strip()
        if not content:
            return Response(message="Error: 'content' is required.", break_loop=False)

        title = str(kwargs.get("title") or self.args.get("title") or "").strip() or None

        self.set_progress("Uploading document to EdgeQuake...")

        try:
            doc = client.documents.upload(content=content, title=title)
            doc_id = getattr(doc, "document_id", "unknown")
            return Response(
                message=f"Document uploaded successfully.\nDocument ID: {doc_id}\nTitle: {title or '(untitled)'}\nThe document is now being processed for entity extraction.",
                break_loop=False,
            )
        except Exception as e:
            return self._handle_sdk_error(e, "upload")

    async def _list_documents(self, **kwargs) -> Response:
        client, err = self._get_client()
        if err:
            return err

        page = int(kwargs.get("page") or self.args.get("page") or 1)
        limit = int(kwargs.get("limit") or self.args.get("limit") or 10)

        self.set_progress("Listing EdgeQuake documents...")

        try:
            docs = client.documents.list(page=page, limit=limit)
            items = getattr(docs, "items", docs) if not isinstance(docs, list) else docs
            if not items:
                return Response(message="No documents found.", break_loop=False)

            lines = [f"Documents (page {page}):"]
            for doc in items:
                doc_id = getattr(doc, "document_id", getattr(doc, "id", "?"))
                title = getattr(doc, "title", "Untitled")
                status = getattr(doc, "status", "unknown")
                lines.append(f"- [{status}] {title} (ID: {doc_id})")
            return Response(message="\n".join(lines), break_loop=False)
        except Exception as e:
            return self._handle_sdk_error(e, "list_documents")

    async def _search_entities(self, **kwargs) -> Response:
        client, err = self._get_client()
        if err:
            return err

        keyword = str(kwargs.get("keyword") or self.args.get("keyword") or "").strip()
        if not keyword:
            return Response(message="Error: 'keyword' is required.", break_loop=False)

        self.set_progress(f"Searching EdgeQuake entities for '{keyword}'...")

        try:
            results = client.graph.search(keyword=keyword)
            items = getattr(results, "entities", results) if not isinstance(results, list) else results
            if not items:
                return Response(message=f"No entities found matching '{keyword}'.", break_loop=False)

            lines = [f"Entities matching '{keyword}':"]
            for entity in items:
                name = getattr(entity, "name", str(entity))
                etype = getattr(entity, "entity_type", "")
                desc = getattr(entity, "description", "")
                type_str = f" ({etype})" if etype else ""
                desc_str = f": {desc[:200]}" if desc else ""
                lines.append(f"- {name}{type_str}{desc_str}")
            return Response(message="\n".join(lines), break_loop=False)
        except Exception as e:
            return self._handle_sdk_error(e, "search_entities")

    async def _graph_stats(self, **kwargs) -> Response:
        client, err = self._get_client()
        if err:
            return err

        self.set_progress("Fetching EdgeQuake graph statistics...")

        try:
            graph = client.graph.get()
            entity_count = getattr(graph, "entity_count", getattr(graph, "num_entities", "?"))
            rel_count = getattr(graph, "relationship_count", getattr(graph, "num_relationships", "?"))
            labels = getattr(graph, "labels", [])

            lines = [
                "Knowledge Graph Statistics:",
                f"- Entities: {entity_count}",
                f"- Relationships: {rel_count}",
            ]
            if labels:
                label_str = ", ".join(str(l) for l in labels[:20])
                lines.append(f"- Labels: {label_str}")
            return Response(message="\n".join(lines), break_loop=False)
        except Exception as e:
            return self._handle_sdk_error(e, "graph_stats")

    async def _health(self, **kwargs) -> Response:
        from plugins.edgequake.helpers.edgequake_client import test_connection

        self.set_progress("Checking EdgeQuake health...")
        result = test_connection()

        if "error" in result:
            return Response(message=f"EdgeQuake health check failed: {result['error']}", break_loop=False)

        lines = [
            "EdgeQuake is healthy:",
            f"- Status: {result.get('status', '?')}",
            f"- Version: {result.get('version', '?')}",
            f"- Storage: {result.get('storage_mode', '?')}",
            f"- LLM Provider: {result.get('llm_provider_name', '?')}",
        ]
        return Response(message="\n".join(lines), break_loop=False)

    def _handle_sdk_error(self, error: Exception, operation: str) -> Response:
        """Convert SDK exceptions into helpful Response messages."""
        err_str = str(error).lower()
        if "connection" in err_str or "refused" in err_str:
            msg = f"EdgeQuake server is unreachable. Check that the server is running and the URL is correct."
        elif "401" in err_str or "unauthorized" in err_str or "auth" in err_str:
            msg = f"EdgeQuake authentication failed. The API key may be invalid."
        elif "timeout" in err_str:
            msg = f"EdgeQuake request timed out. The server may be overloaded."
        else:
            msg = f"EdgeQuake {operation} error: {str(error)}"
        return Response(message=msg, break_loop=False)
```

**Step 2: Verify the file parses correctly**

```bash
python -c "import ast; ast.parse(open('plugins/edgequake/tools/edgequake.py').read()); print('Syntax OK')"
```

Expected: `Syntax OK`

**Step 3: Commit**

```bash
git add plugins/edgequake/tools/edgequake.py
git commit -m "feat(edgequake): add agent tool with 6 methods (query, upload, list, search, stats, health)"
```

---

### Task 5: Settings API Handler (`api/edgequake_settings.py`)

**Files:**
- Create: `plugins/edgequake/api/edgequake_settings.py`

**Context:** This follows the `ApiHandler` pattern from `python/helpers/api.py`. The handler manages plugin-owned settings (stored in `plugins/edgequake/settings.json`, separate from A0's core settings). It supports three actions: `load`, `save`, and `test`.

**Step 1: Write the API handler**

```python
"""
API handler for EdgeQuake plugin settings.

Actions:
- load: Read current settings (API key masked)
- save: Validate and persist settings
- test: Test connection with provided (unsaved) settings
"""

from flask import Request
from python.helpers.api import ApiHandler, Input, Output


class EdgequakeSettings(ApiHandler):

    async def process(self, input: Input, request: Request) -> Output:
        action = input.get("action", "load")

        if action == "load":
            return self._load()
        elif action == "save":
            return self._save(input.get("settings", {}))
        elif action == "test":
            return self._test(input.get("settings", {}))
        else:
            return {"error": f"Unknown action: {action}"}

    def _load(self) -> dict:
        from plugins.edgequake.helpers.edgequake_client import get_edgequake_settings

        settings = get_edgequake_settings()
        # Mask API key for display
        api_key = settings.get("api_key", "")
        if api_key and len(api_key) > 4:
            settings["api_key"] = "****" + api_key[-4:]
        elif api_key:
            settings["api_key"] = "****"
        return {"settings": settings}

    def _save(self, settings: dict) -> dict:
        from plugins.edgequake.helpers.edgequake_client import (
            get_edgequake_settings,
            save_edgequake_settings,
        )

        if not settings:
            return {"error": "No settings provided"}

        # Merge with existing — if API key is masked, keep the original
        current = get_edgequake_settings()
        api_key = settings.get("api_key", "").strip()
        if api_key.startswith("****") or not api_key:
            settings["api_key"] = current.get("api_key", "")

        # Validate base_url
        base_url = settings.get("base_url", "").strip()
        if not base_url:
            settings["base_url"] = "http://localhost:8080"

        # Ensure timeout is an int
        try:
            settings["timeout"] = int(settings.get("timeout", 30))
        except (ValueError, TypeError):
            settings["timeout"] = 30

        save_edgequake_settings(settings)
        return {"success": True}

    def _test(self, settings: dict) -> dict:
        from plugins.edgequake.helpers.edgequake_client import (
            get_edgequake_settings,
            test_connection,
        )

        if not settings:
            return {"error": "No settings provided"}

        # If API key is masked, substitute from saved settings
        api_key = settings.get("api_key", "").strip()
        if api_key.startswith("****") or not api_key:
            current = get_edgequake_settings()
            settings["api_key"] = current.get("api_key", "")

        if not settings.get("api_key", "").strip():
            return {"error": "API key is required to test connection"}

        return test_connection(settings=settings)
```

**Step 2: Verify the file parses correctly**

```bash
python -c "import ast; ast.parse(open('plugins/edgequake/api/edgequake_settings.py').read()); print('Syntax OK')"
```

Expected: `Syntax OK`

**Step 3: Commit**

```bash
git add plugins/edgequake/api/edgequake_settings.py
git commit -m "feat(edgequake): add settings API handler (load/save/test)"
```

---

### Task 6: Settings Store (`webui/edgequake-settings-store.js`)

**Files:**
- Create: `plugins/edgequake/webui/edgequake-settings-store.js`

**Context:** This follows the Alpine store pattern from A0's component system. The store manages settings state and communicates with the API handler. API calls use `callJsonApi()` which adds CSRF protection. The endpoint path for plugin APIs is `/api/plugins/edgequake/edgequake_settings` per A0-PLUGINS.md routes.

**Step 1: Write the store**

```javascript
import { createStore } from "/js/AlpineStore.js";
import * as API from "/js/api.js";

const model = {
  // Settings state
  base_url: "http://localhost:8080",
  api_key: "",
  workspace_id: "",
  tenant_id: "",
  timeout: 30,

  // UI state
  loading: false,
  connection_status: null, // null | "testing" | "connected" | "error"
  connection_info: "",
  show_api_key: false,

  async load() {
    this.loading = true;
    try {
      const response = await API.callJsonApi(
        "/api/plugins/edgequake/edgequake_settings",
        { action: "load" }
      );
      if (response && response.settings) {
        this.base_url = response.settings.base_url || "http://localhost:8080";
        this.api_key = response.settings.api_key || "";
        this.workspace_id = response.settings.workspace_id || "";
        this.tenant_id = response.settings.tenant_id || "";
        this.timeout = response.settings.timeout || 30;
      }
    } catch (e) {
      console.error("EdgeQuake: failed to load settings:", e);
    } finally {
      this.loading = false;
    }
  },

  async save() {
    this.loading = true;
    try {
      const response = await API.callJsonApi(
        "/api/plugins/edgequake/edgequake_settings",
        {
          action: "save",
          settings: {
            base_url: this.base_url,
            api_key: this.api_key,
            workspace_id: this.workspace_id,
            tenant_id: this.tenant_id,
            timeout: this.timeout,
          },
        }
      );
      if (response && response.success) {
        window.closeModal("../plugins/edgequake/webui/edgequake-settings.html");
      } else if (response && response.error) {
        alert("Save failed: " + response.error);
      }
    } catch (e) {
      console.error("EdgeQuake: failed to save settings:", e);
      alert("Failed to save settings: " + e.message);
    } finally {
      this.loading = false;
    }
  },

  async testConnection() {
    this.connection_status = "testing";
    this.connection_info = "";
    try {
      const response = await API.callJsonApi(
        "/api/plugins/edgequake/edgequake_settings",
        {
          action: "test",
          settings: {
            base_url: this.base_url,
            api_key: this.api_key,
            workspace_id: this.workspace_id,
            tenant_id: this.tenant_id,
            timeout: this.timeout,
          },
        }
      );
      if (response && response.error) {
        this.connection_status = "error";
        this.connection_info = response.error;
      } else if (response && response.status) {
        this.connection_status = "connected";
        this.connection_info = `${response.status} | v${response.version} | ${response.storage_mode} | ${response.llm_provider_name}`;
      } else {
        this.connection_status = "error";
        this.connection_info = "Unexpected response";
      }
    } catch (e) {
      this.connection_status = "error";
      this.connection_info = e.message || "Connection failed";
    }
  },

  destroy() {
    this.connection_status = null;
    this.connection_info = "";
    this.show_api_key = false;
  },
};

export const store = createStore("edgequakeSettings", model);
```

**Step 2: Commit**

```bash
git add plugins/edgequake/webui/edgequake-settings-store.js
git commit -m "feat(edgequake): add settings Alpine store"
```

---

### Task 7: Settings Modal UI (`webui/edgequake-settings.html`)

**Files:**
- Create: `plugins/edgequake/webui/edgequake-settings.html`

**Context:** This is a plugin-owned modal opened via `openModal('../plugins/edgequake/webui/edgequake-settings.html')`. It uses A0's `.field` / `.field-control` CSS classes from `settings.css`, the `.btn` / `.btn-ok` / `.btn-cancel` classes from `modals.css`, and the `data-modal-footer` convention for pinned footers.

**Step 1: Write the settings modal**

```html
<html>
<head>
  <title>EdgeQuake Settings</title>
  <script type="module">
    import { store } from "/plugins/edgequake/webui/edgequake-settings-store.js";
  </script>
</head>

<body>
<div x-data>
  <template x-if="$store.edgequakeSettings">
    <div
      x-create="$store.edgequakeSettings.load()"
      x-destroy="$store.edgequakeSettings.destroy()"
    >
      <div class="section">
        <div class="section-title">Connection</div>
        <div class="section-description">
          Connect to an EdgeQuake server for knowledge graph-powered RAG.
        </div>

        <!-- Server URL -->
        <div class="field">
          <div class="field-label">
            <div class="field-title">Server URL</div>
            <div class="field-description">Base URL of the EdgeQuake server</div>
          </div>
          <div class="field-control">
            <input
              type="text"
              x-model="$store.edgequakeSettings.base_url"
              placeholder="http://localhost:8080"
            />
          </div>
        </div>

        <!-- API Key -->
        <div class="field">
          <div class="field-label">
            <div class="field-title">API Key</div>
            <div class="field-description">Authentication key for the EdgeQuake API</div>
          </div>
          <div class="field-control eq-api-key-field">
            <input
              :type="$store.edgequakeSettings.show_api_key ? 'text' : 'password'"
              x-model="$store.edgequakeSettings.api_key"
              placeholder="Enter API key"
              autocomplete="off"
            />
            <button
              class="eq-toggle-btn"
              @click="$store.edgequakeSettings.show_api_key = !$store.edgequakeSettings.show_api_key"
              title="Toggle visibility"
            >
              <span class="material-symbols-outlined" x-text="$store.edgequakeSettings.show_api_key ? 'visibility_off' : 'visibility'"></span>
            </button>
          </div>
        </div>

        <!-- Workspace ID -->
        <div class="field">
          <div class="field-label">
            <div class="field-title">Workspace ID</div>
            <div class="field-description">Optional workspace for multi-tenant setups</div>
          </div>
          <div class="field-control">
            <input
              type="text"
              x-model="$store.edgequakeSettings.workspace_id"
              placeholder="(optional)"
            />
          </div>
        </div>

        <!-- Tenant ID -->
        <div class="field">
          <div class="field-label">
            <div class="field-title">Tenant ID</div>
            <div class="field-description">Optional tenant for multi-tenant setups</div>
          </div>
          <div class="field-control">
            <input
              type="text"
              x-model="$store.edgequakeSettings.tenant_id"
              placeholder="(optional)"
            />
          </div>
        </div>

        <!-- Timeout -->
        <div class="field">
          <div class="field-label">
            <div class="field-title">Timeout</div>
            <div class="field-description">Request timeout in seconds</div>
          </div>
          <div class="field-control">
            <input
              type="number"
              x-model.number="$store.edgequakeSettings.timeout"
              min="5"
              max="300"
            />
          </div>
        </div>
      </div>

      <!-- Test Connection -->
      <div class="section">
        <div class="section-title">Connection Test</div>
        <div class="eq-test-row">
          <button
            class="btn btn-ok"
            @click="$store.edgequakeSettings.testConnection()"
            :disabled="$store.edgequakeSettings.connection_status === 'testing'"
          >
            <span
              x-show="$store.edgequakeSettings.connection_status === 'testing'"
              class="material-symbols-outlined spinning"
            >progress_activity</span>
            <span x-show="$store.edgequakeSettings.connection_status !== 'testing'">Test Connection</span>
            <span x-show="$store.edgequakeSettings.connection_status === 'testing'">Testing...</span>
          </button>

          <!-- Status indicator -->
          <div class="eq-status" x-show="$store.edgequakeSettings.connection_status === 'connected'">
            <span class="eq-dot eq-dot-green"></span>
            <span x-text="$store.edgequakeSettings.connection_info"></span>
          </div>
          <div class="eq-status" x-show="$store.edgequakeSettings.connection_status === 'error'">
            <span class="eq-dot eq-dot-red"></span>
            <span x-text="$store.edgequakeSettings.connection_info"></span>
          </div>
        </div>
      </div>

      <!-- Footer -->
      <div class="modal-footer" data-modal-footer>
        <button
          class="btn btn-ok"
          @click="$store.edgequakeSettings.save()"
          :disabled="$store.edgequakeSettings.loading"
        >Save</button>
        <button
          class="btn btn-cancel"
          @click="window.closeModal('../plugins/edgequake/webui/edgequake-settings.html')"
        >Cancel</button>
      </div>
    </div>
  </template>
</div>
</body>
</html>

<style>
.eq-api-key-field {
  position: relative;
}

.eq-api-key-field input {
  padding-right: 2.5rem;
}

.eq-toggle-btn {
  position: absolute;
  right: 0.5rem;
  top: 50%;
  transform: translateY(-50%);
  background: none;
  border: none;
  cursor: pointer;
  color: var(--color-text);
  opacity: 0.6;
  padding: 0.25rem;
}

.eq-toggle-btn:hover {
  opacity: 1;
}

.eq-test-row {
  display: flex;
  align-items: center;
  gap: 1rem;
  flex-wrap: wrap;
}

.eq-status {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.875rem;
  color: var(--color-text);
}

.eq-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  display: inline-block;
  flex-shrink: 0;
}

.eq-dot-green {
  background-color: #27ae60;
}

.eq-dot-red {
  background-color: #e74c3c;
}

.spinning {
  animation: spin 1s linear infinite;
  font-size: 1rem;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>
```

**Step 2: Commit**

```bash
git add plugins/edgequake/webui/edgequake-settings.html
git commit -m "feat(edgequake): add settings modal UI"
```

---

### Task 8: Sidebar Button Extension

**Files:**
- Create: `plugins/edgequake/extensions/webui/sidebar-quick-actions-main-start/edgequake-button.html`

**Context:** This follows the A0-PLUGINS.md baseline extension pattern. It injects a button into the sidebar that opens the EdgeQuake settings modal. The button uses `x-move-after` for placement and `openModal()` with the plugin-relative path.

**Step 1: Write the sidebar button**

```html
<div x-data>
  <button
    x-move-after=".config-button#dashboard"
    class="config-button"
    id="edgequake"
    @click="openModal('../plugins/edgequake/webui/edgequake-settings.html')"
    title="EdgeQuake Knowledge Graph">
    <span class="material-symbols-outlined">hub</span>
  </button>
</div>
```

**Step 2: Commit**

```bash
git add plugins/edgequake/extensions/webui/sidebar-quick-actions-main-start/edgequake-button.html
git commit -m "feat(edgequake): add sidebar button extension"
```

---

### Task 9: Final Verification & Cleanup

**Step 1: Verify full directory structure**

```bash
find plugins/edgequake -type f | sort
```

Expected output:

```
plugins/edgequake/api/__init__.py
plugins/edgequake/api/edgequake_settings.py
plugins/edgequake/extensions/webui/sidebar-quick-actions-main-start/edgequake-button.html
plugins/edgequake/helpers/__init__.py
plugins/edgequake/helpers/edgequake_client.py
plugins/edgequake/prompts/agent.system.tool.edgequake.md
plugins/edgequake/tools/__init__.py
plugins/edgequake/tools/edgequake.py
plugins/edgequake/webui/edgequake-settings-store.js
plugins/edgequake/webui/edgequake-settings.html
```

**Step 2: Verify all Python files parse**

```bash
python -c "
import ast, glob
for f in sorted(glob.glob('plugins/edgequake/**/*.py', recursive=True)):
    if f.endswith('__init__.py'): continue
    ast.parse(open(f).read())
    print(f'OK: {f}')
print('All files parse successfully')
"
```

Expected: all files report `OK` and final line says `All files parse successfully`.

**Step 3: Verify JavaScript parses**

```bash
node -e "
const fs = require('fs');
const code = fs.readFileSync('plugins/edgequake/webui/edgequake-settings-store.js', 'utf8');
try { new Function(code); } catch(e) { /* module syntax expected */ }
console.log('JS file reads OK');
"
```

**Step 4: Final commit with all files**

If any files were missed in prior commits:

```bash
git add plugins/edgequake/
git status
# Only commit if there are unstaged changes
```

---

## Summary

| Task | File | Purpose |
|------|------|---------|
| 1 | Directory scaffold | Empty `__init__.py` files, directory structure |
| 2 | `helpers/edgequake_client.py` | SDK client factory, settings I/O, connection test |
| 3 | `prompts/agent.system.tool.edgequake.md` | Agent-facing tool description |
| 4 | `tools/edgequake.py` | Tool with 6 methods (query, upload, list, search, stats, health) |
| 5 | `api/edgequake_settings.py` | Settings API handler (load/save/test) |
| 6 | `webui/edgequake-settings-store.js` | Alpine store for settings UI state |
| 7 | `webui/edgequake-settings.html` | Settings modal with connection test |
| 8 | Extension button HTML | Sidebar button to open settings |
| 9 | Verification | Parse checks, structure verification |

**Total files:** 10 (3 Python, 1 Markdown, 2 JavaScript/HTML, 1 HTML extension, 3 `__init__.py`)

**Dependencies:** `edgequake-sdk` (pip install). Plugin gracefully handles missing SDK.

**No core code modifications required.** The plugin is fully self-contained.
