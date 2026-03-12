# QMD Plugin Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a QMD knowledge search plugin for Agent Zero that integrates the `@tobilu/qmd` SDK via a persistent Node.js subprocess, giving agents hybrid BM25 + vector + LLM-reranked local search over markdown collections.

**Architecture:** A Node.js bridge process (`bridge/bridge.js`) wraps the QMD SDK and communicates with Python via line-delimited JSON-RPC 2.0 over stdin/stdout. A Python `QMDClient` helper manages the subprocess lifecycle per agent session (lazy start, kept alive). Four Agent Zero `Tool` subclasses expose search, retrieval, status, and gated management operations.

**Tech Stack:** Python 3.11+ (asyncio), Node.js ≥22, `@tobilu/qmd` npm package, Agent Zero plugin conventions (Tool, Extension, ApiHandler, Alpine.js config UI).

---

## File Map

| File | Role |
|------|------|
| `usr/plugins/qmd/plugin.yaml` | Plugin manifest |
| `usr/plugins/qmd/default_config.yaml` | Default settings |
| `usr/plugins/qmd/bridge/package.json` | Node.js dependencies |
| `usr/plugins/qmd/bridge/bridge.js` | QMD SDK wrapper, JSON-RPC over stdin/stdout |
| `usr/plugins/qmd/helpers/qmd_client.py` | Async Python subprocess manager |
| `usr/plugins/qmd/tools/qmd_status.py` | Tool: index status (no params) |
| `usr/plugins/qmd/tools/qmd_search.py` | Tool: query/search/vsearch |
| `usr/plugins/qmd/tools/qmd_get.py` | Tool: get/multi-get by path or docid |
| `usr/plugins/qmd/tools/qmd_manage.py` | Tool: collection/context/embed (gated) |
| `usr/plugins/qmd/prompts/qmd_tools.md` | System prompt template for agent |
| `usr/plugins/qmd/extensions/python/system_prompt/_20_qmd_prompt.py` | Injects QMD capabilities into system prompt |
| `usr/plugins/qmd/extensions/python/agent_init/_30_qmd_auto_index.py` | Auto-indexes project dir on first init |
| `usr/plugins/qmd/api/status.py` | GET /api/plugins/qmd/status for config UI |
| `usr/plugins/qmd/webui/config.html` | Plugin settings panel (Alpine.js) |
| `usr/plugins/qmd/initialize.py` | One-time setup: verify node, npm install, selftest |
| `tests/test_qmd_client.py` | Unit tests for QMDClient subprocess management |
| `tests/test_qmd_tools.py` | Unit tests for tool execute() methods |

---

## Chunk 1: Scaffold + Bridge

### Task 1: Plugin Scaffold

**Files:**
- Create: `usr/plugins/qmd/plugin.yaml`
- Create: `usr/plugins/qmd/default_config.yaml`
- Create directories: `usr/plugins/qmd/{bridge,helpers,tools,extensions/python/system_prompt,extensions/python/agent_init,prompts,api,webui}/`

- [ ] **Step 1: Create the directory tree**

```bash
mkdir -p usr/plugins/qmd/{bridge,helpers,tools,api,webui,prompts}
mkdir -p usr/plugins/qmd/extensions/python/system_prompt
mkdir -p usr/plugins/qmd/extensions/python/agent_init
```

Run from: `/Users/lazy/Documents/agent-zero`

- [ ] **Step 2: Write plugin.yaml**

```yaml
title: QMD Knowledge Search
description: Local hybrid search for markdown notes, docs, and knowledge bases. BM25 + vector + LLM reranking, fully on-device.
version: 1.0.0
settings_sections:
  - agent
per_project_config: false
always_enabled: false
```

Save to: `usr/plugins/qmd/plugin.yaml`

- [ ] **Step 3: Write default_config.yaml**

```yaml
management_enabled: false
auto_index_project: true
db_path: ""
bridge_startup_timeout: 30
request_timeout_search: 60
request_timeout_default: 10
```

Save to: `usr/plugins/qmd/default_config.yaml`

- [ ] **Step 4: Verify plugin appears in A0 plugin list**

Start Agent Zero (or use an existing running instance). Navigate to Settings → Plugins. Confirm "QMD Knowledge Search" appears in the list with a toggle.

- [ ] **Step 5: Commit**

```bash
git add usr/plugins/qmd/plugin.yaml usr/plugins/qmd/default_config.yaml
git commit -m "feat(qmd): scaffold plugin manifest and default config"
```

---

### Task 2: Node.js Bridge Package

**Files:**
- Create: `usr/plugins/qmd/bridge/package.json`

- [ ] **Step 1: Write package.json**

```json
{
  "name": "agent-zero-qmd-bridge",
  "version": "1.0.0",
  "type": "module",
  "dependencies": {
    "@tobilu/qmd": "latest"
  },
  "engines": {
    "node": ">=22"
  }
}
```

Save to: `usr/plugins/qmd/bridge/package.json`

- [ ] **Step 2: Verify node version**

```bash
node --version
```

Expected: `v22.x.x` or higher. If not, install Node.js 22+ from nodejs.org or `brew install node`.

- [ ] **Step 3: Install dependencies**

```bash
cd usr/plugins/qmd/bridge && npm install
```

Expected: `node_modules/` created, `@tobilu/qmd` installed.

- [ ] **Step 4: Commit package.json (not node_modules)**

```bash
cd /Users/lazy/Documents/agent-zero
echo "usr/plugins/qmd/bridge/node_modules/" >> .gitignore
git add usr/plugins/qmd/bridge/package.json usr/plugins/qmd/bridge/package-lock.json .gitignore
git commit -m "feat(qmd): add bridge Node.js package manifest"
```

---

### Task 3: Bridge (bridge.js)

**Files:**
- Create: `usr/plugins/qmd/bridge/bridge.js`

The bridge reads `QMD_DB_PATH` from env, creates a QMD store, signals ready, then processes JSON-RPC requests line by line.

- [ ] **Step 1: Write bridge.js**

