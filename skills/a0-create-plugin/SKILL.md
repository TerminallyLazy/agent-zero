---
name: a0-create-plugin
description: Create, extend, or modify Agent Zero plugins. Follows strict full-stack conventions (usr/plugins, plugin.yaml, Store Gating, AgentContext, plugin settings). Use for UI hooks, API handlers, lifecycle extensions, or plugin settings UI.
---

# Agent Zero Plugin Development

> [!IMPORTANT]
> Always create new plugins in `/a0/usr/plugins/<plugin_name>/`. The `/a0/plugins/` directory is reserved for core system plugins.

Primary references:
- /a0/AGENTS.md (Full-stack architecture & AgentContext)
- /a0/docs/agents/AGENTS.components.md (Component system deep dive)
- /a0/docs/agents/AGENTS.modals.md (Modal system & CSS conventions)
- /a0/AGENTS.plugins.md (Extension points, plugin.yaml, settings system, Plugin Index)

---

## Step 0: Ask First — Local or Community Plugin?

Before starting, ask the user one question:

> "Should this plugin be **local only** (stays in your Agent Zero installation) or a **community plugin** (published to the Plugin Index so others can install it)?"

- **Local plugin**: Create it in `/a0/usr/plugins/<plugin_name>/`. No repository needed. Skip to the manifest section below.
- **Community plugin**: The plugin must live in its own GitHub repository (runtime manifest at the repo root), and then a separate index submission PR is made to https://github.com/agent0ai/a0-plugins. Guide the user through both steps.

---

## Plugin Manifest (plugin.yaml)

Every plugin must have a `plugin.yaml` or it will not be discovered.

```yaml
title: My Plugin
description: What this plugin does.
version: 1.0.0
settings_sections:
  - agent
per_project_config: false
per_agent_config: false
```

`settings_sections` controls which Settings tabs show a subsection for this plugin. Valid values: `agent`, `external`, `mcp`, `developer`, `backup`. Use `[]` for no subsection.

Activation defaults to ON when no toggle rule exists. Set `per_project_config` and/or `per_agent_config` to enable advanced per-scope switching. Core system plugins may also use `always_enabled: true` to lock the plugin permanently ON (reserved for framework use).

---

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

---

## Plugin Settings

If your plugin needs user-configurable settings, add `webui/config.html`. The system detects it automatically and shows a Settings button in the relevant tabs (per `settings_sections` in `plugin.yaml`).

### Settings modal contract

The modal provides Project + Agent profile context selectors. Your config.html binds to `$store.pluginSettings.settings`:

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

The modal's Save button persists `$store.pluginSettings.settings` to `config.json` in the correct scope (project/agent/global).

### Surfacing core settings (e.g. memory pattern)

If your plugin exposes existing core settings rather than plugin-specific ones, set `saveMode = 'core'` so Save delegates to the core settings API:

```html
<div x-data x-init="
    $store.pluginSettings.saveMode = 'core';
    if ($store.settings && !$store.settings.settings) $store.settings.onOpen();
">
  <x-component path="settings/agent/memory.html"></x-component>
</div>
```

### Sidebar Button (sidebar entry point)
- Extension point: `sidebar-quick-actions-main-start`
- Class: `class="config-button"`
- Placement: `x-move-after=".config-button#dashboard"`
- Action: `@click="openModal('/plugins/<plugin_name>/webui/my-modal.html')"`

---

## Backend API & Context

### Import Paths
- Correct: `from agent import AgentContext, AgentContextType`
- Correct: `from initialize import initialize_agent`

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

---

## Directory Layout
```
/a0/usr/plugins/<name>/
  plugin.yaml           # Required manifest
  default_config.yaml   # Optional default settings fallback
  README.md             # Optional, shown in Plugin List UI
  LICENSE               # Optional, shown in Plugin List UI
  agents/
    <profile>/agent.yaml # Optional plugin-distributed agent profile
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

---

## Community Plugin: GitHub Repo + Plugin Index Submission

If the user chose a **community plugin**, follow these additional steps after building and testing the plugin locally.

### 1. Repository Structure

The plugin must live in its own GitHub repository with the plugin contents at the **repository root** (not inside a subfolder):

```text
your-plugin-repo/          ← GitHub repository root
├── plugin.yaml            ← runtime manifest (title, description, version, ...)
├── default_config.yaml
├── README.md
├── LICENSE
├── api/
├── tools/
├── extensions/
└── webui/
```

Help the user create this repository and push the plugin files to it.

### 2. Index manifest (different from runtime manifest)

The Plugin Index (`https://github.com/agent0ai/a0-plugins`) uses a **separate, simpler `plugin.yaml`** that only describes discoverability — it is NOT the same as the runtime manifest:

```yaml
title: My Plugin
description: What this plugin does.
github: https://github.com/yourname/your-plugin-repo
tags:
  - tools
  - example
```

Only four fields: `title`, `description`, `github` (required), and `tags` (optional, up to 5). See the recommended tag list at https://github.com/agent0ai/a0-plugins/blob/main/TAGS.md.

### 3. Submission steps

1. Fork `https://github.com/agent0ai/a0-plugins`.
2. Create the folder `plugins/<your-plugin-name>/` in the fork.
3. Add the index `plugin.yaml` inside it (and optionally a square thumbnail ≤ 20 KB named `thumbnail.png`, `thumbnail.jpg`, or `thumbnail.webp`).
4. Open a Pull Request. The PR must add exactly one new plugin folder.
5. CI will validate automatically. A maintainer reviews and merges.

Submission constraints:
- Folder name: unique, stable, lowercase, kebab-case
- Folders starting with `_` are reserved for internal use
- `title` max 50 characters, `description` max 500 characters

Help the user prepare the fork, the index manifest, and draft the PR.

---

## Plugin Index & Marketplace

The **Plugin Index** is the community hub at https://github.com/agent0ai/a0-plugins.

A **Plugin Marketplace** (a built-in always-active plugin) is planned and will allow users to browse, install, and update indexed plugins directly from the Agent Zero UI. When available, this skill will be updated to guide users through marketplace-based installation as well.
