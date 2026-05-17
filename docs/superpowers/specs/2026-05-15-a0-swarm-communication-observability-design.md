# a0_swarm Communication and Observability Enhancement: Design Spec

**Plugin slug:** `a0_swarm`
**Install path:** `usr/plugins/a0_swarm/`
**Python import root:** `usr.plugins.a0_swarm`
**Build target:** enhance the existing `a0_swarm` plugin on branch `swarm_enhance`
**Related spec:** `docs/superpowers/specs/2026-05-14-a0-swarm-design.md`

This spec extends the existing `a0_swarm` plugin. The current plugin can spawn
parallel local subagents, enlist remote Agent Zero instances through FastA2A,
and render a right-canvas observability panel. The next increment makes swarm
communication durable, scoped, observable, and reliable across local and remote
agents.

No mockups are part of this design. The implementation should ship working
plugin behavior, tests, and operator-facing setup surfaces.

---

## 1. Goals

1. Fix message delivery so a message accepted by the orchestrator is not
   silently lost.
2. Support subagent-to-subagent messaging inside the same swarm run.
3. Let subagents autonomously message the orchestrator.
4. Make delivery state visible: queued, delivered, failed, and read.
5. Improve the right-canvas panel so operators can see runs, agents, messages,
   activity, blockers, remote location, and setup health.
6. Make additional remote Agent Zero containers simple to configure and verify,
   with same-host Docker discovery as the guided path and A2A URLs as the
   universal fallback.

---

## 2. Non-Goals

1. Do not replace `call_subordinate`.
2. Do not move `a0_swarm` out of `usr/plugins/a0_swarm/`.
3. Do not edit core Agent Zero behavior unless an existing plugin extension
   point cannot safely support the required behavior.
4. Do not require all remote A0 containers to be on the same Docker host.
5. Do not imply remote continuation is supported when the remote A2A endpoint
   rejects or cannot resume a context.

---

## 3. Architecture

The enhancement centers on a first-class swarm run and message ledger.

Each `delegate_parallel` call creates a `SwarmRun` id. Every local or remote
agent registered by that call belongs to the run. Peer messaging is scoped by
`run_id`, which prevents one swarm from messaging stale agents in another
swarm even when agent names are reused across parent contexts.

Messages are records, not fire-and-forget side effects. A message is accepted
into the ledger first, then delivered by an adapter:

| Adapter | Target | Delivery behavior |
|---|---|---|
| Local adapter | Local `AgentContext` | Inject with `AgentContext.communicate(...)` when running or idle/resumable; fail only when the context is gone or non-resumable. |
| Remote A2A adapter | Remote A0 context | Continue the stored remote context id when supported; mark failed with the exact reason when unsupported or unreachable. |
| Orchestrator adapter | Parent context | Record immediately for the panel; no hidden UI success state. |

The existing registry remains the in-process source of truth, but its model
expands from "agents with embedded messages" to "runs, agents, messages, and
timeline events." HTTP APIs and WebSocket push continue to be thin translators
over registry snapshots.

---

## 4. Data Model

### `SwarmRun`

```python
@dataclass
class SwarmRun:
    run_id: str
    parent_context_id: str
    parent_agent_name: str
    status: SwarmRunStatus
    started_at: str
    finished_at: str = ""
    title: str = ""
```

`SwarmRunStatus` values: `active`, `done`, `failed`, `cancelled`.

Run status is derived from member agents unless explicitly cancelled.

### `SwarmAgent`

Extend `SwarmAgentStatus` with `IDLE = "idle"`. `idle` means the agent has an
existing context and can receive queued work, but is not currently inside an
active processing task.

Add these fields to the existing `SwarmAgent`:

```python
run_id: str
delivery_mode: str = "local"      # "local" or "remote_a2a"
last_seen_at: str = ""
last_error: str = ""
```

The existing remote fields remain:

```python
remote_label: str = ""
remote_base_url: str = ""
remote_task_id: str = ""
```

### `SwarmMessage`

Replace the embedded message shape with a ledger-oriented shape:

```python
@dataclass
class SwarmMessage:
    message_id: str
    run_id: str
    sender: str              # agent_name or "orchestrator"
    recipient: str           # agent_name or "orchestrator"
    content: str
    delivery_state: str      # "queued", "delivered", "failed"
    read: bool = False
    created_at: str = ""
    delivered_at: str = ""
    failed_at: str = ""
    failure_reason: str = ""
```

`read` is UI state only. It does not replace delivery state.

### `SwarmTimelineEvent`

Timeline events are lightweight records used by the panel:

```python
@dataclass
class SwarmTimelineEvent:
    event_id: str
    run_id: str
    agent_name: str
    kind: str       # "activity", "message", "status", "blocker", "result", "delivery"
    text: str
    created_at: str
    ref_id: str = ""
```

Message events should reference `message_id` through `ref_id`.

---

## 5. Registry Contract

