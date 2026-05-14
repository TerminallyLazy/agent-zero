# a0_swarm — Parallel Subagent Swarm Plugin: Design Spec

**Plugin slug:** `a0_swarm`
**Install path:** `usr/plugins/a0_swarm/`
**Python import root:** `usr.plugins.a0_swarm`
**Target version:** 1.0.0

This document is the validated design for the `a0_swarm` plugin. It supersedes
`A0-Swarm.md` where the two disagree; the prior document was a draft that
referenced several framework APIs that do not exist as written. Every framework
integration point below has been verified against the current Agent Zero
codebase.

---

## 1. Purpose

Enable an Agent Zero orchestrator to delegate independent subtasks to multiple
subagents running in parallel, each in its own isolated `AgentContext`, and
monitor and message them live from the Web UI sidebar.

The plugin does not modify the existing `call_subordinate` tool. Sequential
subordinate dispatch and shared-context subordinates remain unchanged.

---

## 2. Architecture

```
┌────────────────────────────────────────────────────────────────┐
│                Agent Zero (Orchestrator, agent 0)               │
│  ┌──────────────────────┐    ┌─────────────────────────────┐   │
│  │ delegate_parallel    │    │ swarm_message               │   │
│  └─────────┬────────────┘    └──────────────┬──────────────┘   │
└────────────┼─────────────────────────────────┼──────────────────┘
             │ asyncio.gather                  │ AgentContext.communicate
             ▼                                 ▼
   ┌──────────────────────┐         ┌──────────────────────┐
   │  Isolated subagents  │◀────────│  helpers/registry.py │
   │  (own AgentContext)  │ writes  │   (singleton, RLock) │
   └──────────────────────┘         └──────────┬───────────┘
                                               │ notify
                ┌──────────────────────────────┼───────────────┐
                ▼                              ▼               ▼
    extensions/python/         api/*.py (ApiHandler)   webui_ws_event
    {monologue_start,           swarm_status            extension hook on
     tool_execute_before,       swarm_send_message      WsWebui → emit_to
     message_loop_start}        swarm_cancel            "swarm_push" → sids
                                swarm_clear_completed
                                               │
                                               ▼
                              webui Alpine store + swarm-panel.html
                              mounted at sidebar-bottom-wrapper-end
```

### Module boundaries

| Module | Responsibility | Imports |
|---|---|---|
| `helpers/registry.py` | Threadsafe in-memory state, subscribers, snapshot | stdlib only |
| `tools/delegate_parallel.py` | Spawn isolated `AgentContext`s, run `monologue()` per agent via `asyncio.gather`, return summary | `agent`, `helpers.tool`, `initialize`, registry |
| `tools/swarm_message.py` | Record message, inject into target via `context.communicate(UserMessage)` | `agent`, `helpers.tool`, registry |
| `api/*.py` | HTTP endpoints; thin translators registry ↔ JSON | `helpers.api`, registry, `agent` |
| `extensions/python/<point>/*` | Lifecycle activity tracking, WS subscribe/push, cleanup | `helpers.extension`, registry |
| `webui/*` | Alpine store + panel HTML + CSS, mounted by `extensions/webui/sidebar-bottom-wrapper-end/...` | none (browser only) |

The registry imports no framework modules. Tools and API handlers depend on
registry but not vice versa. The push extension is the only module that bridges
registry → WebSocket transport.

---

## 3. Data Model — `helpers/registry.py`

```python
class SwarmAgentStatus(str, Enum):
    PENDING = "pending"
    WORKING = "working"
    BLOCKED = "blocked"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"

@dataclass
class SwarmMessage:
    sender: str       # agent_name or "orchestrator"
    recipient: str    # agent_name or "orchestrator"
    content: str
    timestamp: str    # ISO 8601, UTC
    read: bool = False

@dataclass
class SwarmAgent:
    agent_name: str          # "SA{parent_num}_{i}" — unique
    label: str               # human label set at delegation
    task: str                # full task text
    context_id: str          # isolated AgentContext.id
    parent_context_id: str   # orchestrator's AgentContext.id
    status: SwarmAgentStatus
    current_activity: str = ""
    blocker: str = ""
    result: str = ""
    messages: list[SwarmMessage] = field(default_factory=list)
    started_at: str          # ISO 8601, UTC
    finished_at: str = ""
```

