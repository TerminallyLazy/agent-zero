# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

The primary users are Agent Zero developers using structural repository intelligence to understand, modify, and verify code. They work inside Agent Zero against active projects and agent profiles, and need useful coding context without leaving their existing workflow.

## Product Purpose

Agent Zero is an extensible agent framework. The Tree-sitter plugin gives its coding agents and developers a structural view of repositories before edits and fast syntax diagnostics afterward. Success means relevant code context is easier to assemble, structural navigation is dependable, and parser/runtime readiness is truthful and actionable.

## Positioning

The plugin integrates repository-scale Tree-sitter intelligence directly into Agent Zero's tools, project-aware settings, coding prompts, and lifecycle hooks. It combines incremental indexing, structural search, task-context assembly, file inspection, diagnostics, and native-parser validation rather than acting as a standalone syntax viewer.

## Operating Context

Users configure the plugin in Agent Zero's Plugin Settings, scoped globally or by project and agent profile. Coding agents invoke Tree-sitter tools during repository work, while developers can inspect runtime readiness and open the Code Intelligence workbench. The plugin runs in Agent Zero's framework runtime and stores plugin-owned indexes locally.

## Capabilities and Constraints

- Preserve Agent Zero's existing plugin lifecycle, settings scope, dark/light themes, controls, and responsive behavior.
- Keep automatic dependency provisioning and validation in `hooks.py`; do not restore `initialize.py`, `execute.py`, or a manual dependency-install action.
- Keep file inspection project-bound by default and make any outside-project access explicit.
- Distinguish structural references and clean syntax from type resolution, compiler correctness, and behavioral verification.
- Report actual language-pack, parser-cache, and runtime state without implying unavailable capabilities.

## Brand Commitments

Use the names Agent Zero, Tree-sitter, and Code Intelligence consistently. The interface should feel native to Agent Zero rather than like a separate product embedded inside it. Copy should be direct, technical, compact, and free of inflated claims.

## Evidence on Hand

- Runtime and product behavior: `usr/plugins/tree_sitter/README.md`, `plugin.yaml`, `hooks.py`, and `helpers/`.
- Settings and workbench surfaces: `usr/plugins/tree_sitter/webui/config.html` and `tree-sitter-inspector.html`.
- Acceptance screenshot: `/var/folders/lg/1g_6bp_15v7810g7hrrg1d880000gn/T/codex-clipboard-989362e7-ed3c-412d-9897-ff600c3635af.png`.
- Existing Agent Zero theme and component tokens: `webui/index.css` and bundled plugin settings surfaces.
- No testimonials, usage benchmarks, or external product claims are available and none should be fabricated.

## Product Principles

1. Structural intelligence should reduce coding uncertainty, not add interface complexity.
2. Runtime readiness and repository boundaries must remain immediately legible and truthful.
3. Advanced controls should stay compact, scannable, and native to Agent Zero.
4. Automation belongs in lifecycle hooks; the settings UI should explain and configure, not repair installation.
5. Visual polish must support high-frequency operation across dark and light themes.

## Accessibility & Inclusion

Preserve semantic labels, keyboard-operable native controls, visible focus states, sufficient contrast in both themes, and responsive layouts that remain usable at narrow widths and browser zoom.
