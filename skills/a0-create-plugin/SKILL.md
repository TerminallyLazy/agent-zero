---
name: a0-create-plugin
description: Create, extend, or modify Agent Zero plugins. Follows strict full-stack conventions (usr/plugins, plugin.json, Store Gating, AgentContext, plugin settings). Use for UI hooks, API handlers, lifecycle extensions, or plugin settings UI.
---

# Agent Zero Plugin Development

> [!IMPORTANT]
> Always create new plugins in usr/plugins/<plugin_name>/. The root /plugins directory is reserved for core system plugins.

Primary references:
- /a0/AGENTS.md (Full-stack architecture & AgentContext)
- /a0/docs/agents/AGENTS.components.md (Component system deep dive)
- /a0/docs/agents/AGENTS.modals.md (Modal system & CSS conventions)
- /a0/AGENTS.plugins.md (Extension points, plugin.json, settings system)

## Plugin Manifest (plugin.json)

Every plugin must have a plugin.json or it will not be discovered:

```json
{
  "name": "My Plugin",
  "description": "What this plugin does.",
  "version": "1.0.0",
  "settings_sections": ["agent"]
}
```

settings_sections controls which Settings tabs show a subsection for this plugin. Valid values: agent, external, mcp, developer, backup. Use [] for no subsection.

## Mandatory Frontend Patterns

### 1. The "Store Gate" Template
To avoid race conditions and undefined errors, every component must use this wrapper:
```html
<div x-data>
  <template x-if="$store.myPluginStore">
    <div x-init="$store.myPluginStore.onOpen()" x-destroy="$store.myPluginStore.cleanup()">
       <!-- Content goes here -->
    </div>
  </template>
</div>
```

### 2. Separate Store Module
Place store logic in a separate .js file. Do NOT use alpine:init listeners inside HTML.
```javascript
// webui/my-store.js
import { createStore } from "/js/AlpineStore.js";
export const store = createStore("myPluginStore", {
    status: 'idle',
    init() { ... },
    onOpen() { ... },
    cleanup() { ... }
});
```
Import it in the HTML <head>:
```html
<head>
  <script type="module" src="/plugins/<plugin_name>/webui/my-store.js"></script>
</head>
```

## Plugin Settings

If your plugin needs user-configurable settings, add webui/config.html. The system detects it automatically and shows a Settings button in the relevant tabs (per settings_sections in plugin.json).

### Settings modal contract

The modal provides Project + Agent profile context selectors. Your config.html binds to $store.pluginSettings.settings:

```html
<html>
<head>
  <title>My Plugin Settings</title>
  <script type="module">
    import { store } from "/components/plugins/plugin-settings-store.js";
  </script>
</head>
<body>
  <div x-data>
    <input x-model="$store.pluginSettings.settings.my_key" />
    <input type="checkbox" x-model="$store.pluginSettings.settings.feature_enabled" />
  </div>
</body>
</html>
```

The modal's Save button persists $store.pluginSettings.settings to config.json in the correct scope (project/agent/global).

### Surfacing core settings (e.g. memory pattern)

If your plugin exposes existing core settings rather than plugin-specific ones, set saveMode = 'core' so Save delegates to the core settings API:

```html
<div x-data x-init="
    $store.pluginSettings.saveMode = 'core';
    if ($store.settings && !$store.settings.settings) $store.settings.onOpen();
">
  <x-component path="settings/agent/memory.html"></x-component>
</div>
```

### Sidebar Button (sidebar entry point)
- Extension point: sidebar-quick-actions-main-start
- Class: class="config-button"
- Placement: x-move-after=".config-button#dashboard"
- Action: @click="openModal('/plugins/<plugin_name>/webui/my-modal.html')"

## Backend API & Context

### Import Paths
- Correct: from agent import AgentContext, AgentContextType
- Correct: from initialize import initialize_agent

### Sending Messages Proactively
```python
from agent import AgentContext
from python.helpers.messages import UserMessage

context = AgentContext.use(context_id)
task = context.communicate(UserMessage("Message text"))
response = await task.result()
```

### Reading Plugin Settings (backend)
```python
from python.helpers.plugins import get_plugin_config, save_plugin_config

# Runtime (with running agent - resolves project/profile from context)
settings = get_plugin_config("my-plugin", agent=agent) or {}

# Explicit write target (project/profile scope)
save_plugin_config(
    "my-plugin",
    project_name="my-project",
    agent_profile="default",
    settings=settings,
)
```

## Directory Layout
```
usr/plugins/<name>/
  plugin.json           # Required manifest
  api/                  # API Handlers (ApiHandler base class)
  tools/                # Tool subclasses
  extensions/
    python/agent_init/  # Python lifecycle extensions
    webui/<point>/      # HTML/JS hook extensions
  webui/
    config.html         # Optional: plugin settings UI
    my-modal.html       # Full plugin pages
    my-store.js         # Alpine stores
```