### `SwarmRegistry` (thread-safe singleton)

```
SwarmRegistry.get() → singleton

State:
    _agents: dict[str, SwarmAgent]
    _rlock: threading.RLock
    _subscribers: list[tuple[asyncio.AbstractEventLoop, Callable]]

Methods:
    register(agent)
    update_status(name, status, **fields)
    update_activity(name, text)
    add_message(SwarmMessage)
    get_agent(name) -> SwarmAgent | None
    get_agent_by_context(ctx_id) -> SwarmAgent | None
    agents_for_parent(parent_ctx_id) -> list[SwarmAgent]
    snapshot(parent_ctx_id: str | None = None) -> list[dict]
    remove(name)
    clear_completed(parent_ctx_id: str | None = None)
    clear_for_parent(parent_ctx_id: str)
    add_subscriber(loop, cb)
    remove_subscriber(cb)
    _notify()  # internal — scheduled via run_coroutine_threadsafe
```

### Key choices versus prior draft

1. **`parent_context_id` field added** so each browser tab sees only swarms
   launched from its own orchestrator context. `snapshot()` and WS push payloads
   filter by it.

2. **Subscribers are `(loop, callback)` tuples.** Registry mutations may occur
   on any thread (asyncio worker, tool thread). On subscribe the WS extension
   captures `asyncio.get_running_loop()` and stores it alongside the callback.
   `_notify()` does `asyncio.run_coroutine_threadsafe(cb(), loop)` per
   subscriber. Prior draft used `asyncio.get_event_loop()` in arbitrary threads,
   which is brittle and deprecated.

3. **`clear_completed`** added for the user-chosen "no cap, manual clear"
   flow. Removes only DONE / FAILED / CANCELLED rows for a parent context.

4. **`clear_for_parent`** added so the framework can free memory when the
   orchestrator's context is disposed.

5. **`_notify()` snapshots the subscriber list inside the lock**, then iterates
   *outside* the lock. Never holds the lock across `run_coroutine_threadsafe`.

---

## 4. Tools

### 4.1 `delegate_parallel` — `tools/delegate_parallel.py`

```python
class DelegateParallel(Tool):
    async def execute(self, tasks: list | None = None, **kwargs):
        if not tasks:
            return Response("No tasks provided to delegate_parallel.",
                            break_loop=False)

        if len(tasks) > 16:
            # console-warn, do not block (user chose no cap)
            log.warning(...)

        registry = SwarmRegistry.get()
        parent_ctx_id = self.agent.context.id
        coros, entries = [], []

        for i, td in enumerate(tasks):
            label  = td.get("label", f"Agent-{i+1}")
            text   = td.get("task", "")
            profile = td.get("profile", "")

            config = initialize_agent()
            if profile: config.profile = profile

            sub_ctx = AgentContext(config=config)            # isolated
            sub_ag  = sub_ctx.agent0
            sub_ag.agent_name = f"SA{self.agent.number+1}_{i+1}"

            entry = SwarmAgent(
                agent_name=sub_ag.agent_name, label=label, task=text,
                context_id=sub_ctx.id, parent_context_id=parent_ctx_id,
                status=SwarmAgentStatus.PENDING,
                started_at=utc_iso_now(),
            )
            registry.register(entry)
            entries.append(entry)
            coros.append(self._run_subagent(sub_ctx, sub_ag, text, entry))

        results = await asyncio.gather(*coros, return_exceptions=True)

        # build markdown summary; one section per entry
        return Response(message=summary, break_loop=False)

    async def _run_subagent(self, sub_ctx, sub_ag, text, entry) -> str:
        reg = SwarmRegistry.get()
        reg.update_status(entry.agent_name, SwarmAgentStatus.WORKING)
        try:
            sub_ag.hist_add_user_message(UserMessage(message=text))
            result = await sub_ag.monologue()
            # honour pre-set CANCELLED (set by cancel endpoint before kill)
            cur = reg.get_agent(entry.agent_name)
            if cur and cur.status != SwarmAgentStatus.CANCELLED:
                reg.update_status(entry.agent_name, SwarmAgentStatus.DONE,
                                  result=result or "", current_activity="")
            return result or ""
        except Exception as e:
            cur = reg.get_agent(entry.agent_name)
            if cur and cur.status != SwarmAgentStatus.CANCELLED:
                reg.update_status(entry.agent_name, SwarmAgentStatus.FAILED,
                                  blocker=str(e), current_activity="")
            raise
        finally:
            AgentContext.remove(sub_ctx.id)
```

