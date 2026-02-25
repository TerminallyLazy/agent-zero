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
├── plugin.json                   # Required: Name, version, settings config
├── api/                          # API handlers (ApiHandler subclasses)
├── tools/                        # Agent tools (Tool subclasses)
├── helpers/                      # Shared Python logic
├── prompts/                      # Prompt templates
├── agents/                       # Agent profiles
├── extensions/
│   ├── python/<point>/           # Backend lifecycle hooks
│   └── webui/<point>/            # UI HTML/JS contributions
└── webui/
    ├── config.html               # Optional: Plugin settings UI
    └── ...                       # Full plugin pages/components
```

### plugin.json format
```json
{
  "name": "My Plugin",
  "description": "What this plugin does.",
  "version": "1.0.0",
  "settings_sections": ["agent"]
}
```
settings_sections values: agent, external, mcp, developer, backup.

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

---

## 5. Routes

| Route | Purpose |
|---|---|
| GET /plugins/<name>/<path> | Serve static assets |
| POST /api/plugins/<name>/<handler> | Call plugin API |
| POST /api/plugins | Management (action: get_config, save_config) |

---

*Refer to AGENTS.md for the main framework guide.*