```javascript
import { createStore } from '@tobilu/qmd'
import readline from 'readline'

const SELFTEST = process.argv.includes('--selftest')
const dbPath = process.env.QMD_DB_PATH || undefined

let store
try {
  store = await createStore({ dbPath })
} catch (err) {
  process.stderr.write(`QMD bridge failed to open store: ${err.message}\n`)
  process.exit(1)
}

// Signal ready
process.stdout.write(JSON.stringify({ ready: true }) + '\n')

if (SELFTEST) {
  // Ping ourselves and exit
  const result = await dispatch('ping', {})
  process.stderr.write(`selftest: ping=${JSON.stringify(result)}\n`)
  await store.close()
  process.exit(0)
}

const rl = readline.createInterface({ input: process.stdin })

rl.on('line', async (line) => {
  let req
  try {
    req = JSON.parse(line)
  } catch {
    // Ignore unparseable lines
    return
  }
  const { jsonrpc, id, method, params } = req
  try {
    const result = await dispatch(method, params ?? {})
    process.stdout.write(JSON.stringify({ jsonrpc, id, result }) + '\n')
  } catch (err) {
    process.stdout.write(
      JSON.stringify({ jsonrpc, id, error: { code: -32000, message: err.message } }) + '\n'
    )
  }
})

rl.on('close', async () => {
  await store.close()
  process.exit(0)
})

process.on('SIGTERM', async () => {
  await store.close()
  process.exit(0)
})

async function dispatch(method, params) {
  switch (method) {
    case 'ping':
      return { pong: true }

    case 'status':
      return await store.getStatus()

    case 'collection_list':
      return { collections: await store.listCollections() }

    case 'context_list':
      return { contexts: await store.listContexts() }

    case 'query': {
      const { q, queries, collections, limit, minScore, intent, explain, rerank } = params
      if (queries) {
        return await store.search({ queries, collections, limit, minScore, intent, explain })
      }
      return await store.search({ query: q, collections, limit, minScore, intent, explain, rerank })
    }

    case 'search': {
      const { q, collections, limit, minScore } = params
      return await store.searchLex(q, { collections, limit, minScore })
    }

    case 'vsearch': {
      const { q, collections, limit, minScore } = params
      return await store.searchVector(q, { collections, limit, minScore })
    }

    case 'get': {
      const { path, full, lineNumbers, fromLine, maxLines } = params
      return await store.get(path, { full, lineNumbers, fromLine, maxLines })
    }

    case 'multi_get': {
      const { pattern, maxBytes } = params
      return await store.multiGet(pattern, { maxBytes })
    }

    case 'collection_add': {
      const { path, name, mask } = params
      await store.addCollection(name, { path, pattern: mask })
      return { ok: true }
    }

    case 'collection_remove': {
      const { name } = params
      await store.removeCollection(name)
      return { ok: true }
    }

    case 'context_add': {
      const { collection, path, text } = params
      await store.addContext(collection, path, text)
      return { ok: true }
    }

    case 'context_remove': {
      const { collection, path } = params
      await store.removeContext(collection, path)
      return { ok: true }
    }

    case 'update': {
      const { collections, pull } = params
      const result = await store.update({ collections, pull })
      return result
    }

    case 'embed': {
      const { force } = params
      const result = await store.embed({ force: force ?? false })
      return result
    }

    default:
      throw new Error(`Unknown method: ${method}`)
  }
}
```

Save to: `usr/plugins/qmd/bridge/bridge.js`

- [ ] **Step 2: Test the bridge standalone**

```bash
cd /Users/lazy/Documents/agent-zero/usr/plugins/qmd/bridge
node bridge.js --selftest
```

Expected output (stdout): `{"ready":true}`
Expected stderr: `selftest: ping={"pong":true}`

If QMD hasn't been set up yet, the bridge may fail to open a store — that's OK for now if `@tobilu/qmd` is installed. If not installed, run `npm install` first.

- [ ] **Step 3: Test basic JSON-RPC manually**

```bash
cd /Users/lazy/Documents/agent-zero/usr/plugins/qmd/bridge
echo '{"jsonrpc":"2.0","id":1,"method":"ping","params":{}}' | node bridge.js
```

Expected output lines:
```
{"ready":true}
{"jsonrpc":"2.0","id":1,"result":{"pong":true}}
```

Then Ctrl-C to exit.

- [ ] **Step 4: Commit**

```bash
cd /Users/lazy/Documents/agent-zero
git add usr/plugins/qmd/bridge/bridge.js
git commit -m "feat(qmd): add Node.js JSON-RPC bridge wrapping QMD SDK"
```

---

## Chunk 2: Python Client

### Task 4: QMDClient (`helpers/qmd_client.py`)

**Files:**
- Create: `usr/plugins/qmd/helpers/qmd_client.py`
- Create: `tests/test_qmd_client.py`

The client manages the subprocess, handles the ready handshake, serializes requests with an asyncio lock, and auto-respawns if the process dies.

- [ ] **Step 1: Write the test file first (TDD)**

```python
# tests/test_qmd_client.py
"""Tests for QMDClient subprocess management."""
from __future__ import annotations

import asyncio
import json
import pytest
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


@pytest.fixture
def bridge_path():
    """Absolute path to bridge.js in the plugin."""
    base = os.path.dirname(os.path.dirname(__file__))
    return os.path.join(base, "usr", "plugins", "qmd", "bridge", "bridge.js")


@pytest.mark.asyncio
async def test_ping_roundtrip(bridge_path):
    """Client starts bridge, pings it, gets pong back."""
    from usr.plugins.qmd.helpers.qmd_client import QMDClient

    client = QMDClient(bridge_path=bridge_path)
    try:
        await client.start()
        assert client.is_running()
        result = await client.call("ping")
        assert result == {"pong": True}
    finally:
        await client.stop()
    assert not client.is_running()


@pytest.mark.asyncio
async def test_auto_respawn(bridge_path):
    """Client auto-respawns if subprocess dies."""
    from usr.plugins.qmd.helpers.qmd_client import QMDClient

    client = QMDClient(bridge_path=bridge_path)
    await client.start()
    pid_before = client._proc.pid

    # Kill it
    client._proc.kill()
    await asyncio.sleep(0.1)

    # Next call should respawn
    result = await client.call("ping")
    assert result == {"pong": True}
    assert client._proc.pid != pid_before

    await client.stop()


@pytest.mark.asyncio
async def test_stop_is_clean(bridge_path):
    """stop() shuts bridge down without errors."""
    from usr.plugins.qmd.helpers.qmd_client import QMDClient

    client = QMDClient(bridge_path=bridge_path)
    await client.start()
    await client.stop()
    assert not client.is_running()
    # Second stop should be a no-op
    await client.stop()


@pytest.mark.asyncio
async def test_gating_blocks_management(bridge_path):
    """call() with gated=True and management_enabled=False raises QMDClientError."""
    from usr.plugins.qmd.helpers.qmd_client import QMDClient, QMDClientError

    client = QMDClient(bridge_path=bridge_path)
    await client.start()
    try:
        with pytest.raises(QMDClientError, match="disabled"):
            await client.call("embed", {}, gated=True, management_enabled=False)
    finally:
        await client.stop()


@pytest.mark.asyncio
async def test_gating_allows_when_enabled(bridge_path):
    """call() with gated=True and management_enabled=True proceeds to bridge."""
    from usr.plugins.qmd.helpers.qmd_client import QMDClient

    client = QMDClient(bridge_path=bridge_path)
    await client.start()
    try:
        # embed with no collections is a no-op — just verify it doesn't raise the gate error
        result = await client.call("embed", {"force": False}, gated=True, management_enabled=True)
        assert isinstance(result, dict)
    finally:
        await client.stop()
```

Save to: `tests/test_qmd_client.py`

- [ ] **Step 2: Run tests — expect FAIL (module not found)**

```bash
cd /Users/lazy/Documents/agent-zero
python -m pytest tests/test_qmd_client.py -v
```

Expected: `ModuleNotFoundError: No module named 'usr.plugins.qmd.helpers.qmd_client'`

- [ ] **Step 3: Write qmd_client.py**

