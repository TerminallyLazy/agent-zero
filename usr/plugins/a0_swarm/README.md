# A0 Swarm

Spawn parallel subagents and monitor / message them from a sidebar panel.

See `docs/superpowers/specs/2026-05-14-a0-swarm-design.md` for the design spec
and `docs/superpowers/plans/2026-05-14-a0-swarm.md` for the implementation plan.

## Tools

- `delegate_parallel(tasks=[{label, task, profile?}, ...])` — runs subagents
  concurrently, each in its own isolated `AgentContext`. Returns a markdown
  summary once all complete.
- `swarm_message(recipient, content, is_blocker?)` — message a peer swarm
  agent or the orchestrator; optionally mark sender as BLOCKED.

## UI

Mounts at `sidebar-bottom-wrapper-end`. Live updates over the existing
`WsWebui` socket. Per-agent: status icon, current activity, blocker chip,
message thread, Message / Send & Unblock / Cancel actions, plus a Clear
Completed button.

## API

| Endpoint | Method | Body | Returns |
|---|---|---|---|
| `/api/swarm_status` | POST | `{parent_context_id?}` | `{agents: SwarmAgent[]}` |
| `/api/swarm_send_message` | POST | `{agent_name, content, unblock?}` | `{ok}` |
| `/api/swarm_cancel` | POST | `{agent_name}` | `{ok}` |
| `/api/swarm_clear_completed` | POST | `{parent_context_id?}` | `{ok}` |

## Tests

```bash
pytest tests/test_a0_swarm_registry.py tests/test_a0_swarm_delegate.py \
       tests/test_a0_swarm_message_tool.py tests/test_a0_swarm_api.py \
       tests/test_a0_swarm_extensions.py -v
```

## Source location

`usr/` is gitignored by default; this plugin's source is force-tracked for
in-repo development. End-user installs clone into their own `usr/plugins/`.