Verified APIs:
- `AgentContext(config=config)` — `agent.py:42-97`.
- `sub_ctx.agent0` — `agent.py:91-93`.
- `AgentContext.remove(id)` — exists in the repo.
- `sub_ag.monologue()` — async, the agent's main loop.
- `sub_ag.hist_add_user_message(UserMessage(message=...))` — same call shape
  used by `tools/call_subordinate.py`.
- `Tool`, `Response` — `helpers.tool`.

`get_log_object()` mirrors `call_subordinate`'s implementation and prints
`icon://group_work {agent_name}: Delegating Parallel Tasks` with `kvps=self.args`.

### 4.2 `swarm_message` — `tools/swarm_message.py`

```python
class SwarmMessageTool(Tool):
    async def execute(self, recipient="orchestrator", content="",
                      is_blocker=False, **kwargs):
        reg = SwarmRegistry.get()
        sender_entry = reg.get_agent_by_context(self.agent.context.id)
        sender_name  = sender_entry.agent_name if sender_entry else self.agent.agent_name

        msg = SwarmMessage(sender=sender_name, recipient=recipient,
                           content=content, timestamp=utc_iso_now())
        reg.add_message(msg)

        if is_blocker and sender_entry:
            reg.update_status(sender_name, SwarmAgentStatus.BLOCKED,
                              blocker=content)

        if recipient != "orchestrator":
            target = reg.get_agent(recipient)
            if target:
                ctx = AgentContext.get(target.context_id)
                if ctx:
                    ctx.communicate(UserMessage(
                        message=f"[Message from {sender_name}]: {content}"))

        return Response(f"Message sent to {recipient}.", break_loop=False)
```

Verified: `AgentContext.communicate(UserMessage, broadcast_level=1)` exists at
`agent.py:251`.

---

## 5. Extensions (Python)

All hook into existing extension points; no fictional surfaces.

### 5.1 Activity tracking

```
extensions/python/monologue_start/_10_swarm_activity.py
    class SwarmActivityOnMonologueStart(Extension):
        async def execute(self, loop_data=None, **kwargs):
            entry = SwarmRegistry.get().get_agent_by_context(
                self.agent.context.id)
            if entry:
                SwarmRegistry.get().update_activity(
                    entry.agent_name, "Thinking...")
```

```
extensions/python/tool_execute_before/_10_swarm_tool_track.py
    class SwarmToolTrack(Extension):
        async def execute(self, tool_name="", tool_args=None, **kwargs):
            entry = SwarmRegistry.get().get_agent_by_context(
                self.agent.context.id)
            if entry:
                SwarmRegistry.get().update_activity(
                    entry.agent_name, f"Using tool: {tool_name}")
```

```
extensions/python/message_loop_start/_10_swarm_unblock.py
    class SwarmUnblockOnResume(Extension):
        async def execute(self, loop_data=None, **kwargs):
            reg = SwarmRegistry.get()
            entry = reg.get_agent_by_context(self.agent.context.id)
            if entry and entry.status == SwarmAgentStatus.BLOCKED:
                reg.update_status(entry.agent_name, SwarmAgentStatus.WORKING,
                                  blocker="")
```

All three early-return if the current agent is not a swarm member — pure no-op
for non-swarm agents.

### 5.2 WebSocket subscribe / push

The plugin does not register a new `WsHandler`. Instead it hooks the existing
`WsWebui` handler via the `webui_ws_event` extension (verified in
`api/ws_webui.py`).

```
extensions/python/webui_ws_event/_10_swarm_ws.py

    _subs: dict[str, tuple[loop, parent_ctx_id, cb]] = {}

    class SwarmWsEvent(Extension):
        async def execute(self, instance, sid, event_type, data,
                          response_data, **kwargs):
            if event_type == "swarm_subscribe":
                parent = data.get("parent_context_id", "")
                loop   = asyncio.get_running_loop()

                async def push_cb():
                    snap = SwarmRegistry.get().snapshot(parent_ctx_id=parent)
                    try:
                        await instance.emit_to(sid, "swarm_push",
                                               {"agents": snap})
                    except Exception:
                        pass

                _subs[sid] = (loop, parent, push_cb)
                SwarmRegistry.get().add_subscriber(loop, push_cb)
                response_data["agents"] = SwarmRegistry.get().snapshot(
                    parent_ctx_id=parent)

            elif event_type == "swarm_unsubscribe":
                entry = _subs.pop(sid, None)
                if entry:
                    SwarmRegistry.get().remove_subscriber(entry[2])
                response_data["ok"] = True
```