```python
# usr/plugins/qmd/helpers/qmd_client.py
"""Async Python client for the QMD Node.js bridge.

Manages the bridge subprocess lifecycle (lazy start, persistent session,
auto-respawn) and serializes JSON-RPC 2.0 requests via stdin/stdout.
"""
from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Optional

BRIDGE_READY_TIMEOUT = 30  # seconds
TIMEOUT_SEARCH = 60        # seconds: query, vsearch, embed
TIMEOUT_DEFAULT = 10       # seconds: get, status, ping, management

# vsearch included at 60s even though spec only calls out query/embed —
# vector search with GGUF model loading is equally slow on cold start.
_LONG_METHODS = {"query", "vsearch", "embed"}


class QMDClientError(Exception):
    pass


class QMDClient:
    def __init__(
        self,
        bridge_path: str,
        db_path: str = "",
        startup_timeout: int = BRIDGE_READY_TIMEOUT,
    ) -> None:
        self._bridge_path = bridge_path
        self._db_path = db_path or ""
        self._startup_timeout = startup_timeout
        self._proc: Optional[asyncio.subprocess.Process] = None
        self._lock = asyncio.Lock()
        self._request_id = 0

    def is_running(self) -> bool:
        return self._proc is not None and self._proc.returncode is None

    async def start(self) -> None:
        """Spawn bridge subprocess and wait for ready signal."""
        env = {**os.environ}
        if self._db_path:
            env["QMD_DB_PATH"] = self._db_path

        self._proc = await asyncio.create_subprocess_exec(
            "node", self._bridge_path,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )

        # Wait for {"ready":true}
        try:
            line = await asyncio.wait_for(
                self._proc.stdout.readline(),
                timeout=self._startup_timeout,
            )
        except asyncio.TimeoutError:
            self._proc.kill()
            raise QMDClientError(
                f"QMD bridge did not start within {self._startup_timeout}s. "
                "Run plugin initialization first."
            )

        if not line:
            stderr = await self._proc.stderr.read()
            raise QMDClientError(
                f"QMD bridge exited immediately. stderr: {stderr.decode()[:200]}"
            )

        try:
            msg = json.loads(line.decode().strip())
        except json.JSONDecodeError:
            raise QMDClientError(f"QMD bridge sent unexpected ready signal: {line!r}")

        if not msg.get("ready"):
            raise QMDClientError(f"QMD bridge ready signal unexpected: {msg}")

    async def stop(self) -> None:
        """Close stdin and wait for bridge to exit cleanly."""
        if not self._proc:
            return
        try:
            if self._proc.stdin and not self._proc.stdin.is_closing():
                self._proc.stdin.close()
                await self._proc.stdin.wait_closed()
            await asyncio.wait_for(self._proc.wait(), timeout=5)
        except (asyncio.TimeoutError, Exception):
            self._proc.kill()
        finally:
            self._proc = None

    async def call(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        gated: bool = False,
        management_enabled: bool = False,
    ) -> dict[str, Any]:
        """Send a JSON-RPC request and return the result.

        Raises QMDClientError on JSON-RPC error responses.
        If gated=True and management_enabled=False, raises without calling bridge.
        """
        if gated and not management_enabled:
            raise QMDClientError(
                "Management operations are disabled. Enable in QMD plugin settings."
            )

        async with self._lock:
            if not self.is_running():
                await self.start()

            timeout = TIMEOUT_SEARCH if method in _LONG_METHODS else TIMEOUT_DEFAULT

            self._request_id += 1
            req_id = self._request_id
            request = json.dumps({
                "jsonrpc": "2.0",
                "id": req_id,
                "method": method,
                "params": params or {},
            })

            assert self._proc and self._proc.stdin
            self._proc.stdin.write((request + "\n").encode())
            await self._proc.stdin.drain()

            try:
                line = await asyncio.wait_for(
                    self._proc.stdout.readline(),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                raise QMDClientError(f"QMD bridge timed out on method '{method}' ({timeout}s)")

            if not line:
                # Process died — mark and respawn on next call
                self._proc = None
                raise QMDClientError("QMD bridge exited unexpectedly. Retry the request.")

            response = json.loads(line.decode().strip())

            if "error" in response:
                raise QMDClientError(response["error"]["message"])

            return response.get("result", {})

    async def _ensure_running(self) -> None:
        """Respawn bridge if it has died."""
        if not self.is_running():
            await self.start()
```

Save to: `usr/plugins/qmd/helpers/qmd_client.py`

- [ ] **Step 4: Add `__init__.py` files so Python can find the module**

```bash
touch usr/plugins/qmd/__init__.py
touch usr/plugins/qmd/helpers/__init__.py
```

- [ ] **Step 5: Run tests — expect PASS**

```bash
cd /Users/lazy/Documents/agent-zero
python -m pytest tests/test_qmd_client.py -v
```

Expected:
```
PASSED tests/test_qmd_client.py::test_ping_roundtrip
PASSED tests/test_qmd_client.py::test_auto_respawn
PASSED tests/test_qmd_client.py::test_stop_is_clean
```

Note: These tests require `@tobilu/qmd` to be installed in `bridge/node_modules/`. If QMD has no index set up yet, the store will open with no collections — that's fine, `ping` still works.

- [ ] **Step 6: Commit**

```bash
git add usr/plugins/qmd/helpers/qmd_client.py usr/plugins/qmd/__init__.py \
        usr/plugins/qmd/helpers/__init__.py tests/test_qmd_client.py
git commit -m "feat(qmd): add async QMDClient subprocess manager with auto-respawn"
```

---

## Chunk 3: Agent Tools

### Task 5: Status Tool (`tools/qmd_status.py`)

**Files:**
- Create: `usr/plugins/qmd/tools/qmd_status.py`
- Create: `tests/test_qmd_tools.py`

Simplest tool — no params, calls bridge `status`, formats output.

- [ ] **Step 1: Add `__init__.py` for tools package**

```bash
touch usr/plugins/qmd/tools/__init__.py
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_qmd_tools.py
"""Unit tests for QMD agent tools."""
from __future__ import annotations

import asyncio
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def make_mock_agent(plugin_config=None):
    """Build a minimal mock Agent sufficient for QMD tools."""
    agent = MagicMock()
    agent.number = 0
    agent.get_data = MagicMock(return_value=None)
    agent.set_data = MagicMock()
    agent.context = MagicMock()
    agent.context.log = MagicMock()
    agent.context.log.log = MagicMock(return_value=MagicMock())
    agent.loop_data = MagicMock()
    agent.config = MagicMock()
    agent.config.profile = "default"
    return agent


def make_tool(cls, agent, args):
    return cls(agent=agent, name=cls.__name__.lower(), method=None, args=args,
               message="", loop_data=None)


@pytest.mark.asyncio
async def test_status_tool_returns_message():
    """QMDStatus.execute() calls bridge status and returns formatted text."""
    from usr.plugins.qmd.tools.qmd_status import QMDStatus

    agent = make_mock_agent()
    mock_client = AsyncMock()
    mock_client.is_running.return_value = True
    mock_client.call = AsyncMock(return_value={
        "collections": [
            {"name": "notes", "doc_count": 42}
        ],
        "indexHealth": {}
    })
    agent.get_data.return_value = mock_client

    tool = make_tool(QMDStatus, agent, {})

    with patch("usr.plugins.qmd.tools.qmd_status.get_or_create_client",
               new=AsyncMock(return_value=mock_client)):
        response = await tool.execute()

    assert "notes" in response.message
    assert response.break_loop is False
```

Add to: `tests/test_qmd_tools.py`