`SwarmRegistry` gains run and ledger methods while preserving the current
thread-safety discipline:

```python
create_run(parent_context_id, parent_agent_name, title="") -> SwarmRun
register_agent(agent)
create_message(run_id, sender, recipient, content) -> SwarmMessage
mark_message_delivered(message_id)
mark_message_failed(message_id, reason)
queued_messages_for_agent(agent_name) -> list[SwarmMessage]
messages_for_run(run_id) -> list[SwarmMessage]
events_for_run(run_id) -> list[SwarmTimelineEvent]
snapshot(parent_ctx_id=None) -> dict
```

Required invariants:

1. All mutations use registry methods. Callers do not directly mutate agent,
   run, message, or event fields.
2. Terminal agent status remains absorbing: `done`, `failed`, and `cancelled`
   cannot be overwritten by late writes.
3. Message acceptance and message delivery are separate operations.
4. A peer recipient must exist in the same `run_id`.
5. Cross-run peer messages are rejected before ledger creation.
6. Unknown recipients are rejected before ledger creation.
7. Subscriber callbacks are still invoked outside the registry lock.
8. `snapshot()` returns deep-converted dicts with no shared mutable state.

Snapshot shape should group by run so the UI does not need to reconstruct
relationships from flat agent lists:

```json
{
  "runs": [
    {
      "run_id": "...",
      "status": "active",
      "agents": [],
      "messages": [],
      "timeline": []
    }
  ]
}
```

For compatibility during rollout, API handlers may also expose the current
top-level `agents` list until the panel store is fully migrated.

---

## 6. Message Delivery Flow

### Orchestrator to Agent

1. UI calls `swarm_send_message` with `agent_name`, `content`, and optional
   `unblock`.
2. Handler resolves the agent and its `run_id`.
3. Registry creates a message with `delivery_state="queued"`.
4. Delivery service attempts adapter delivery.
5. Registry marks the message `delivered` or `failed`.
6. If `unblock` is true and the target is blocked, target status changes to
   `working` only after the message is accepted into the ledger.

### Agent to Orchestrator

1. Subagent calls `swarm_message(recipient="orchestrator", content=...)`.
2. Tool resolves sender by `AgentContext.id`.
3. Registry creates and immediately marks the message delivered to the
   orchestrator inbox.
4. If `is_blocker=true`, the sender status becomes `blocked` and a blocker
   timeline event is appended.

### Agent to Agent

1. Subagent calls `swarm_message(recipient="<peer agent_name>", content=...)`.
2. Tool resolves sender by `AgentContext.id`.
3. Registry verifies sender and recipient share the same `run_id`.
4. Registry creates a queued message.
5. Delivery service attempts delivery to the peer.
6. The sender receives a tool response that includes the message id and the
   resulting delivery state.

### Queued Local Delivery

When a local target has a context but is between turns, the agent status is
`idle` and the message remains queued and visible. The delivery service retries
at safe lifecycle points:

1. Before a local subagent starts work.
2. When a local subagent is resumed with `AgentContext.communicate(...)`.
3. When a lifecycle extension observes the target context becoming runnable.

Queued delivery must be idempotent. A message that is already delivered or
failed is never delivered again.

### Remote A2A Delivery

Remote delivery uses the stored remote endpoint and remote context id.

1. If `remote_base_url` or remote context id is missing, mark failed.
2. If the remote endpoint is unreachable or auth fails, mark failed with the
   connection/auth reason.
3. If the remote accepts the continuation/intervention, mark delivered.
4. If the remote starts a new task instead of continuing the context, keep the
   message state honest by marking failed unless the response proves the same
   context was used.

---

## 7. UI Behavior

The right-canvas panel becomes an operational swarm view.

It shows:

1. Active runs grouped by `run_id`.
2. Per-run counts: working, blocked, queued messages, failed deliveries, done.
3. Per-agent origin: local or remote endpoint label.
4. Per-agent execution state: pending, working, blocked, idle, done, failed,
   cancelled.
5. Per-agent last activity and last error.
6. A combined timeline of activity, status changes, blocker changes, messages,
   delivery changes, results, retries, and cancellation.
7. Message delivery badges: queued, delivered, failed.
8. Actions: message, send and unblock, retry delivery, retry agent, cancel,
   clear completed.

The key UI rule is that "sent" never means "delivered." After submit, a message
appears as `queued`. It changes to `delivered` only after the adapter confirms
handoff. If delivery fails, the message row shows the failure reason inline.

No marketing-style or decorative mockup work is required. The panel should use
the existing right-canvas and plugin UI conventions.

---

## 8. Remote Container Setup

Remote setup lives in Plugin Settings.

### Same-host Docker guided path

When Docker access is available, the plugin should detect likely sibling A0
containers and present them as candidates. A candidate is valid only after a
test verifies:

1. Network reachability.
2. Agent card retrieval.
3. Authentication.
4. A2A task submission.
5. A2A continuation/intervention support.
6. Cancel support when available.

The plugin must not permanently modify Docker, host networking, GPU runtime, or
remote containers without explicit operator action. It may provide exact
commands and diagnostics.

### URL fallback

Operators can always add explicit A2A remotes with:

1. Label.
2. Base A2A URL.
3. Auth token.
4. Optional project segment/name.

Each remote row gets a test action and a copyable `endpoint` value for
`delegate_parallel`.

---

## 9. API Changes

Existing endpoints remain, but response payloads expand.

| Endpoint | Purpose |
|---|---|
| `swarm_status` | Return grouped runs, agents, messages, timeline, remote health summary. |
| `swarm_send_message` | Create ledger message and attempt delivery. |
| `swarm_cancel` | Cancel local context or remote task; append timeline event. |
| `swarm_clear_completed` | Clear terminal runs/agents for a parent context. |
| `swarm_retry_message` | Retry a failed or queued message. |
| `swarm_retry_agent` | Re-run a failed/cancelled agent task in the same run lineage. |
| `swarm_test_remote` | Validate one configured or proposed A2A remote. |
| `swarm_discover_docker` | Return same-host Docker A0 candidates when Docker is available. |

APIs return structured errors with `ok: false`, `error`, and when relevant
`message_id`, `agent_name`, or `remote_label`.

---

## 10. Tool Prompt Changes

`agent.system.tool.swarm_message.md` must explain:

1. Use `recipient="orchestrator"` for status, blockers, and questions for the
   parent agent.
2. Use a peer agent name only for agents in the same swarm run.
3. A successful tool call means the message was accepted into the ledger; the
   response includes delivery state.
4. Use `is_blocker=true` only when the sender cannot proceed without help.

`agent.system.tool.delegate_parallel.md` must explain:

1. Optional `endpoint` routes a task to a configured remote.
2. Local and remote agents can message peers and the orchestrator during the
   run.
3. Labels should be meaningful because the panel uses them for observability.

---

## 11. Error Handling

1. Unknown recipient: reject before ledger write.
2. Cross-run peer message: reject before ledger write with "recipient is not in
   this swarm run."
3. Target idle but resumable: keep message queued.
4. Target gone and not resumable: mark failed.
5. Remote auth or connectivity failure: mark failed with the reason.
6. Remote continuation unsupported: keep agent result/status unchanged and mark
   only that message failed.
7. Cancel race: preserve terminal-state absorbing and append a timeline event.
8. Registry subscriber failure: log at debug/warning level and keep the registry
   mutation.

---

## 12. Testing

Add focused tests for:

1. Run creation and agent scoping.
2. Message lifecycle: queued, delivered, failed, read.
3. Orchestrator-to-agent local delivery.
4. Agent-to-orchestrator delivery and blocker status.
5. Agent-to-agent delivery inside one run.
6. Cross-run message rejection.
7. Queued local delivery, then delivery on resume.
8. Remote A2A happy path.
9. Remote auth/connectivity/continuation failure paths.
10. API payload shape for grouped runs, message state, and timeline.
11. Remote test endpoint output.
12. Existing delegation, cancellation, result truncation, and WebSocket fallback
    behavior.

Verification should include the existing focused suite:

```bash
pytest tests/test_a0_swarm_registry.py tests/test_a0_swarm_delegate.py \
       tests/test_a0_swarm_message_tool.py tests/test_a0_swarm_api.py \
       tests/test_a0_swarm_extensions.py -v
```

New tests should be added to those files or new `tests/test_a0_swarm_*.py`
files, depending on scope.

---

## 13. Implementation Order

1. Extend registry models with runs, message ledger, and timeline events.
2. Add delivery service and adapters for local, orchestrator, and remote A2A.
3. Update `delegate_parallel` to create runs and register agents under run ids.
4. Update `swarm_message` and `swarm_send_message` to use the ledger.
5. Add queued-message retry at lifecycle points.
6. Expand status APIs and WebSocket snapshots.
7. Update the right-canvas panel for grouped runs and delivery states.
8. Add remote setup diagnostics and Docker discovery.
9. Update README and tool prompts.
10. Run focused tests and a plugin discovery/loadability check.

---

## 14. Acceptance Criteria

1. UI-originated messages no longer disappear silently.
2. A message visibly moves from queued to delivered or failed.
3. Subagents can message the orchestrator.
4. Subagents can message peers in the same run.
5. Cross-run peer messaging is rejected.
6. Idle-but-resumable local targets keep messages queued until delivery is
   possible.
7. Remote delivery reports auth/connectivity/continuation failures accurately.
8. The panel shows run grouping, agent origin, activity, delivery state, and
   timeline events.
9. Plugin Settings can test configured remotes and same-host Docker candidates.
10. Existing `a0_swarm` delegation and cancellation behavior remains covered by
    tests.
