# Agent Zero Plugins

This directory contains default plugins. For a full-stack development guide, see [docs/AGENTS.md](../docs/AGENTS.md).

> [!TIP]
> While Agent Zero looks for plugins in both `usr/plugins/` and `plugins/`, you should **always develop new plugins in `usr/plugins/`**. This ensures your work is isolated from core system files and persists through framework updates.

## Architecture

Agent Zero uses a convention-over-configuration plugin model:

- Runtime capabilities are discovered from directory structure.
- Backend owns discovery, routing, and static asset serving.
- Frontend uses explicit `x-extension` breakpoints plus the standard `x-component` loader.

### Internal Components

1. **Backend plugin discovery** (`python/helpers/plugins.py`)
   - `get_plugin_roots()` resolves roots in priority order (`usr/plugins` first, then `plugins`).
   - `list_plugins()` builds the effective set (first root wins on ID conflicts).
   - `get_webui_extensions(extension_point, filters)` scans `extensions/webui/<extension_point>/`.

2. **Path resolution** (`python/helpers/subagents.py`)
   - `get_paths(..., include_plugins=True)` includes plugin candidates for prompts/tools.

3. **Python extension runtime** (`python/helpers/extension.py`)
   - `call_extensions(extension_point, agent, **kwargs)` executes extension classes.
   - Searches `python/extensions/<point>/` and `plugins/*/extensions/python/<point>/`.
   - Extension classes derive from `Extension` and implement `async execute()`.

4. **API and static routes** (`run_ui.py`, `python/api/load_webui_extensions.py`)
   - `GET /plugins/<plugin_id>/<path>` serves plugin static assets.
   - Plugin APIs are mounted under `/api/plugins/<plugin_id>/<handler>`.
   - `POST /api/load_webui_extensions` returns extension files for a given extension point.

5. **Frontend WebUI extension runtime** (`webui/js/extensions.js`)
   - HTML flow: discovers `<x-extension>` tags, calls backend API, injects `<x-component>` tags.
   - JS flow: `callJsExtensions("<extension_point>", contextObject)` loads and executes plugin JS modules.
   - Both HTML and JS lookups are cached per extension point.

## File Structure

```text
usr/plugins/
  <plugin_name>/
    plugin.json                   # Required manifest (enables discovery)
    api/                          # API handlers (ApiHandler subclasses)
    tools/                        # Agent tools (Tool subclasses)
    helpers/                      # Shared Python helpers
    prompts/                      # Prompt templates
    agents/                       # Agent profiles
    extensions/
      python/<extension_point>/   # Python lifecycle extensions
      webui/<extension_point>/    # WebUI HTML/JS hook contributions
    webui/
      config.html                 # Optional: plugin settings UI
      ...                         # Full plugin-owned UI pages/components
```

## Directory Conventions

Each plugin lives in `usr/plugins/<plugin_name>/`.

Capability discovery is based on these paths:

- `plugin.json` - **required** manifest; a directory without it is not recognized as a plugin
- `api/*.py` - API handlers (`ApiHandler` subclasses), exposed under `/api/plugins/<plugin_name>/<handler>`
- `tools/*.py` - agent tools (`Tool` subclasses)
- `helpers/*.py` - shared Python helpers
- `extensions/python/<extension_point>/*.py` - backend lifecycle extensions
- `extensions/webui/<extension_point>/*` - WebUI extension assets (HTML/JS)
- `webui/**` - full plugin-owned UI pages/components (loaded directly by path)
- `webui/config.html` - if present, a Settings button appears for this plugin in the relevant settings tabs
- `prompts/**/*.md` - prompt templates
- `agents/` - agent profiles

### `plugin.json` format

```json
{
  "name": "My Plugin",
  "description": "What this plugin does.",
  "version": "1.0.0",
  "settings_sections": ["agent"]
}
```

`settings_sections` controls which Settings tabs show a subsection for this plugin. Current valid values: `agent`, `external`, `mcp`, `developer`, `backup`. Leave empty (`[]`) for no subsection.

