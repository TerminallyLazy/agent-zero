# Agent Zero - Core Plugins

This directory contains the system-level plugins for Agent Zero.

## Directory Structure

- plugins/: Core system plugins (reserved for framework updates).
- usr/plugins/: Recommended location for user-developed plugins.

## Documentation

For detailed guides on how to create, extend, or configure plugins, please refer to:

- AGENTS.plugins.md: Full-stack plugin architecture, manifest format, and extension points.
- AGENTS.md: Main framework guide and backend context overview.

## Usage

Plugins are automatically discovered based on the presence of a plugin.json file. Each plugin can contribute:
- Backend: APIs, Tools, Helpers, and Lifecycle Extensions.
- Frontend: HTML/JS UI contributions via core breakpoints.
- Config: Isolated settings scoped per-project and per-agent profile.
