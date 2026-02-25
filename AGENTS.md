# Agent Zero - AGENTS.md

[Generated using reconnaissance on 2026-02-22]

## Quick Reference
Tech Stack: Python 3.12+ | Flask | Alpine.js | LiteLLM | WebSocket (Socket.io)
Dev Server: python run_ui.py (runs on http://localhost:50001 by default)
Run Tests: pytest (standard) or pytest tests/test_name.py (file-scoped)
Documentation: README.md | docs/
Frontend Deep Dives: [Component System](docs/agents/AGENTS.components.md) | [Modal System](docs/agents/AGENTS.modals.md) | [Plugin Architecture](AGENTS.plugins.md)

---

## Table of Contents
1. [Project Overview](#project-overview)
2. [Core Commands](#core-commands)
3. [Docker Environment](#docker-environment)
4. [Project Structure](#project-structure)
5. [Development Patterns & Conventions](#development-patterns--conventions)
6. [Safety and Permissions](#safety-and-permissions)
7. [Code Examples](#code-examples)
8. [Git Workflow](#git-workflow)
9. [API Documentation](#api-documentation)
10. [Troubleshooting](#troubleshooting)

---

## Project Overview

Agent Zero is a dynamic, organic agentic framework designed to grow and learn. It uses the operating system as a tool, featuring a multi-agent cooperation model where every agent can create subordinates to break down tasks.

Type: Full-Stack Agentic Framework (Python Backend + Alpine.js Frontend)
Status: Active Development
Primary Language(s): Python, JavaScript (ES Modules)

---

## Core Commands

### Setup
Do not combine these commands; run them individually:
```bash
pip install -r requirements.txt
pip install -r requirements2.txt
```
- Start WebUI: python run_ui.py

---

## Docker Environment

When running in Docker, Agent Zero uses two distinct Python runtimes to isolate the framework from the code being executed:

### 1. Framework Runtime (/opt/venv-a0)
- Version: Python 3.12.4
- Purpose: Runs the Agent Zero backend, API, and core logic.
- Packages: Contains all dependencies from requirements.txt.

### 2. Execution Runtime (/opt/venv)
- Version: Python 3.13
- Purpose: Default environment for the interactive terminal and the agent's code execution tool.
- Behavior: This is the environment active when you docker exec into the container. Packages installed by the agent via pip install during a task are stored here.

---

## Project Structure

```
/
├── agent.py              # Core Agent and AgentContext definitions
├── initialize.py         # Framework initialization logic
├── models.py             # LLM provider configurations
├── run_ui.py             # WebUI server entry point
├── python/
│   ├── api/              # API Handlers (ApiHandler subclasses)
│   ├── extensions/       # Backend lifecycle extensions
│   ├── helpers/          # Shared Python utilities (plugins, files, etc.)
│   ├── tools/            # Agent tools (Tool subclasses)
│   └── websocket_handlers/# WebSocket event handlers
├── webui/
│   ├── components/       # Alpine.js components
│   ├── js/               # Core frontend logic (modals, stores, etc.)
│   └── index.html        # Main UI shell
├── usr/                  # User data directory (isolated from core)
│   ├── plugins/          # Custom user plugins
│   ├── settings.json     # User-specific configuration
│   └── workdir/          # Default agent workspace
├── plugins/              # Core system plugins
├── agents/               # Agent profiles (prompts and config)
├── prompts/              # System and message prompt templates
└── tests/                # Pytest suite
```

Key Files:
- agent.py: Defines AgentContext and the main Agent class.
- python/helpers/plugins.py: Plugin discovery and configuration logic.
- webui/js/AlpineStore.js: Store factory for reactive frontend state.
- python/helpers/api.py: Base class for all API endpoints.
- docs/agents/AGENTS.components.md: Deep dive into the frontend component architecture.
- docs/agents/AGENTS.modals.md: Guide to the stacked modal system.
- AGENTS.plugins.md: Comprehensive guide to the full-stack plugin system.

---

## Development Patterns & Conventions

### Backend (Python)
- Context Access: Use from agent import AgentContext, AgentContextType (not python.helpers.context).
- Communication: Use mq from python.helpers.messages to log proactive UI messages:
  mq.log_user_message(context.id, "Message", source="Plugin")
- API Handlers: Derive from ApiHandler in python/helpers/api.py.
- Extensions: Use the extension framework in python/helpers/extension.py for lifecycle hooks.
- Error Handling: Use RepairableException for errors the LLM might be able to fix.

### Frontend (Alpine.js)
- Store Gating: Always wrap store-dependent content in a template:
```html
<div x-data>
  <template x-if="$store.myStore">
    <div x-init="$store.myStore.onOpen()">...</div>
  </template>
</div>
```
- Store Registration: Use createStore from /js/AlpineStore.js.
- Modals: Use openModal(path) and closeModal() from /js/modals.js.

---

## 2. The Frontend: Component System

Agent Zero uses a custom **Component Loader** that fetches HTML, extracts `<style>` and `<script type="module">`, and injects them into the DOM.

### The "Golden Rules" of Frontend Components

1.  **Store Gating (Critical)**: Always wrap your component content in a template that waits for the store. This prevents "undefined" errors during the loading race.
    ```html
    <div x-data>
      <template x-if="$store.myStore">
        <div class="content">...</div>
      </template>
    </div>
    ```
2.  **Separate Store Files**: Never put store registration logic directly inside the HTML `alpine:init` block. Use a separate `*-store.js` file and import it via `<script type="module" src="...">`.
3.  **createStore Proxy**: Use `createStore` from `/js/AlpineStore.js`. It ensures the store is available to the module even before Alpine fully boots.

---

## 3. The Modal System

Modals in A0 are "stacked" and loaded dynamically via `openModal(path)`.

### Directory Convention
- `webui/components/modals/<feature>/<feature>.html`
- `webui/components/modals/<feature>/<feature>-store.js`

### Plugin Settings

Plugins get a dedicated settings modal with **Project** and **Agent profile** context selectors. To enable it:

1. Add `webui/config.html` to your plugin (auto-detected).
2. Set `"settings_sections": ["agent"]` in `plugin.yaml` - this places a subsection with a Settings button in the chosen tab.

Your `config.html` binds to `$store.pluginSettings.settings` (a plain object persisted as `config.yaml`). The modal's Save/Cancel footer handles persistence automatically. See `plugins/README.md` for the full contract and settings resolution priority chain.

For plugins that surface **existing core settings** (e.g. wrapping `settings/agent/memory.html`), set `$store.pluginSettings.saveMode = 'core'` in `x-init` to route Save through the core settings API instead.

---

## 4. Lifecycle Synchronization

### Lifecycle Synchronization
| Action | Backend Extension | Frontend Lifecycle |
|---|---|---|
| Initialization | agent_init | init() in Store |
| Mounting | N/A | x-create directive |
| Processing | monologue_start/end | UI loading state |
| Cleanup | context_deleted | x-destroy directive |

---

## Safety and Permissions

### Allowed Without Asking
- Read any file in the repository.
- Update code files in usr/.

usr/plugins/my-plugin/
├── plugin.yaml           # Required manifest (name, version, settings_sections)
├── api/                  # ApiHandler (python.helpers.api)
├── extensions/
│   ├── python/agent_init/ # Auto-start logic
│   └── webui/            # sidebar-quick-actions-main-start/
└── webui/
    ├── config.html       # Optional: plugin settings UI
    └── my-modal.html     # Full plugin pages + stores

### Ask Before Executing
- pip install (new dependencies).
- Deleting core files outside of usr/ or tmp/.
- Modifying agent.py or initialize.py.
- Making git commits or pushes.

### Never Do
- Commit, hardcode or leak secrets or .env files.
- Bypass CSRF or authentication checks.
- Hardcode API keys.

---

## Code Examples

### API Handler (Good)
```python
from python.helpers.api import ApiHandler, Request, Response

class MyHandler(ApiHandler):
    async def process(self, input: dict, request: Request) -> dict | Response:
        # Business logic here
        return {"ok": True, "data": "result"}
```

### Alpine Store (Good)
```javascript
import { createStore } from "/js/AlpineStore.js";

export const store = createStore("myStore", {
    items: [],
    init() { /* global setup */ },
    onOpen() { /* mount setup */ },
    cleanup() { /* unmount cleanup */ }
});
```

### Tool Definition (Good)
```python
from python.helpers.tool import Tool, ToolResult

class MyTool(Tool):
    async def execute(self, arg1: str):
        # Tool logic
        return ToolResult("Success")
```

---

## Troubleshooting

### Dependency Conflicts
If pip install fails, try running in a clean virtual environment:
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements2.txt
```

### WebSocket Connection Failures
- Check if X-CSRF-Token is being sent.
- Ensure the runtime ID in the session matches the current server instance.

---

*Last updated: 2026-02-22*
*Maintained by: Agent Zero Core Team*