- [ ] **Step 3: Run test — expect FAIL**

```bash
python -m pytest tests/test_qmd_tools.py::test_status_tool_returns_message -v
```

Expected: `ModuleNotFoundError: No module named 'usr.plugins.qmd.tools.qmd_status'`

- [ ] **Step 4: Write a shared client-access helper**

Create `usr/plugins/qmd/helpers/client_access.py` — shared by all tools to get or create the `QMDClient` for the current agent:

```python
# usr/plugins/qmd/helpers/client_access.py
"""Shared helper: get or lazily create the QMDClient for an agent session."""
from __future__ import annotations

import os
from typing import TYPE_CHECKING

from helpers import plugins
from usr.plugins.qmd.helpers.qmd_client import QMDClient

if TYPE_CHECKING:
    from agent import Agent

PLUGIN_NAME = "qmd"
CLIENT_KEY = "qmd_client"


async def get_or_create_client(agent: "Agent") -> QMDClient:
    """Return existing QMDClient for agent, or create and start a new one."""
    client = agent.get_data(CLIENT_KEY)
    if client is not None and client.is_running():
        return client

    config = plugins.get_plugin_config(PLUGIN_NAME, agent=agent) or {}
    plugin_dir = plugins.find_plugin_dir(PLUGIN_NAME)
    bridge_path = os.path.join(plugin_dir, "bridge", "bridge.js")
    db_path = config.get("db_path", "")
    startup_timeout = config.get("bridge_startup_timeout", 30)

    client = QMDClient(
        bridge_path=bridge_path,
        db_path=db_path,
        startup_timeout=startup_timeout,
    )
    await client.start()
    agent.set_data(CLIENT_KEY, client)
    return client


def is_management_enabled(agent: "Agent") -> bool:
    """Return True if management operations are allowed."""
    config = plugins.get_plugin_config(PLUGIN_NAME, agent=agent) or {}
    return bool(config.get("management_enabled", False))
```

Save to: `usr/plugins/qmd/helpers/client_access.py`

- [ ] **Step 5: Write qmd_status.py**

```python
# usr/plugins/qmd/tools/qmd_status.py
"""QMD status tool — returns index health and collection list."""
from __future__ import annotations

from helpers.tool import Tool, Response
from usr.plugins.qmd.helpers.client_access import get_or_create_client
from usr.plugins.qmd.helpers.qmd_client import QMDClientError


class QMDStatus(Tool):

    async def execute(self, **kwargs) -> Response:
        try:
            client = await get_or_create_client(self.agent)
            status = await client.call("status")
        except QMDClientError as e:
            return Response(message=f"QMD error: {e}", break_loop=False)

        collections = status.get("collections", [])
        if not collections:
            return Response(
                message="QMD: No collections indexed. Add one with `qmd collection add <path> --name <name>` then run `qmd embed`.",
                break_loop=False,
            )

        lines = ["QMD Index Status:", ""]
        for c in collections:
            name = c.get("name", "?")
            doc_count = c.get("doc_count", 0)
            lines.append(f"  • {name}: {doc_count} documents")

        bridge_running = "running" if client.is_running() else "stopped"
        lines.append(f"\nBridge: {bridge_running}")

        return Response(message="\n".join(lines), break_loop=False)
```

Save to: `usr/plugins/qmd/tools/qmd_status.py`

- [ ] **Step 6: Run test — expect PASS**

```bash
python -m pytest tests/test_qmd_tools.py::test_status_tool_returns_message -v
```

Expected: `PASSED`

- [ ] **Step 7: Commit**

```bash
git add usr/plugins/qmd/tools/qmd_status.py \
        usr/plugins/qmd/helpers/client_access.py \
        usr/plugins/qmd/helpers/__init__.py \
        tests/test_qmd_tools.py
git commit -m "feat(qmd): add status tool and shared client-access helper"
```

---

### Task 6: Search Tool (`tools/qmd_search.py`)

**Files:**
- Create: `usr/plugins/qmd/tools/qmd_search.py`
- Modify: `tests/test_qmd_tools.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_qmd_tools.py`:

```python
@pytest.mark.asyncio
async def test_search_tool_returns_results():
    """QMDSearch.execute() calls bridge query and formats results."""
    from usr.plugins.qmd.tools.qmd_search import QMDSearch

    agent = make_mock_agent()
    mock_client = AsyncMock()
    mock_client.is_running.return_value = True
    mock_client.call = AsyncMock(return_value=[
        {
            "title": "Auth Guide",
            "displayPath": "docs/auth.md",
            "docId": "#abc123",
            "score": 0.92,
            "snippet": "Authentication uses JWT tokens...",
            "context": "Work documentation",
        }
    ])

    tool = make_tool(QMDSearch, agent, {"q": "authentication", "mode": "query"})

    with patch("usr.plugins.qmd.tools.qmd_search.get_or_create_client",
               new=AsyncMock(return_value=mock_client)):
        response = await tool.execute(q="authentication", mode="query")

    assert "Auth Guide" in response.message
    assert "#abc123" in response.message
    assert "92%" in response.message
    assert response.break_loop is False


@pytest.mark.asyncio
async def test_search_tool_no_results():
    """QMDSearch returns helpful message when nothing found."""
    from usr.plugins.qmd.tools.qmd_search import QMDSearch

    agent = make_mock_agent()
    mock_client = AsyncMock()
    mock_client.call = AsyncMock(return_value=[])

    tool = make_tool(QMDSearch, agent, {"q": "xyzzy"})

    with patch("usr.plugins.qmd.tools.qmd_search.get_or_create_client",
               new=AsyncMock(return_value=mock_client)):
        response = await tool.execute(q="xyzzy")

    assert "No results" in response.message
```

- [ ] **Step 2: Run tests — expect FAIL**

```bash
python -m pytest tests/test_qmd_tools.py -k "search" -v
```

- [ ] **Step 3: Write qmd_search.py**

```python
# usr/plugins/qmd/tools/qmd_search.py
"""QMD search tool — query/search/vsearch across indexed collections."""
from __future__ import annotations

from helpers.tool import Tool, Response
from usr.plugins.qmd.helpers.client_access import get_or_create_client
from usr.plugins.qmd.helpers.qmd_client import QMDClientError

MAX_RESULTS = 10
MAX_SNIPPET_CHARS = 500


def _format_results(results: list) -> str:
    if not results:
        return "No results found."

    lines = []
    for r in results[:MAX_RESULTS]:
        title = r.get("title", r.get("displayPath", "?"))
        path = r.get("displayPath", "")
        docid = r.get("docId", "")
        score = r.get("score", 0)
        snippet = (r.get("snippet") or "")[:MAX_SNIPPET_CHARS]
        context = r.get("context", "")

        lines.append(f"**{title}** ({path}) {docid}")
        lines.append(f"Score: {round(score * 100)}%")
        if context:
            lines.append(f"Context: {context}")
        if snippet:
            lines.append(snippet)
        lines.append("")

    return "\n".join(lines).strip()


class QMDSearch(Tool):

    async def execute(
        self,
        q: str = "",
        mode: str = "query",
        collections: list | str | None = None,
        limit: int = 5,
        min_score: float = 0.0,
        intent: str = "",
        explain: bool = False,
        **kwargs,
    ) -> Response:
        if not q:
            return Response(message="QMD: 'q' parameter is required.", break_loop=False)

        limit = min(int(limit), MAX_RESULTS)
        if isinstance(collections, str):
            collections = [c.strip() for c in collections.split(",") if c.strip()]

        params: dict = {
            "q": q,
            "limit": limit,
            "minScore": float(min_score),
        }
        if collections:
            params["collections"] = collections
        if intent:
            params["intent"] = intent
        if explain:
            params["explain"] = True

        # Map mode to bridge method
        method = {"query": "query", "search": "search", "vsearch": "vsearch"}.get(mode, "query")

        try:
            client = await get_or_create_client(self.agent)
            results = await client.call(method, params)
        except QMDClientError as e:
            return Response(message=f"QMD error: {e}", break_loop=False)

        # searchLex/searchVector return list directly; query returns list too
        if isinstance(results, dict):
            results = results.get("items", results.get("results", []))

        return Response(message=_format_results(results), break_loop=False)
```

