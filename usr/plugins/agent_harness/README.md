# Agent Harness

`agent_harness` turns Agent Zero into a coding-first, DeerFlow-inspired implementation harness.

It adds explicit run modes, checkpointed risky actions, thread-scoped workspace data, memory curation, task-graph orchestration, and a DeerFlow-like core bridge over Agent Zero's existing runtime.

## What This Plugin Is

Agent Harness is the closest DeerFlow-style coding harness that fits naturally inside Agent Zero's plugin architecture.

It is designed for:

- deep implementation tasks that benefit from an explicit run lifecycle
- safer autonomous coding with checkpoints before risky actions
- project rule curation instead of silent memory writes
- thread-local uploads, outputs, and scratch workspace data
- structured orchestration for larger coding tasks
- exposing DeerFlow-like backend state without replacing Agent Zero itself

## What This Plugin Is Not

This plugin is not a literal port of the full DeerFlow backend.

Today it does not ship:

- a standalone LangGraph server
- a separate DeerFlow gateway service
- DeerFlow's channel app layer
- DeerFlow's full sandbox/provider stack

Instead, it brings DeerFlow's coding-harness ideas into Agent Zero by using Agent Zero's own plugin hooks, API handlers, tools, and UI.

## Main Capabilities

- DeerFlow-aligned coding modes: `flash`, `standard`, `pro`, `ultra`
- explicit run state with objective, phase, risk level, failures, verification, and task tracking
- guarded execution with approval checkpoints for risky actions
- manual and queued memory curation for reusable repo rules
- DeerFlow-style thread data roots for `workspace`, `uploads`, and `outputs`
- optional multi-step task-graph orchestration with parallel subagent dispatch in `ultra`
- a DeerFlow-like core facade for thread state, configured models, available skills, and memory status
- dashboard UI for current run, task graph, pending checkpoints, memory queue, and recent accepted rules

## Quick Start

1. Enable the plugin in Agent Zero.

   This plugin is not `always_enabled`, so it must be turned on through Agent Zero's plugin controls. It supports global, per-project, and per-agent configuration.

2. Open the Agent Harness UI.

   The plugin provides:

   - a dashboard for active run state and review queues
   - a status strip above the chat input when `show_status_ui` is enabled
   - a sidebar entry for quick access

3. Start a run.

   For most coding tasks, start in `pro`.

   Use `ultra` when the work is large enough to benefit from decomposition and parallel subagents.

4. Work in chat as usual.

   The harness injects workflow instructions into the runtime and tracks the run as the agent moves through inspect, plan, implementation, verification, and completion.

5. Review checkpoints and memory proposals.

   Risky actions will pause behind a checkpoint. Reusable rules are captured into a review queue instead of being silently persisted.

6. Verify and complete.

   The harness expects tests or other verification to be recorded before a run is completed.

## Recommended Mode Selection

| Mode | Best For | Planning | Subagents | Default Policy |
| --- | --- | --- | --- | --- |
| `flash` | small, low-risk coding tasks | usually skipped | disabled | `subagent_limit=0`, `repair_limit=0` |
| `standard` | moderate single-agent work | optional | disabled | `subagent_limit=0`, `repair_limit=1` |
| `pro` | most serious coding work | recommended for multi-step tasks | disabled | `subagent_limit=0`, `repair_limit=1` |
| `ultra` | larger, multi-file, decomposable work | required before multi-file execution | enabled | `subagent_limit=3`, `repair_limit=3` |

Migration note:

- legacy stored values such as `assist`, `build`, and `surge` are normalized to the new DeerFlow-style modes so older saved settings do not break existing chats

## Run Lifecycle

Each harness run tracks a concrete coding workflow:

1. `inspect`
2. `plan`
3. `implement`
4. `verify`
5. `repair`
6. `summarize`
7. `complete`

The practical behavior depends on mode:

- `flash` favors the shortest safe path
- `standard` keeps the work thoughtful but single-agent
- `pro` encourages deliberate inspect -> plan -> implement -> verify work
- `ultra` expects task decomposition and supports dispatch/collect loops for parallel work

When a task graph exists, the harness tracks:

- pending sub-tasks
- dispatched sub-tasks
- completed sub-tasks
- failed sub-tasks

The dashboard renders both a Mermaid graph and a text fallback view of the graph.

## Safety Model

Agent Harness adds review checkpoints before risky behavior.

By default, checkpoints are required for:

- dependency installation commands
- destructive shell commands
- edits to protected files or folders

Default protected paths:

- `agent.py`
- `initialize.py`
- `usr/plugins/`

The guardrail matcher treats folder-style entries such as `usr/plugins/` as directory prefixes, so nested files under that path are protected too.

The plugin also exposes a manual checkpoint tool so the agent can request approval proactively when the action is risky even if it is not caught by a pattern.

## Memory Curation

Instead of silently persisting every reusable observation, the harness can queue memory proposals for review.