```
extensions/python/webui_ws_disconnect/_10_swarm_cleanup.py
    class SwarmWsCleanup(Extension):
        async def execute(self, instance, sid, **kwargs):
            entry = _subs.pop(sid, None)
            if entry:
                SwarmRegistry.get().remove_subscriber(entry[2])
```

Verified: `WsHandler.emit_to(sid, event, payload)` at
`helpers/ws_manager.py:1201`.

### 5.3 Parent-context cleanup (optional)

```
extensions/python/process_chain_end/_10_swarm_cleanup_parent.py
    on chain end → if registry has no ACTIVE swarms for this parent_ctx,
    leave history alone (user may still want to view results).
    Hard-clear only on AgentContext disposal — wire via context_remove
    extension if available; otherwise relies on `clear_completed` button.
```

---

## 6. API Handlers

All inherit `ApiHandler` from `helpers.api` and use the real signature
`async def process(self, input: dict, request: Request) -> dict | Response`
(verified at `helpers/api.py:32` and `api/api_message.py:27`). Auto-discovered
from `usr/plugins/a0_swarm/api/`.

### 6.1 `api/swarm_status.py`

```python
class SwarmStatus(ApiHandler):
    async def process(self, input, request):
        parent = (input or {}).get("parent_context_id") or ""
        return {"agents": SwarmRegistry.get().snapshot(parent_ctx_id=parent or None)}
```

### 6.2 `api/swarm_send_message.py`

```python
class SwarmSendMessage(ApiHandler):
    async def process(self, input, request):
        agent_name = (input or {}).get("agent_name", "")
        content    = (input or {}).get("content", "")
        unblock    = bool((input or {}).get("unblock", False))
        if not agent_name or not content:
            return Response(...400 error...)
        reg   = SwarmRegistry.get()
        entry = reg.get_agent(agent_name)
        if not entry:
            return Response(...404 error...)
        reg.add_message(SwarmMessage(sender="orchestrator",
                                     recipient=agent_name, content=content,
                                     timestamp=utc_iso_now()))
        if unblock and entry.status == SwarmAgentStatus.BLOCKED:
            reg.update_status(agent_name, SwarmAgentStatus.WORKING, blocker="")
        ctx = AgentContext.get(entry.context_id)
        if ctx:
            ctx.communicate(UserMessage(
                message=f"[Orchestrator]: {content}"))
        return {"ok": True}
```

### 6.3 `api/swarm_cancel.py`

```python
class SwarmCancel(ApiHandler):
    async def process(self, input, request):
        agent_name = (input or {}).get("agent_name", "")
        if not agent_name:
            return Response(...400...)
        reg   = SwarmRegistry.get()
        entry = reg.get_agent(agent_name)
        if not entry:
            return Response(...404...)
        # set CANCELLED *before* killing so _run_subagent doesn't overwrite
        reg.update_status(agent_name, SwarmAgentStatus.CANCELLED,
                          current_activity="")
        ctx = AgentContext.get(entry.context_id)
        if ctx:
            ctx.kill_process()
        return {"ok": True}
```

Verified: `AgentContext.kill_process()` at `agent.py:224`.

### 6.4 `api/swarm_clear_completed.py`

```python
class SwarmClearCompleted(ApiHandler):
    async def process(self, input, request):
        parent = (input or {}).get("parent_context_id") or None
        SwarmRegistry.get().clear_completed(parent_ctx_id=parent)
        return {"ok": True}
```

### 6.5 `hooks.py`

```python
def install():
    pass    # no install steps

def pre_update():
    pass    # no pre-update steps
```

No `register_routes` / `register_ws_handlers`. The framework auto-discovers
handlers from `api/`.

---

## 7. Frontend

### 7.1 Mount point

```
extensions/webui/sidebar-bottom-wrapper-end/_10_swarm_panel.html
```