Save to: `usr/plugins/qmd/tools/qmd_search.py`

- [ ] **Step 4: Run tests — expect PASS**

```bash
python -m pytest tests/test_qmd_tools.py -k "search" -v
```

- [ ] **Step 5: Commit**

```bash
git add usr/plugins/qmd/tools/qmd_search.py tests/test_qmd_tools.py
git commit -m "feat(qmd): add search tool (query/search/vsearch modes)"
```

---

### Task 7: Get Tool (`tools/qmd_get.py`)

**Files:**
- Create: `usr/plugins/qmd/tools/qmd_get.py`
- Modify: `tests/test_qmd_tools.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_qmd_tools.py`:

```python
@pytest.mark.asyncio
async def test_get_tool_single():
    """QMDGet.execute() retrieves a single document by path."""
    from usr.plugins.qmd.tools.qmd_get import QMDGet

    agent = make_mock_agent()
    mock_client = AsyncMock()
    mock_client.call = AsyncMock(return_value={
        "title": "Auth Guide",
        "displayPath": "docs/auth.md",
        "body": "# Auth Guide\n\nContent here...",
    })

    tool = make_tool(QMDGet, agent, {"path": "docs/auth.md"})

    with patch("usr.plugins.qmd.tools.qmd_get.get_or_create_client",
               new=AsyncMock(return_value=mock_client)):
        response = await tool.execute(path="docs/auth.md")

    assert "Auth Guide" in response.message
    assert "Content here" in response.message


@pytest.mark.asyncio
async def test_get_tool_multi():
    """QMDGet.execute() with pattern calls multi_get."""
    from usr.plugins.qmd.tools.qmd_get import QMDGet

    agent = make_mock_agent()
    mock_client = AsyncMock()
    mock_client.call = AsyncMock(return_value={
        "docs": [
            {"displayPath": "docs/a.md", "body": "Content A"},
            {"displayPath": "docs/b.md", "body": "Content B"},
        ],
        "errors": []
    })

    tool = make_tool(QMDGet, agent, {"pattern": "docs/*.md"})

    with patch("usr.plugins.qmd.tools.qmd_get.get_or_create_client",
               new=AsyncMock(return_value=mock_client)):
        response = await tool.execute(pattern="docs/*.md")

    assert "docs/a.md" in response.message
    assert "docs/b.md" in response.message
```

- [ ] **Step 2: Run tests — expect FAIL**

```bash
python -m pytest tests/test_qmd_tools.py -k "get_tool" -v
```

- [ ] **Step 3: Write qmd_get.py**

```python
# usr/plugins/qmd/tools/qmd_get.py
"""QMD get tool — retrieve document(s) by path, docid, glob, or comma list."""
from __future__ import annotations

from helpers.tool import Tool, Response
from usr.plugins.qmd.helpers.client_access import get_or_create_client
from usr.plugins.qmd.helpers.qmd_client import QMDClientError

DEFAULT_MAX_LINES = 200
DEFAULT_MAX_BYTES = 10240


class QMDGet(Tool):

    async def execute(
        self,
        path: str = "",
        pattern: str = "",
        full: bool = False,
        line_numbers: bool = False,
        from_line: int | None = None,
        max_lines: int = DEFAULT_MAX_LINES,
        max_bytes: int = DEFAULT_MAX_BYTES,
        **kwargs,
    ) -> Response:
        if not path and not pattern:
            return Response(
                message="QMD: provide 'path' (single doc) or 'pattern' (glob/list).",
                break_loop=False,
            )

        try:
            client = await get_or_create_client(self.agent)

            if pattern:
                result = await client.call("multi_get", {
                    "pattern": pattern,
                    "maxBytes": int(max_bytes),
                })
                return Response(message=_format_multi(result), break_loop=False)
            else:
                params: dict = {
                    "path": path,
                    "full": bool(full),
                    "lineNumbers": bool(line_numbers),
                    "maxLines": int(max_lines),
                }
                if from_line is not None:
                    params["fromLine"] = int(from_line)
                result = await client.call("get", params)
                return Response(message=_format_single(result), break_loop=False)

        except QMDClientError as e:
            return Response(message=f"QMD error: {e}", break_loop=False)


def _format_single(doc: dict) -> str:
    if "error" in doc:
        parts = [f"Document not found: {doc['error']}"]
        similar = doc.get("similarFiles", [])
        if similar:
            parts.append("Did you mean:")
            parts.extend(f"  • {f}" for f in similar[:5])
        return "\n".join(parts)

    title = doc.get("title", doc.get("displayPath", ""))
    path = doc.get("displayPath", "")
    body = doc.get("body") or doc.get("snippet", "")
    context = doc.get("context", "")

    parts = [f"**{title}** ({path})"]
    if context:
        parts.append(f"Context: {context}")
    if body:
        parts.append("\n" + body)
    return "\n".join(parts)


def _format_multi(result: dict) -> str:
    docs = result.get("docs", [])
    errors = result.get("errors", [])

    parts = []
    for doc in docs:
        parts.append(f"--- {doc.get('displayPath', '?')} ---")
        parts.append(doc.get("body") or doc.get("snippet", ""))
        parts.append("")

    if errors:
        parts.append("Errors:")
        parts.extend(f"  • {e}" for e in errors)

    return "\n".join(parts).strip() or "No documents found."
```

Save to: `usr/plugins/qmd/tools/qmd_get.py`

- [ ] **Step 4: Run tests — expect PASS**

```bash
python -m pytest tests/test_qmd_tools.py -k "get_tool" -v
```

- [ ] **Step 5: Commit**

```bash
git add usr/plugins/qmd/tools/qmd_get.py tests/test_qmd_tools.py
git commit -m "feat(qmd): add get/multi-get tool with explicit path/pattern params"
```

---

### Task 8: Manage Tool (`tools/qmd_manage.py`)

**Files:**
- Create: `usr/plugins/qmd/tools/qmd_manage.py`
- Modify: `tests/test_qmd_tools.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_qmd_tools.py`:

```python
@pytest.mark.asyncio
async def test_manage_blocked_when_disabled():
    """QMDManage returns error when management_enabled is False."""
    from usr.plugins.qmd.tools.qmd_manage import QMDManage

    agent = make_mock_agent()
    mock_client = AsyncMock()

    tool = make_tool(QMDManage, agent, {"action": "embed"})

    with patch("usr.plugins.qmd.tools.qmd_manage.get_or_create_client",
               new=AsyncMock(return_value=mock_client)), \
         patch("usr.plugins.qmd.tools.qmd_manage.is_management_enabled", return_value=False):
        response = await tool.execute(action="embed")

    assert "disabled" in response.message.lower()
    mock_client.call.assert_not_called()


@pytest.mark.asyncio
async def test_manage_collection_add():
    """QMDManage.execute() calls collection_add when management enabled."""
    from usr.plugins.qmd.tools.qmd_manage import QMDManage

    agent = make_mock_agent()
    mock_client = AsyncMock()
    mock_client.call = AsyncMock(return_value={"ok": True})

    tool = make_tool(QMDManage, agent, {"action": "collection_add", "path": "/tmp/notes", "name": "notes"})

    with patch("usr.plugins.qmd.tools.qmd_manage.get_or_create_client",
               new=AsyncMock(return_value=mock_client)), \
         patch("usr.plugins.qmd.tools.qmd_manage.is_management_enabled", return_value=True):
        response = await tool.execute(action="collection_add", path="/tmp/notes", name="notes")

    mock_client.call.assert_called_once()
    assert "notes" in response.message or "ok" in response.message.lower()
```

- [ ] **Step 2: Run tests — expect FAIL**

```bash
python -m pytest tests/test_qmd_tools.py -k "manage" -v
```

- [ ] **Step 3: Write qmd_manage.py**

```python
# usr/plugins/qmd/tools/qmd_manage.py
"""QMD management tool — collection, context, index management (gated)."""
from __future__ import annotations

from helpers.tool import Tool, Response
from usr.plugins.qmd.helpers.client_access import get_or_create_client, is_management_enabled
from usr.plugins.qmd.helpers.qmd_client import QMDClientError

GATED_ACTIONS = {
    "collection_add", "collection_remove",
    "context_add", "context_remove",
    "update", "embed",
}


class QMDManage(Tool):

    async def execute(
        self,
        action: str = "",
        name: str = "",
        path: str = "",
        mask: str = "",
        text: str = "",
        collection: str = "",
        force: bool = False,
        pull: bool = False,
        **kwargs,
    ) -> Response:
        if not action:
            return Response(message="QMD: 'action' parameter is required.", break_loop=False)

        if action in GATED_ACTIONS and not is_management_enabled(self.agent):
            return Response(
                message="Management operations are disabled. Enable 'Management Access' in QMD plugin settings.",
                break_loop=False,
            )

        try:
            client = await get_or_create_client(self.agent)
            return await self._dispatch(client, action, name, path, mask, text, collection, force, pull)
        except QMDClientError as e:
            return Response(message=f"QMD error: {e}", break_loop=False)

    async def _dispatch(self, client, action, name, path, mask, text, collection, force, pull) -> Response:
        if action == "collection_add":
            if not path or not name:
                return Response(message="QMD: collection_add requires 'path' and 'name'.", break_loop=False)
            params = {"path": path, "name": name}
            if mask:
                params["mask"] = mask
            await client.call("collection_add", params)
            return Response(message=f"Collection '{name}' added from {path}.", break_loop=False)

        elif action == "collection_remove":
            if not name:
                return Response(message="QMD: collection_remove requires 'name'.", break_loop=False)
            await client.call("collection_remove", {"name": name})
            return Response(message=f"Collection '{name}' removed.", break_loop=False)

        elif action == "context_add":
            if not text:
                return Response(message="QMD: context_add requires 'text'.", break_loop=False)
            await client.call("context_add", {
                "collection": collection or "",
                "path": path or "/",
                "text": text,
            })
            return Response(message=f"Context added for {path or '/'}.", break_loop=False)

        elif action == "context_remove":
            await client.call("context_remove", {"collection": collection or "", "path": path or "/"})
            return Response(message=f"Context removed for {path or '/'}.", break_loop=False)

        elif action == "update":
            result = await client.call("update", {"pull": pull})
            indexed = result.get("indexed", 0)
            updated = result.get("updated", 0)
            removed = result.get("removed", 0)
            return Response(
                message=f"Index updated: {indexed} indexed, {updated} updated, {removed} removed.",
                break_loop=False,
            )

        elif action == "embed":
            result = await client.call("embed", {"force": force})
            embedded = result.get("embedded", 0)
            return Response(message=f"Embeddings generated: {embedded} chunks.", break_loop=False)

        else:
            return Response(
                message=f"QMD: unknown action '{action}'. Valid: collection_add, collection_remove, context_add, context_remove, update, embed.",
                break_loop=False,
            )
```

Save to: `usr/plugins/qmd/tools/qmd_manage.py`

- [ ] **Step 4: Run tests — expect PASS**

```bash
python -m pytest tests/test_qmd_tools.py -k "manage" -v
```

- [ ] **Step 5: Run all tool tests**

```bash
python -m pytest tests/test_qmd_tools.py tests/test_qmd_client.py -v
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add usr/plugins/qmd/tools/qmd_manage.py tests/test_qmd_tools.py
git commit -m "feat(qmd): add management tool with gated access control"
```

---

## Chunk 4: Extensions + Prompts

### Task 9: System Prompt Template (`prompts/qmd_tools.md`)

**Files:**
- Create: `usr/plugins/qmd/prompts/qmd_tools.md`

This file is loaded by the system_prompt extension and injected into every agent prompt.

- [ ] **Step 1: Write qmd_tools.md**

```markdown
## QMD Knowledge Search

You have access to a local hybrid search engine (QMD) for searching markdown notes, documentation, and knowledge bases.

**Available collections:** {{collections}}

### Tools

**qmd_search** — Search for information
- `mode`: `"query"` (best, uses AI reranking), `"search"` (fast keyword), `"vsearch"` (semantic)
- `q`: your query — plain text or structured syntax
- `collections`: optional list to restrict search
- `limit`: number of results (default 5)
- `intent`: optional context to disambiguate ambiguous queries

**qmd_get** — Retrieve document content
- `path`: file path or `#docid` (from search results)
- `pattern`: glob pattern or comma-separated list (for batch retrieval)
- `full`: true for complete content

**qmd_status** — Check index health and available collections

**qmd_manage** — Manage collections and index (requires management access)
- `action`: `collection_add`, `collection_remove`, `context_add`, `embed`, `update`

### Query Syntax (for qmd_search `q` param)

Single-line queries are auto-expanded. For best results use structured syntax:
```
lex: exact keywords "quoted phrase" -exclude
vec: natural language question about the topic
hyde: write what the answer would look like, 50-100 words
intent: disambiguation context (optional, on its own line)
```

### Search Strategy

