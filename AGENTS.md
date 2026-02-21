# Agent Zero — Full-Stack Agent & Plugin Architecture

This document bridges the gap between the **Python Backend** (AgentContext, LLM loop) and the **Frontend Component System** (Alpine.js, Modals). Use this as the canonical reference for building deep integrations.

---

## 1. The Core Concept: `AgentContext`

Every conversation in Agent Zero is an `AgentContext`. It owns the message history, the LLM state, the tool definitions, and the log queue.

### Backend: Managing Contexts
When building a plugin, you must interact with the context system correctly:

```python
from agent import AgentContext, AgentContextType, initialize_agent
from python.helpers.messages import UserMessage

# 1. Access an existing context (e.g., from a stored ID)
context = AgentContext.use(context_id)

# 2. Or create a new one
config = {} # use defaults
context = AgentContext(config=config, type=AgentContextType.USER)
await initialize_agent(context)

# 3. Communicate (send a message and wait for completion)
task = context.communicate(UserMessage("Hello Agent!"))
response_text = await task.result()
```

### The Glue: `MessageQueue` (mq)
The frontend listens to a WebSocket. To make messages appear in the WebUI from your plugin, use the log helper:

```python
# In your ApiHandler or bridge
from python.helpers.messages import mq

# This makes the user message appear in the UI immediately
mq.log_user_message(context.id, "Incoming message from WhatsApp", source="WhatsApp")
```

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
2. Set `"settings_sections": ["agent"]` in `plugin.json` - this places a subsection with a Settings button in the chosen tab.

Your `config.html` binds to `$store.pluginSettings.settings` (a plain object persisted as `config.json`). The modal's Save/Cancel footer handles persistence automatically. See `plugins/README.md` for the full contract and settings resolution priority chain.

For plugins that surface **existing core settings** (e.g. wrapping `settings/agent/memory.html`), set `$store.pluginSettings.saveMode = 'core'` in `x-init` to route Save through the core settings API instead.

---

## 4. Lifecycle Synchronization

| Action | Backend Extension | Frontend Lifecycle |
|---|---|---|
| **Initialization** | `agent_init` | `init()` in Store |
| **Mounting** | N/A | `x-create` directive |
| **Processing** | `monologue_start/end` | UI loading state |
| **Cleanup** | `context_deleted` | `x-destroy` directive |

---

## 5. Directory Mapping (Plugin Layout)

> [!IMPORTANT]
> **Always create new plugins in `usr/plugins/`.** The root `/plugins/` folder is reserved for core Agent Zero plugins and may be overwritten during framework updates.

```text
usr/plugins/my-plugin/
├── plugin.json           # Required manifest (name, version, settings_sections)
├── api/                  # ApiHandler (python.helpers.api)
├── extensions/
│   ├── python/agent_init/ # Auto-start logic
│   └── webui/            # sidebar-quick-actions-main-start/
└── webui/
    ├── config.html       # Optional: plugin settings UI
    └── my-modal.html     # Full plugin pages + stores
```

Refer to `docs/agents/AGENTS.components.md` for deep UI technicals and `docs/agents/AGENTS.modals.md` for modal-specific CSS classes (`btn-ok`, `btn-cancel`).