## Frontend Extensions

### HTML insertion via breakpoints

Core UI defines insertion points like:

```html
<x-extension id="sidebar-quick-actions-main-start"></x-extension>
```

Resolution flow:

1. `webui/js/extensions.js` finds `x-extension` nodes.
2. It calls `/api/load_webui_extensions` with the extension point and HTML filters.
3. Backend returns matching files from `plugins/*/extensions/webui/<extension_point>/`.
4. `extensions.js` injects returned entries as `<x-component path="...">`.
5. `components.js` loads each component using the standard component pipeline.

Required baseline for HTML UI extensions in this repository:
- include a root `x-data` scope
- include one explicit `x-move-*` placement directive

### JS hook extensions

JS hooks are loaded from the same extension point structure:

`plugins/<plugin_id>/extensions/webui/<extension_point>/*.js`

Runtime code calls:

`callJsExtensions("<extension_point>", contextObject)`

### Fine placement helpers

`initFw.js` provides Alpine move directives for plugin markup:

- `x-move-to-start`
- `x-move-to-end`
- `x-move-to`
- `x-move-before`
- `x-move-after`

## Plugin Settings

If your plugin needs user-configurable settings:

1. Add `webui/config.html` to your plugin. The system detects this file automatically.
2. Declare which settings tabs should show a subsection for your plugin via `settings_sections` in `plugin.json`.
3. The plugin settings modal provides **Project** and **Agent profile** context selectors (same as the Skills list). Settings are scoped per-project and per-agent.

### Config HTML contract

Your `config.html` receives context from `$store.pluginSettings`:

```html
<html>
<head>
  <title>My Plugin Config</title>
  <script type="module">
    import { store } from "/components/plugins/plugin-settings-store.js";
  </script>
</head>
<body>
  <div x-data>
    <!-- bind fields to $store.pluginSettings.settings -->
    <input x-model="$store.pluginSettings.settings.my_key" />
  </div>
</body>
</html>
```

- `$store.pluginSettings.settings` - plain object loaded from `config.json`, save-scoped to the selected project/agent.
- The modal's **Save** button calls `POST /plugins` (`action: save_config`) automatically.
- For plugins that surface **core settings** (like memory), set `saveMode = 'core'` in `x-init` so Save delegates to the core settings API instead.

### Settings resolution priority (highest first)

```
project/.a0proj/agents/<profile>/plugins/<name>/config.json
project/.a0proj/plugins/<name>/config.json
usr/agents/<profile>/plugins/<name>/config.json
agents/<profile>/plugins/<name>/config.json
usr/plugins/<name>/config.json
plugins/<name>/config.json
```

## Plugin Author Flow

1. Create `usr/plugins/<plugin_name>/`.
2. Add `plugin.json` manifest (required for discovery).
3. Add backend capabilities by convention (`api/`, `tools/`, `helpers/`, `extensions/python/`, `prompts/`, `agents/`).
4. Pick a WebUI breakpoint or JS hook extension point.
5. For HTML UI entries: place files under `extensions/webui/<extension_point>/`, use root `x-data` + one `x-move-*` directive.
6. For JS hooks: place `*.js` files under `extensions/webui/<extension_point>/`, export a default async function.
7. Place full plugin pages/components in `webui/` and open them directly by path.
8. Optionally add `webui/config.html` and set `settings_sections` in `plugin.json` to expose settings in the UI.

## Routes

- Plugin static assets: `GET /plugins/<plugin_name>/<path>`
- Plugin APIs: `POST /api/plugins/<plugin_name>/<handler>`
- WebUI extension discovery: `POST /api/load_webui_extensions`
- Plugin management (get/save config): `POST /plugins`

## Notes

- User plugins in `usr/plugins/` override repo plugins by plugin ID.
- Runtime behavior is fully convention-driven from directory structure.
- Extension point ordering between multiple plugins is currently implicit (filesystem order).
- When you need a new extension point for your plugin, submit a PR - we are actively expanding coverage based on community needs.