Each proposal includes:

- the candidate rule text
- a reason
- source metadata
- a target scope

Supported scopes:

- `project`
- `agent`
- `global`

Accepted rules are surfaced back into future harness prompts as accepted project rules.

## Thread Data Layout

When workspace support is enabled, the plugin prepares DeerFlow-style thread data directories for each chat context.

If the chat is attached to a project, the data is rooted under that project.

If the chat is not attached to a project, the data is rooted under the chat storage folder.

Layout:

```text
.harness/
  threads/
    <context_id>/
      user-data/
        workspace/
        uploads/
        outputs/
  offloads/
  runs/
```

Meaning:

- `workspace/`: thread-local scratch space for implementation work
- `uploads/`: files uploaded into the thread
- `outputs/`: generated artifacts for the thread
- `offloads/`: auxiliary markdown offloads
- `runs/`: saved run logs

Project-backed workspaces also ensure the project's `.gitignore` includes:

- `.harness/workspace/`
- `.harness/offloads/`
- `.harness/threads/`

## User Interface

The plugin includes several user-facing surfaces:

### Dashboard

The dashboard shows:

- current run objective, mode, phase, status, and risk level
- tracked tasks
- task graph progress
- pending checkpoints
- pending memory proposals
- recent accepted rules
- the latest verification result

### Status Strip

When enabled, the plugin can display a compact harness status strip above the chat input so the current run remains visible without opening the full dashboard.

### Sidebar Entry

The plugin also registers sidebar/status entrypoints so the harness can be reached from the existing Agent Zero UI shell.

## Tooling Inside the Agent Loop

The plugin exposes three primary tools inside Agent Zero.

### `harness_run`

This is the main orchestration tool.

Supported actions:

- `start`: begin a run with a mode, objective, and optional constraints
- `status`: summarize the current run
- `phase`: move the run to a new phase
- `plan`: submit a task graph for decomposed work
- `dispatch`: spawn ready sub-tasks in parallel
- `collect`: collect completed sub-task results and update the graph
- `task`: upsert tracked task items
- `verification`: record a verification result
- `failure`: record a bounded failure or repair loop
- `clean`: clear workspace/offloads while preserving outputs and run logs
- `complete`: finish the run after verification and task completion

### `harness_checkpoint`

This tool creates a manual review checkpoint with:

- a reason
- a proposed action
- optional tool metadata
- risk level

Use it when the action is risky and should pause for approval even if the guardrail layer has not blocked it automatically.

### `harness_memory_propose`

This tool submits candidate reusable rules into the memory review queue.

Use it when the agent learns a durable repo convention that should be reviewed before being persisted.

If `memory_curation_enabled` is turned off, proposed rules are accepted immediately instead of being queued.

## Runtime Wiring

The plugin uses Agent Zero lifecycle extensions to keep the harness active throughout a run.

Important runtime hooks:

- `extensions/python/tool_execute_before/_20_harness_guardrails.py`
  Blocks risky execution and opens checkpoints.
- `extensions/python/tool_execute_after/_20_harness_tool_events.py`
  Tracks tool activity and sub-task outcomes.
- `extensions/python/message_loop_prompts_after/_20_harness_runtime.py`
  Injects harness instructions into the active prompt.
- `extensions/python/chat_model_call_after/_20_harness_cost.py`
  Tracks token usage and budget information.
- `extensions/python/monologue_start/_20_harness_workspace.py`
  Prepares thread-scoped workspace roots before work begins.

## DeerFlow-Like Core Bridge

The plugin exposes DeerFlow-style host state through a local facade.

Core bridge helpers:

- `helpers/deerflow_core.py`
- `helpers/deerflow_client.py`
- `helpers/workspace.py`

The bridge currently surfaces:

- thread path summary
- configured models
- available skills
- memory status
- thread uploads
- thread artifacts

This is intended to make Agent Zero feel more like DeerFlow at the harness boundary, even though the underlying runtime is still Agent Zero.

## Plugin APIs

All plugin API routes live under `/plugins/agent_harness/`.

| Endpoint | Purpose |
| --- | --- |
| `run` | start, inspect current run state, stop a run, and submit checkpoint decisions |
| `state` | dashboard state, pending checkpoints, memory queue, recent rules, latest verification |
| `memory_queue` | accept or reject queued memory proposals |
| `deerflow_core` | DeerFlow-like thread, model, skill, and memory summary |
| `thread_data` | inspect thread data roots or clean them up |
| `thread_uploads` | list, upload, or delete thread-local uploads |
| `thread_artifacts` | list generated artifacts or download a specific artifact |

Behavior notes:

- `run` is what the dashboard uses for `start`, `checkpoint_decide`, and `stop`
- `state` is the dashboard polling endpoint
- `thread_uploads` accepts `GET` and `POST` and supports `action=upload` and `action=delete`
- `thread_artifacts` supports listing artifacts and downloading a requested file via `GET`
- `thread_data` supports `action=status` and `action=cleanup`