1. **Start with `query` mode** — it auto-expands, does BM25+vector+reranking
2. **Use `lex:` when you know exact terms** — function names, error messages, version numbers
3. **Use `vec:` for concepts** — "how does X work", "why does Y happen"
4. **Combine `lex:` + `vec:`** for best recall on complex topics
5. **After search, use `qmd_get` with `#docid`** to retrieve full content of relevant documents
```

Save to: `usr/plugins/qmd/prompts/qmd_tools.md`

- [ ] **Step 2: Commit**

```bash
git add usr/plugins/qmd/prompts/qmd_tools.md
git commit -m "feat(qmd): add agent system prompt template"
```

---

### Task 10: System Prompt Extension

**Files:**
- Create: `usr/plugins/qmd/extensions/python/system_prompt/_20_qmd_prompt.py`

- [ ] **Step 1: Write _20_qmd_prompt.py**

```python
# usr/plugins/qmd/extensions/python/system_prompt/_20_qmd_prompt.py
"""Inject QMD tool documentation into the agent system prompt."""
from __future__ import annotations

from helpers.extension import Extension
from helpers import cache
from agent import LoopData

_CACHE_AREA = "qmd_prompt_cache"
_COLLECTION_CACHE_KEY = "collections"


class QMDPrompt(Extension):

    async def execute(
        self,
        system_prompt: list[str] = [],
        loop_data: LoopData = LoopData(),
        **kwargs,
    ):
        if not self.agent:
            return

        # Get collections — cache per session to avoid bridge call every message
        collections_str = await self._get_collections()

        prompt_text = self.agent.read_prompt(
            "qmd_tools.md",
            collections=collections_str,
        )
        system_prompt.append(prompt_text)

    async def _get_collections(self) -> str:
        """Return a comma-separated list of collection names, cached per session."""
        # cache.get(area, key, default) — two positional args required
        cached = cache.get(_CACHE_AREA, _COLLECTION_CACHE_KEY)
        if cached:
            return cached

        try:
            from usr.plugins.qmd.helpers.client_access import get_or_create_client
            client = await get_or_create_client(self.agent)
            result = await client.call("collection_list")
            collections = result.get("collections", [])
            names = ", ".join(c.get("name", "") for c in collections) or "none"
        except Exception:
            names = "unknown (bridge not running)"

        # cache.add(area, key, data) — no TTL support; clears on plugin reload
        cache.add(_CACHE_AREA, _COLLECTION_CACHE_KEY, names)
        return names
```

Save to: `usr/plugins/qmd/extensions/python/system_prompt/_20_qmd_prompt.py`

- [ ] **Step 2: Verify it loads in A0**

Start Agent Zero. Open Settings → Plugins → Enable QMD. Start a chat. Check that the system prompt contains the QMD section by asking the agent: "What search tools do you have available?"

Expected: Agent mentions `qmd_search`, `qmd_get`, etc.

- [ ] **Step 3: Commit**

```bash
git add usr/plugins/qmd/extensions/python/system_prompt/_20_qmd_prompt.py
git commit -m "feat(qmd): add system_prompt extension for agent tool awareness"
```

---

### Task 11: Agent Init Extension

**Files:**
- Create: `usr/plugins/qmd/extensions/python/agent_init/_30_qmd_auto_index.py`

- [ ] **Step 1: Write _30_qmd_auto_index.py**

```python
# usr/plugins/qmd/extensions/python/agent_init/_30_qmd_auto_index.py
"""Auto-index the current project directory on first agent init."""
from __future__ import annotations

import os
from helpers.extension import Extension
from helpers import plugins
from helpers.defer import DeferredTask


PLUGIN_NAME = "qmd"
AUTO_INDEXED_KEY = "qmd_auto_indexed"


class QMDAutoIndex(Extension):

    async def execute(self, **kwargs):
        if not self.agent:
            return

        # Root agent only — sub-agents do not auto-index
        if self.agent.number != 0:
            return

        # Run only once per agent context
        if self.agent.get_data(AUTO_INDEXED_KEY):
            return

        # Check config
        config = plugins.get_plugin_config(PLUGIN_NAME, agent=self.agent) or {}
        if not config.get("auto_index_project", True):
            return
        if not config.get("management_enabled", False):
            # Auto-index requires management access
            return

        cwd = self.agent.get_data("cwd") or os.getcwd()
        project_name = os.path.basename(cwd.rstrip("/\\"))

        try:
            from usr.plugins.qmd.helpers.client_access import get_or_create_client
            client = await get_or_create_client(self.agent)

            # Check if a collection for this path already exists
            result = await client.call("collection_list")
            collections = result.get("collections", [])
            existing_paths = {c.get("pwd", "") for c in collections}

            if cwd not in existing_paths:
                await client.call("collection_add", {
                    "path": cwd,
                    "name": project_name,
                })

                # Fire embed in background — don't block agent startup
                async def run_embed():
                    await client.call("embed", {})

                DeferredTask().start_task(run_embed)

        except Exception:
            # Auto-index is best-effort — never fail agent init
            pass

        self.agent.set_data(AUTO_INDEXED_KEY, True)
```

Save to: `usr/plugins/qmd/extensions/python/agent_init/_30_qmd_auto_index.py`

- [ ] **Step 2: Manual test**

Enable the plugin in A0 settings. Also enable "Management Access" in the QMD config panel. Start a new chat in a project directory. Run `qmd_status` — the project directory should appear as a collection.

- [ ] **Step 3: Commit**

```bash
git add usr/plugins/qmd/extensions/python/agent_init/_30_qmd_auto_index.py
git commit -m "feat(qmd): add agent_init extension for auto-indexing project directory"
```

---

## Chunk 5: API Handler + Config UI + Initialize

### Task 12: Status API Handler (`api/status.py`)

**Files:**
- Create: `usr/plugins/qmd/api/status.py`

- [ ] **Step 1: Write status.py**

```python
# usr/plugins/qmd/api/status.py
"""GET /api/plugins/qmd/status — bridge state for the config UI."""
from __future__ import annotations

from helpers.api import ApiHandler, Input, Output, Request


class Status(ApiHandler):

    @classmethod
    def get_methods(cls) -> list[str]:
        return ["GET"]

    @classmethod
    def requires_csrf(cls) -> bool:
        return False  # Read-only status endpoint; no state mutation

    async def process(self, input: Input, request: Request) -> Output:
        ctxid = request.args.get("ctxid", "") or input.get("ctxid", "")
        context = self.use_context(ctxid) if ctxid else None
        agent = context.streaming_agent if context else None

        running = False
        pid = None
        collections = []

        if agent:
            client = agent.get_data("qmd_client")
            if client:
                running = client.is_running()
                if running and hasattr(client, "_proc") and client._proc:
                    pid = client._proc.pid
                try:
                    result = await client.call("collection_list")
                    collections = result.get("collections", [])
                except Exception:
                    pass

        return {
            "running": running,
            "pid": pid,
            "collections": [
                {"name": c.get("name", ""), "doc_count": c.get("doc_count", 0)}
                for c in collections
            ],
        }
```

Save to: `usr/plugins/qmd/api/status.py`

- [ ] **Step 2: Verify endpoint is reachable**

With A0 running and QMD plugin enabled, make a request:

```bash
curl -s "http://localhost:8000/api/plugins/qmd/status" | python -m json.tool
```

Expected response shape:
```json
{"running": false, "pid": null, "collections": []}
```

- [ ] **Step 3: Commit**

```bash
git add usr/plugins/qmd/api/status.py
git commit -m "feat(qmd): add status API handler for config UI"
```

---

### Task 13: Config UI (`webui/config.html`)

**Files:**
- Create: `usr/plugins/qmd/webui/config.html`

Uses Alpine.js (`x-data`, `x-model`, `x-if`) matching A0's existing config UI pattern.

- [ ] **Step 1: Write config.html**

```html
<html>
<head>
    <title>QMD Knowledge Search</title>
