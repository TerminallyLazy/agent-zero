# Agent Zero - Plugins Guide

This guide covers the Python Backend and Frontend WebUI plugin architecture. Use this as the definitive reference for building and extending Agent Zero.

---

## 1. Architecture Overview

Agent Zero uses a convention-over-configuration plugin model where runtime capabilities are discovered from the directory structure.

### Internal Components

1. Backend discovery (python/helpers/plugins.py): Resolves roots (usr/plugins/ first, then plugins/) and builds the effective set of plugins.
2. Path resolution (python/helpers/subagents.py): Injects plugin paths into the agent's search space for prompts, tools, and configurations.
3. Python extensions (python/helpers/extension.py): Executes lifecycle hooks from extensions/python/<point>/.
4. WebUI extensions (webui/js/extensions.js): Injects HTML/JS contributions into core UI breakpoints (x-extension).

---

## 2. File Structure

Each plugin lives in usr/plugins/<plugin_name>/.

```text
usr/plugins/<plugin_name>/
├── plugin.yaml                   # Required: Title, version, settings + activation metadata
├── default_config.yaml           # Optional: fallback settings defaults
├── README.md                     # Optional: shown in Plugin List UI
├── LICENSE                       # Optional: shown in Plugin List UI
├── api/                          # API handlers (ApiHandler subclasses)
├── tools/                        # Agent tools (Tool subclasses)
├── helpers/                      # Shared Python logic
├── prompts/                      # Prompt templates
├── agents/                       # Agent profiles (agents/<profile>/agent.yaml)
├── extensions/
│   ├── python/<point>/           # Backend lifecycle hooks
│   └── webui/<point>/            # UI HTML/JS contributions
└── webui/
    ├── config.html               # Optional: Plugin settings UI
    └── ...                       # Full plugin pages/components
```

### plugin.yaml (runtime manifest)

This is the manifest file that lives inside your plugin directory and drives runtime behavior. It is distinct from the index manifest used when publishing to the Plugin Index (see Section 7).

```yaml
title: My Plugin
description: What this plugin does.
version: 1.0.0
settings_sections:
  - agent
per_project_config: false
per_agent_config: false
# Optional: lock plugin permanently ON in UI/back-end
always_enabled: false
```

Field reference:
- `title`: UI display name
- `description`: Short plugin summary
- `version`: Plugin version string
- `settings_sections`: Which Settings tabs show a subsection for this plugin. Valid values: `agent`, `external`, `mcp`, `developer`, `backup`. Use `[]` for no subsection.
- `per_project_config`: Enables project-scoped settings and toggle rules
- `per_agent_config`: Enables agent-profile-scoped settings and toggle rules
- `always_enabled`: Forces ON and disables toggle controls in the UI (reserved for framework use)

---

## 3. Frontend Extensions

### HTML Breakpoints
Core UI defines insertion points like <x-extension id="sidebar-quick-actions-main-start"></x-extension>.
To contribute:
1. Place HTML files in extensions/webui/<extension_point>/.
2. Include a root x-data scope.
3. Include an x-move-* directive (e.g., x-move-to-start, x-move-after="#id").

### JS Hooks
Place *.js files in extensions/webui/<extension_point>/ and export a default async function. They are called via callJsExtensions("<point>", context).

---

## 4. Plugin Settings

1. Add webui/config.html to your plugin.
2. Bind fields to $store.pluginSettings.settings.
3. Settings are scoped per-project and per-agent automatically.

### Resolution Priority (Highest First)
1. project/.a0proj/agents/<profile>/plugins/<name>/config.json
2. project/.a0proj/plugins/<name>/config.json
3. usr/agents/<profile>/plugins/<name>/config.json
4. usr/plugins/<name>/config.json
5. plugins/<name>/default_config.yaml (fallback defaults)

## 5. Plugin Activation Model

- Global and scoped activation are independent, with no inheritance between scopes.
- Activation flags are files: `.toggle-1` (ON) and `.toggle-0` (OFF).
- UI states are `ON`, `OFF`, and `Advanced` (shown when any project/profile-specific override exists).
- `always_enabled: true` in `plugin.yaml` forces ON and disables toggle controls in the UI.
- The "Switch" modal is the canonical per-scope activation surface, and "Configure Plugin" keeps scope synchronized with the settings modal.

---

## 6. Routes

| Route | Purpose |
|---|---|
| GET /plugins/<name>/<path> | Serve static assets |
| POST /api/plugins/<name>/<handler> | Call plugin API |
| POST /api/plugins | Management (actions: get_config, save_config, list_configs, delete_config, toggle_plugin, get_doc) |

---

## 7. Plugin Index & Community Sharing

The **Plugin Index** is a community-maintained repository at https://github.com/agent0ai/a0-plugins that lists plugins available to the Agent Zero community. Plugins listed there can be discovered and installed by other users.

### Two Distinct plugin.yaml Files

There are two completely different `plugin.yaml` schemas used at different stages. They must not be confused:

**Runtime manifest** (inside your plugin repo/directory, drives Agent Zero behavior):
```yaml
title: My Plugin
description: What this plugin does.
version: 1.0.0
settings_sections:
  - agent
per_project_config: false
per_agent_config: false
always_enabled: false
```

**Index manifest** (submitted to the `a0-plugins` repo under `plugins/<your-plugin-name>/`, drives discoverability only):
```yaml
title: My Plugin
description: What this plugin does.
github: https://github.com/yourname/your-plugin-repo
tags:
  - tools
  - example
```

The index manifest contains only four fields (`title`, `description`, `github`, `tags`) and must not include runtime fields. The `github` field must point to the root of a GitHub repository that itself contains a runtime `plugin.yaml` at the repository root.

### Repository Structure for Community Plugins

When creating a plugin intended for the community, the plugin should be a standalone GitHub repository where the plugin directory contents live at the repo root:

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

Users install it locally by cloning (or downloading) the repo contents into `/a0/usr/plugins/<plugin_name>/`.

### Submitting to the Plugin Index

1. Create a GitHub repository for your plugin with the runtime `plugin.yaml` at the repo root.
2. Fork `https://github.com/agent0ai/a0-plugins`.
3. Create a folder `plugins/<your-plugin-name>/` containing only an index `plugin.yaml` (and optionally a square thumbnail image ≤ 20 KB).
4. Open a Pull Request with exactly one new plugin folder.
5. CI validates the submission automatically. A maintainer reviews and merges.

Index submission rules:
- One plugin per PR
- Folder name must be unique, stable, lowercase, kebab-case
- Folders starting with `_` are reserved for internal use
- `github` must point to a public repo that contains `plugin.yaml` at its root
- `title` max 50 characters, `description` max 500 characters
- `tags`: optional, up to 5, use recommended tags from https://github.com/agent0ai/a0-plugins/blob/main/TAGS.md

### Plugin Marketplace (Coming Soon)

A built-in **Plugin Marketplace** plugin (always active) will allow users to browse the Plugin Index and install or update community plugins directly from the Agent Zero UI. This section will be updated once the marketplace plugin is released.

---

*Refer to AGENTS.md for the main framework guide.*