## Settings

The plugin ships a default config in `default_config.yaml` and supports both per-project and per-agent overrides.

| Setting | Default | Meaning |
| --- | --- | --- |
| `ambient_assist_enabled` | `true` | keep lightweight coding guidance active even without an explicit run |
| `default_deep_mode` | `pro` | default mode when starting a deep harness workflow |
| `memory_curation_enabled` | `true` | queue reusable rules for review instead of silently persisting them |
| `show_status_ui` | `true` | display the compact harness status strip |
| `max_auto_edit_files` | `8` | cap on automatic broad edit fan-out before the task should slow down |
| `dependency_install_requires_checkpoint` | `true` | require approval before install commands |
| `destructive_actions_require_checkpoint` | `true` | require approval before destructive commands |
| `protected_paths` | see config | files and directory prefixes that always require approval before editing |
| `mode_policies` | varies by mode | subagent and repair-loop policy per mode |
| `context_pressure_threshold` | `0.7` | threshold used to classify context pressure |
| `context_model_window` | `128000` | assumed context window for pressure calculations |
| `workspace_enabled` | `true` | create DeerFlow-style thread workspace roots |
| `token_budget` | `0` | optional hard budget for usage tracking; `0` means disabled |
| `cost_tracking_enabled` | `true` | track prompt/completion token usage during runs |

Current default mode policies:

- `flash`: `subagent_limit=0`, `repair_limit=0`
- `standard`: `subagent_limit=0`, `repair_limit=1`
- `pro`: `subagent_limit=0`, `repair_limit=1`
- `ultra`: `subagent_limit=3`, `repair_limit=3`

## Included DeerFlow Compatibility Assets

The plugin includes local DeerFlow-style assets so it is usable without copying files out of the upstream DeerFlow repository.

Included assets:

- `Install.md`
- `scripts/check_deerflow_harness.py`
- `scripts/import_deerflow_public_skills.py`
- `skills/public/bootstrap`
- `skills/public/find-skills`

Use these when you want to:

- verify that the plugin has all expected DeerFlow-style assets
- compare local plugin state against a DeerFlow checkout
- import DeerFlow public skills into Agent Zero

## Verification

Basic parity and plugin checks:

```bash
./.venv/bin/python usr/plugins/agent_harness/scripts/check_deerflow_harness.py
./.venv/bin/pytest -q tests/test_agent_harness_plugin.py tests/test_harness_*.py
```

Verify against a local DeerFlow checkout:

```bash
./.venv/bin/python usr/plugins/agent_harness/scripts/check_deerflow_harness.py --source /path/to/deer-flow
```

Optional DeerFlow public skill import:

```bash
./.venv/bin/python usr/plugins/agent_harness/scripts/import_deerflow_public_skills.py --source /path/to/deer-flow
```

## Recommended Usage Pattern

For most users, this flow works well:

1. Enable the plugin for the current project or agent.
2. Start a `pro` run for normal coding work.
3. Switch to `ultra` only when the task is large enough to justify decomposition.
4. Let checkpoints slow you down before risky actions instead of bypassing them.
5. Review memory proposals so durable project rules stay clean and intentional.
6. Treat `outputs/` as the canonical place for thread-local generated artifacts.
7. Run verification before completing the harness run.

## Troubleshooting

### The dashboard is empty

Make sure the plugin is enabled for the current scope and that the current chat context exists.

### I do not see a run

No run exists until one is started. The dashboard can still load, but run-specific controls will remain idle until `start` is called.

### The harness keeps blocking an action

Check the pending checkpoint queue. The block may be caused by:

- a dependency installation command
- a destructive command
- a protected path edit

### Uploads or artifacts are missing

Remember that uploads and outputs are thread-scoped, not global. A different chat context will have a different thread data root.

### I want full DeerFlow backend parity

This plugin gets close at the harness layer, but full parity would require Agent Zero core work beyond the plugin boundary, especially around LangGraph-style execution and a separate gateway/runtime service.

## File Guide

If you are extending the plugin itself, these are the most important files:

- `plugin.yaml`
- `default_config.yaml`
- `api/run.py`
- `api/state.py`
- `api/memory_queue.py`
- `api/deerflow_core.py`
- `api/thread_data.py`
- `api/thread_uploads.py`
- `api/thread_artifacts.py`
- `tools/harness_run.py`
- `tools/harness_checkpoint.py`
- `tools/harness_memory_propose.py`
- `helpers/deerflow_core.py`
- `helpers/deerflow_client.py`
- `helpers/workspace.py`
- `webui/dashboard.html`
- `webui/config.html`
- `webui/harness-store.js`

## Related Docs

- `Install.md`
- `docs/plans/2026-04-01-deerflow-core-parity-design.md`

If you want the design rationale behind the DeerFlow parity bridge, read the design doc. If you want the operational bootstrap and verification path, read `Install.md`.