</head>

<body>
    <div x-data="{ bridgeStatus: null }" x-init="
        fetch('/api/plugins/qmd/status?ctxid=' + (context?.id || ''))
            .then(r => r.json())
            .then(d => bridgeStatus = d)
            .catch(() => bridgeStatus = { running: false, collections: [] })
    ">
        <template x-if="config">
            <div>
                <div class="section-title">QMD Knowledge Search</div>
                <div class="section-description">
                    Local hybrid search for markdown notes, docs, and knowledge bases.
                    Uses BM25 + vector + LLM reranking, all on-device.
                </div>

                <!-- Bridge Status Card -->
                <div class="field" x-show="bridgeStatus">
                    <div class="field-label">
                        <div class="field-title">Bridge Status</div>
                        <div class="field-description">
                            QMD Node.js bridge process state.
                        </div>
                    </div>
                    <div class="field-control">
                        <span x-show="bridgeStatus?.running" style="color: green">● Running</span>
                        <span x-show="!bridgeStatus?.running" style="color: gray">○ Stopped</span>
                        <span x-show="bridgeStatus?.collections?.length > 0">
                            — <span x-text="bridgeStatus?.collections?.length"></span> collection(s)
                        </span>
                    </div>
                </div>

                <!-- Management Access Toggle -->
                <div class="field">
                    <div class="field-label">
                        <div class="field-title">Management Access</div>
                        <div class="field-description">
                            Allow the agent to add/remove collections, add context, and trigger reindexing.
                            Disabled by default — enable only if you want the agent to modify your index.
                        </div>
                    </div>
                    <div class="field-control">
                        <label class="toggle">
                            <input type="checkbox" x-model="config.management_enabled" />
                            <span class="toggler"></span>
                        </label>
                    </div>
                </div>

                <!-- Auto-index Project Toggle -->
                <div class="field">
                    <div class="field-label">
                        <div class="field-title">Auto-index Project</div>
                        <div class="field-description">
                            Automatically add the current project directory as a QMD collection
                            when an agent session starts. Requires Management Access to be enabled.
                        </div>
                    </div>
                    <div class="field-control">
                        <label class="toggle">
                            <input type="checkbox" x-model="config.auto_index_project" />
                            <span class="toggler"></span>
                        </label>
                    </div>
                </div>

                <!-- Database Path -->
                <div class="field">
                    <div class="field-label">
                        <div class="field-title">Database Path</div>
                        <div class="field-description">
                            Path to the QMD SQLite index. Leave empty to use the QMD default
                            (~/.cache/qmd/index.sqlite).
                        </div>
                    </div>
                    <div class="field-control">
                        <input type="text"
                            x-model="config.db_path"
                            placeholder="~/.cache/qmd/index.sqlite" />
                    </div>
                </div>

            </div>
        </template>
    </div>
</body>
</html>
```

Save to: `usr/plugins/qmd/webui/config.html`

- [ ] **Step 2: Verify in A0 UI**

Go to Settings → Plugins → QMD → Configure. Verify the settings panel renders with toggles and status card.

- [ ] **Step 3: Commit**

```bash
git add usr/plugins/qmd/webui/config.html
git commit -m "feat(qmd): add plugin config UI with status card and toggles"
```

---

### Task 14: Initialization Script (`initialize.py`)

**Files:**
- Create: `usr/plugins/qmd/initialize.py`

- [ ] **Step 1: Write initialize.py**

```python
# usr/plugins/qmd/initialize.py
"""One-time setup for the QMD plugin.

Verifies Node.js >= 22, installs @tobilu/qmd via npm, and runs
a bridge selftest to confirm the installation works.
"""
from __future__ import annotations

import subprocess
import sys
import os


def main() -> int:
    plugin_dir = os.path.dirname(os.path.abspath(__file__))
    bridge_dir = os.path.join(plugin_dir, "bridge")
    bridge_js = os.path.join(bridge_dir, "bridge.js")

    # Step 1: Check Node.js >= 22
    print("Checking Node.js version...")
    try:
        result = subprocess.run(
            ["node", "--version"], capture_output=True, text=True, check=True
        )
        version_str = result.stdout.strip().lstrip("v")
        major = int(version_str.split(".")[0])
        if major < 22:
            print(f"ERROR: Node.js {version_str} found, but >= 22 is required.")
            print("Install from https://nodejs.org or: brew install node")
            return 1
        print(f"  Node.js {version_str} ✓")
    except FileNotFoundError:
        print("ERROR: Node.js not found.")
        print("Install from https://nodejs.org or: brew install node")
        return 1

    # Step 2: npm install in bridge/
    print("Installing @tobilu/qmd (this may take a minute)...")
    result = subprocess.run(
        ["npm", "install"],
        cwd=bridge_dir,
        check=False,
    )
    if result.returncode != 0:
        print("ERROR: npm install failed.")
        return result.returncode
    print("  @tobilu/qmd installed ✓")

    # Step 3: Bridge selftest
    print("Running bridge selftest...")
    result = subprocess.run(
        ["node", bridge_js, "--selftest"],
        capture_output=True, text=True, check=False,
        timeout=60,
    )
    if result.returncode != 0:
        print(f"ERROR: Bridge selftest failed (exit {result.returncode}).")
        print(f"stderr: {result.stderr[:300]}")
        return result.returncode
    print("  Bridge selftest passed ✓")

    print("")
    print("QMD bridge ready.")
    print("Next steps:")
    print("  qmd collection add ~/notes --name notes")
    print("  qmd embed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Save to: `usr/plugins/qmd/initialize.py`

- [ ] **Step 2: Test initialize.py manually**

```bash
cd /Users/lazy/Documents/agent-zero
python usr/plugins/qmd/initialize.py
```

Expected output:
```
Checking Node.js version...
  Node.js 22.x.x ✓
Installing @tobilu/qmd (this may take a minute)...
  @tobilu/qmd installed ✓
Running bridge selftest...
  Bridge selftest passed ✓

QMD bridge ready.
...
```

- [ ] **Step 3: Verify "Init" button works in A0 UI**

Go to Settings → Plugins → QMD → Init. Confirm the initialization runs and succeeds.

- [ ] **Step 4: Commit**

```bash
git add usr/plugins/qmd/initialize.py
git commit -m "feat(qmd): add initialize.py for node/npm setup and bridge selftest"
```

---

## Final Verification

- [ ] **Run full test suite**

```bash
cd /Users/lazy/Documents/agent-zero
python -m pytest tests/test_qmd_client.py tests/test_qmd_tools.py -v
```

Expected: all tests PASS.

- [ ] **End-to-end smoke test in A0**

1. Enable QMD plugin
2. Run Init
3. Start a chat
4. Ask: "Use qmd_status to check the index"
5. Ask: "Search for documentation about authentication using qmd_search"
6. Ask: "Get the file from the result using qmd_get with the docid"

Expected: Agent correctly calls each tool and formats results.

- [ ] **Final commit**

```bash
git add -A
git commit -m "feat(qmd): QMD plugin complete — all tools, extensions, API, config UI"
```
