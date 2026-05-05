# Spike 0.5: A0 `x-extension` breakpoint for jcode `SidePanel*` events

**Date:** 2026-05-05
**Spec ref:** §5.8, §11
**A0 webui revision:** current branch `jcode-harness`
**jcode crate:** `jcode-side-panel-types` (lib.rs, 93 lines)
**Status:** Resolved

## A0 right-canvas surface system

A0 already has a **right-canvas** system that supersedes a single side-panel. It's a unified
surface area with multiple "surfaces" (each with its own tab + panel content), driven by
`$store.rightCanvas` (`webui/components/canvas/right-canvas-store.js`).

Available `x-extension` breakpoints (verified from
`webui/components/canvas/right-canvas.html`):

| Breakpoint | Purpose |
|---|---|
| `right-canvas-shell-start` / `-end` | Wrap the entire canvas shell |
| `right-canvas-tabs-start` / `-end` | Inject custom tabs into the tab strip |
| `right-canvas-toolbar-start` / `-end` | Add toolbar buttons (e.g., refresh, undock) |
| `right-canvas-panels` | Inject panel content area |
| `right-canvas-empty-state` | Override empty state |

Surfaces register with `$store.rightCanvas` declaring `{id, title, icon (or image), undockable}`
and get a tab + panel automatically. Surface activation calls `open(surfaceId)`.

## jcode SidePanel data model

From `jcode/crates/jcode-side-panel-types/src/lib.rs`:

```rust
pub struct SidePanelSnapshot {
    pub focused_page_id: Option<String>,
    pub pages: Vec<SidePanelPage>,
}
pub struct SidePanelPage {
    pub id: String,
    pub title: String,
    pub file_path: String,
    pub format: SidePanelPageFormat,  // currently only Markdown
    pub source: SidePanelPageSource,  // Managed | LinkedFile | Ephemeral
    pub content: String,
    pub updated_at_ms: u64,
}
```

The `History` event from `jcode-protocol` carries an optional `side_panel: SidePanelSnapshot`
on subscribe, and updates flow as `ServerEvent::SidePanel` (variant name to confirm in Spike 0.1
or via fixture capture).

## Mapping (chosen)

**One A0 surface, one tab per jcode page.** The plugin registers a single right-canvas surface
named "jcode" and renders jcode's pages as **internal tabs** within that surface's panel
component (mirroring the way A0's own surfaces work). Reasoning:

- jcode pages are dynamic (created/destroyed per session); injecting each as a top-level
  right-canvas surface would clutter A0's tab strip.
- jcode's own `focused_page_id` semantics are scoped to its set; leaking that state into
  A0's whole rightCanvas store creates conflicts.
- A surface-with-internal-tabs lets the plugin own the inner state machine and respond to
  `ServerEvent::SidePanel` updates without touching A0's store.

## Implementation sketch

```javascript
// usr/plugins/jcode_harness/extensions/webui/right-canvas-tabs-start/jcode_surface.js
export default async function () {
  if (!window.$store?.rightCanvas) return;
  $store.rightCanvas.registerSurface({
    id: "jcode",
    title: "jcode",
    icon: "psychology",   // Material Symbols name
    undockable: true,
    panelComponent: "jcode-panel",   // Alpine component name
  });
}
```

```html
<!-- usr/plugins/jcode_harness/extensions/webui/right-canvas-panels/jcode_panel.html -->
<template x-if="$store.rightCanvas.isSurfaceActive('jcode')">
  <div x-data="jcodePanel()" x-init="init()">
    <div class="jcode-tabstrip">
      <template x-for="page in pages" :key="page.id">
        <button :class="{active: page.id === focusedId}"
                @click="focusedId = page.id"
                x-text="page.title"></button>
      </template>
    </div>
    <div class="jcode-page-content"
         x-html="renderMarkdown(currentPage()?.content || '')"></div>
  </div>
</template>
```

`jcodePanel()` Alpine component subscribes to plugin's IPC event stream and updates
`pages`/`focusedId` from `ServerEvent::SidePanel` snapshots.

## Plan impact

Update plan Chunk 9 (WebUI):

- Replace `extensions/webui/side-panel-start/` with two breakpoints:
  - `right-canvas-tabs-start/jcode_surface.js` — registers the surface
  - `right-canvas-panels/jcode_panel.html` + `.js` — renders the panel content
- File-structure tree at plan top must update.
- Task 9.3 description reframes from "side-panel-start extension" to "right-canvas surface
  registration + panel".

## Verification still needed (folded into integration phase)

- Confirm exact `ServerEvent` variant name for SidePanel updates (capture fixture)
- Confirm `$store.rightCanvas.registerSurface` API exists or look up actual API in
  `webui/components/canvas/right-canvas-store.js`
- Verify Material Symbols `psychology` icon renders (or pick alternative)