Contains exactly:

```html
<x-component src="/plugins/a0_swarm/webui/swarm-panel.html"></x-component>
```

Static asset route `GET /plugins/<name>/<path>` is documented in the framework
plugins guide.

### 7.2 `webui/swarm-store.js`

Alpine store created via `createStore("swarmStore", proto)` from
`/js/AlpineStore.js`.

State:
- `agents: []`
- `panelOpen: true`
- `composingFor: null`
- `composeText: ""`

Behaviour:
- `init()` calls `_subscribeWs()` and `_loadInitial()`.
- `_subscribeWs()` uses the existing socket. The actual accessor is determined
  during implementation by inspecting `webui/js/websocket.js`; candidates are
  `Alpine.store("syncStore").socket` or a singleton exported from
  `websocket.js`. If neither exists, fall back to polling
  `/api/swarm_status` every 1500 ms while panel is open.
- `_loadInitial()` fetches `/api/swarm_status` once with the current
  `parent_context_id` (read from the syncStore / chat store).
- `sendMessage`, `cancelAgent`, `clearCompleted` use plain `fetch` with the
  framework's existing CSRF mechanism (header name discovered during
  implementation by inspecting `webui/js/api.js`).

Getters: `activeAgents`, `completedAgents`, `hasAgents`.
Helpers: `statusIcon`, `statusClass`, `unreadCount`, `relativeTime`,
`markRead`, `openCompose`, `closeCompose`, `togglePanel`.

### 7.3 `webui/swarm-panel.html`

Alpine component:
- Collapsible header with agent count badge.
- Active section: card per agent with status icon, label, name, current
  activity (pulsing), blocker chip, message thread, Message / Cancel buttons.
- Compose box appears under a card when `composingFor === agent.agent_name`:
  Send, Send & Unblock (when blocked), Cancel.
- Completed section: dimmed cards with finished_at, truncated result preview,
  and a "Clear Completed" button at the section header.

### 7.4 `webui/swarm-panel.css`

CSS uses existing theme variables (`--bg-secondary`, `--border-color`,
`--text-primary`, `--text-secondary`, `--text-muted`, `--accent`). Status colours
left-border accents:

| Status | Colour |
|---|---|
| working | `#4a9eff` |
| blocked | `#f59e0b` |
| done    | `#22c55e` |
| failed  | `#ef4444` |
| pending | `#6b7280` |
| cancelled | `#374151` |

---

## 8. Manifest — `plugin.yaml`

```yaml
name: a0_swarm
title: A0 Swarm
description: Spawn parallel subagents with a real-time monitoring panel.
version: 1.0.0
settings_sections: []
per_project_config: false
per_agent_config: false
always_enabled: false
```

---

## 9. Prompts

Both prompt files from the prior draft are kept verbatim:
- `prompts/tool.delegate_parallel.md`
- `prompts/tool.swarm_message.md`

Filename pattern `tool.*.md` is the existing convention for tool descriptions.

---

## 10. Error Handling & Lifecycle

| Event | Handling |
|---|---|
| Subagent raises | `_run_subagent` marks FAILED (unless pre-set CANCELLED), context removed in `finally`, exception captured by `asyncio.gather(return_exceptions=True)` |
| User clicks Cancel | API sets status=CANCELLED → calls `kill_process()` → `_run_subagent` exception handler skips status update because status is already CANCELLED |
| User unblocks via send | API: `add_message` + status=WORKING + `context.communicate(...)` |
| Subagent sets is_blocker | `swarm_message` tool: `add_message` + status=BLOCKED |
| WS client disconnects | `webui_ws_disconnect` extension drops sid + removes subscriber |
| Registry mutation | RLock acquired only for the data update; `_notify()` copies subscriber list inside the lock and iterates outside it |
| Parent context disposed | `clear_for_parent(parent_ctx_id)` releases memory (wired if framework exposes a context-disposal hook; otherwise relies on the manual "Clear Completed" button) |

---

## 11. Testing

**Unit (pytest):**
- `helpers/registry.py`
  - register / update_status / update_activity / add_message round-trip.
  - snapshot filtering by `parent_context_id`.
  - `clear_completed` removes only terminal-status rows.
  - Concurrency: `threading.Thread` × 20 mutating; assert no `RuntimeError`,
    final snapshot consistent.
  - `add_subscriber` / `remove_subscriber`: callback invoked on mutation,
    not invoked after removal.

- `tools/delegate_parallel.py`
  - Patch `Agent.monologue` to return a canned string; assert N entries
    transition PENDING → WORKING → DONE, each gets its own context_id,
    `AgentContext.remove` is called for each.
  - Patch `Agent.monologue` to raise; assert FAILED + blocker text.
  - Mixed success / failure: `gather` returns mixed; summary contains both
    DONE and FAILED sections.

- `tools/swarm_message.py`
  - `is_blocker=True` flips sender to BLOCKED.
  - Non-orchestrator recipient: `AgentContext.communicate` called with
    `[Message from …]:` prefix.

**Integration (manual):**
- Load Agent Zero locally, enable `a0_swarm`.
- Run `delegate_parallel` with two trivial tasks; observe two cards spawn,
  status flips, results appear, "Completed" section populated.
- Use `swarm_message` from a subagent with `is_blocker=true` to orchestrator;
  observe blocker chip; click Send & Unblock from the UI; subagent receives
  intervention message and resumes.
- Click Cancel on a running subagent; status → CANCELLED, process killed,
  summary marks it cancelled.
- Click Clear Completed; only terminal rows disappear.

---

## 12. Non-Goals (out of scope for v1.0.0)

- Persistence to disk / DB across process restarts.
- Cross-process or distributed swarms (single Agent Zero process only).
- Plugin Settings UI (`settings_sections: []`).
- Per-project or per-agent config (`per_*_config: false`).
- Plugin Index submission / community publish (handled separately).
- Automatic concurrency cap (user accepted no cap; warn-log above 16).

---

## 13. Verified vs Unverified Integration Points

**Verified against current codebase:**
- `AgentContext(config=config)` (`agent.py:42`).
- `AgentContext.agent0` (`agent.py:91`).
- `AgentContext.remove(id)`.
- `AgentContext.get(id)`.
- `AgentContext.communicate(UserMessage)` (`agent.py:251`).
- `AgentContext.kill_process()` (`agent.py:224`).
- `Agent.monologue()` (async).
- `Agent.hist_add_user_message(UserMessage)` (`tools/call_subordinate.py:31`).
- `helpers.tool.Tool`, `Response`.
- `helpers.api.ApiHandler` with `process(self, input, request)` signature
  (`helpers/api.py:32`, `api/api_message.py:27`).
- `helpers.extension.Extension`.
- `helpers.ws.WsHandler.emit_to` (`helpers/ws_manager.py:1201`).
- `api/ws_webui.py` exposes `webui_ws_event`, `webui_ws_connect`,
  `webui_ws_disconnect` extension dispatch.
- `x-extension id="sidebar-bottom-wrapper-end"` exists in
  `webui/components/sidebar/bottom/sidebar-bottom.html`.
- Plugin api/ and extensions/python/ folders are auto-discovered.

**Discovered during implementation (low risk):**
- Exact socket accessor name in `webui/js/websocket.js`.
- Exact CSRF header convention used by `webui/js/api.js`.
- Whether an `AgentContext` disposal hook exists for parent-cleanup wiring;
  fallback is the Clear Completed button.

---

## 14. File Tree

```
usr/plugins/a0_swarm/
├── plugin.yaml
├── hooks.py
├── helpers/
│   └── registry.py
├── tools/
│   ├── delegate_parallel.py
│   └── swarm_message.py
├── api/
│   ├── swarm_status.py
│   ├── swarm_send_message.py
│   ├── swarm_cancel.py
│   └── swarm_clear_completed.py
├── extensions/
│   ├── python/
│   │   ├── monologue_start/_10_swarm_activity.py
│   │   ├── tool_execute_before/_10_swarm_tool_track.py
│   │   ├── message_loop_start/_10_swarm_unblock.py
│   │   ├── webui_ws_event/_10_swarm_ws.py
│   │   └── webui_ws_disconnect/_10_swarm_cleanup.py
│   └── webui/
│       └── sidebar-bottom-wrapper-end/
│           └── _10_swarm_panel.html
├── prompts/
│   ├── tool.delegate_parallel.md
│   └── tool.swarm_message.md
└── webui/
    ├── swarm-store.js
    ├── swarm-panel.html
    └── swarm-panel.css
```
