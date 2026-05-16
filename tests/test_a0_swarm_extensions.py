import json
import sys, types, asyncio
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if "agent" not in sys.modules:
    _agent_stub = types.ModuleType("agent")
    _agent_stub.AgentContext = MagicMock()
    _agent_stub.UserMessage = lambda message=None, **kw: {"message": message}
    sys.modules["agent"] = _agent_stub

# Stub helpers.extension before importing the plugin extensions
if "helpers.extension" not in sys.modules:
    _ext_stub = types.ModuleType("helpers.extension")

    class _Extension:
        def __init__(self, agent=None, **kwargs):
            self.agent = agent

    _ext_stub.Extension = _Extension
    sys.modules["helpers.extension"] = _ext_stub

import pytest
from usr.plugins.a0_swarm.helpers.registry import (
    SwarmRegistry, SwarmAgent, SwarmAgentStatus,
)


@pytest.fixture(autouse=True)
def fresh_registry():
    SwarmRegistry._instance = None
    yield
    SwarmRegistry._instance = None


def _register_swarm_agent(name="SA1_1", ctx="ctx-1",
                          status=SwarmAgentStatus.WORKING, **kw):
    SwarmRegistry.get().register(SwarmAgent(
        agent_name=name, label="x", task="t",
        context_id=ctx, parent_context_id="P",
        status=status, started_at="t",
        **{k: v for k, v in kw.items() if k in {"blocker", "result"}},
    ))


# ---- monologue_start ------------------------------------------------------

@pytest.mark.asyncio
async def test_monologue_start_updates_activity_for_swarm_agent():
    from usr.plugins.a0_swarm.extensions.python.monologue_start._10_swarm_activity import (
        SwarmActivityOnMonologueStart,
    )
    _register_swarm_agent()
    agent = MagicMock(); agent.context.id = "ctx-1"
    ext = SwarmActivityOnMonologueStart(agent=agent)
    await ext.execute()
    assert SwarmRegistry.get().get_agent("SA1_1").current_activity == "Thinking..."


@pytest.mark.asyncio
async def test_monologue_start_is_noop_for_non_swarm_agent():
    from usr.plugins.a0_swarm.extensions.python.monologue_start._10_swarm_activity import (
        SwarmActivityOnMonologueStart,
    )
    agent = MagicMock(); agent.context.id = "unknown-ctx"
    ext = SwarmActivityOnMonologueStart(agent=agent)
    await ext.execute()  # must not raise


# ---- tool_execute_before --------------------------------------------------

@pytest.mark.asyncio
async def test_tool_execute_before_updates_activity():
    from usr.plugins.a0_swarm.extensions.python.tool_execute_before._10_swarm_tool_track import (
        SwarmToolTrack,
    )
    _register_swarm_agent()
    agent = MagicMock(); agent.context.id = "ctx-1"
    ext = SwarmToolTrack(agent=agent)
    await ext.execute(tool_name="web_search", tool_args={})
    assert SwarmRegistry.get().get_agent("SA1_1").current_activity == "Using tool: web_search"


# ---- message_loop_start ---------------------------------------------------

@pytest.mark.asyncio
async def test_message_loop_start_clears_blocker():
    from usr.plugins.a0_swarm.extensions.python.message_loop_start._10_swarm_unblock import (
        SwarmUnblockOnResume,
    )
    _register_swarm_agent(status=SwarmAgentStatus.BLOCKED, blocker="stuck")
    agent = MagicMock(); agent.context.id = "ctx-1"
    ext = SwarmUnblockOnResume(agent=agent)
    await ext.execute()
    a = SwarmRegistry.get().get_agent("SA1_1")
    assert a.status == SwarmAgentStatus.WORKING
    assert a.blocker == ""


# ---- webui_ws_event -------------------------------------------------------

@pytest.mark.asyncio
async def test_swarm_subscribe_returns_snapshot_and_registers_subscriber():
    from usr.plugins.a0_swarm.extensions.python.webui_ws_event._10_swarm_ws import (
        SwarmWsEvent, _subs,
    )
    _subs.clear()
    SwarmRegistry._instance = None  # ensure fresh
    _register_swarm_agent("SA1_1", ctx="c1")
    SwarmRegistry.get().register(SwarmAgent(
        agent_name="SA2_1", label="x", task="t",
        context_id="c2", parent_context_id="P2",
        status=SwarmAgentStatus.WORKING, started_at="t",
    ))

    instance = MagicMock()
    instance.emit_to = AsyncMock()
    response_data = {}

    ext = SwarmWsEvent(agent=None)
    await ext.execute(
        instance=instance, sid="sid-1",
        event_type="swarm_subscribe",
        data={"parent_context_id": "P"},
        response_data=response_data,
    )

    assert isinstance(response_data["agents"], list)
    assert isinstance(json.loads(json.dumps(response_data))["agents"], list)
    assert len(response_data["agents"]) == 1
    assert response_data["agents"][0]["agent_name"] == "SA1_1"
    assert "runs" in response_data
    assert "sid-1" in _subs

    SwarmRegistry.get().update_activity("SA1_1", "Pushing...")
    await asyncio.sleep(0.05)
    instance.emit_to.assert_awaited()
    payload = instance.emit_to.await_args.args[2]
    assert isinstance(payload["agents"], list)
    assert isinstance(json.loads(json.dumps(payload))["agents"], list)
    assert "runs" in payload


@pytest.mark.asyncio
async def test_swarm_unsubscribe_removes_subscriber():
    from usr.plugins.a0_swarm.extensions.python.webui_ws_event._10_swarm_ws import (
        SwarmWsEvent, _subs,
    )
    _subs.clear()
    ext = SwarmWsEvent(agent=None)
    instance = MagicMock(); instance.emit_to = AsyncMock()
    response_data = {}
    await ext.execute(instance=instance, sid="sid-1",
                      event_type="swarm_subscribe",
                      data={"parent_context_id": "P"}, response_data=response_data)
    assert "sid-1" in _subs
    response_data2 = {}
    await ext.execute(instance=instance, sid="sid-1",
                      event_type="swarm_unsubscribe",
                      data={}, response_data=response_data2)
    assert "sid-1" not in _subs
    assert response_data2 == {"ok": True}


@pytest.mark.asyncio
async def test_swarm_ws_disconnect_cleans_up():
    from usr.plugins.a0_swarm.extensions.python.webui_ws_event._10_swarm_ws import (
        SwarmWsEvent, _subs,
    )
    from usr.plugins.a0_swarm.extensions.python.webui_ws_disconnect._10_swarm_cleanup import (
        SwarmWsCleanup,
    )
    _subs.clear()
    ext_sub = SwarmWsEvent(agent=None)
    instance = MagicMock(); instance.emit_to = AsyncMock()
    await ext_sub.execute(instance=instance, sid="sid-1",
                          event_type="swarm_subscribe",
                          data={"parent_context_id": "P"}, response_data={})
    ext_dc = SwarmWsCleanup(agent=None)
    await ext_dc.execute(instance=instance, sid="sid-1")
    assert "sid-1" not in _subs


@pytest.mark.asyncio
async def test_swarm_ws_push_cb_evicts_when_instance_garbage_collected():
    """If the WsWebui instance is GC'd, push_cb removes itself from the registry."""
    from usr.plugins.a0_swarm.extensions.python.webui_ws_event._10_swarm_ws import (
        SwarmWsEvent, _subs,
    )
    import gc

    _subs.clear()
    SwarmRegistry._instance = None

    # Plain class so weakref works (MagicMock supports weakref but rebinding to
    # None below is unambiguous when using a real object).
    class _FakeWsInstance:
        async def emit_to(self, sid, event, payload):
            pass

    instance = _FakeWsInstance()
    ext = SwarmWsEvent(agent=None)
    await ext.execute(instance=instance, sid="sid-1",
                      event_type="swarm_subscribe",
                      data={"parent_context_id": "P"}, response_data={})

    assert "sid-1" in _subs
    cb = _subs["sid-1"][2]
    assert len(SwarmRegistry.get()._subscribers) == 1

    # Drop the only strong reference to the WsWebui instance
    del instance
    gc.collect()

    # Invoking the callback should now self-evict
    await cb()

    assert "sid-1" not in _subs
    assert len(SwarmRegistry.get()._subscribers) == 0


@pytest.mark.asyncio
async def test_message_loop_start_flushes_queued_messages(monkeypatch):
    from usr.plugins.a0_swarm.extensions.python.message_loop_start import _10_swarm_unblock as ext_mod

    reg = SwarmRegistry.get()
    run = reg.create_run("P", "A0")
    agent_entry = SwarmAgent(
        agent_name="SA1_1", label="x", task="t", context_id="ctx-1",
        parent_context_id="P", status=SwarmAgentStatus.BLOCKED,
        started_at="t", run_id=run.run_id,
    )
    reg.register(agent_entry)
    reg.create_message(run.run_id, "orchestrator", "SA1_1", "resume")

    called = []

    async def fake_flush(agent_name):
        called.append(agent_name)
        return []

    monkeypatch.setattr(ext_mod.delivery, "deliver_queued_for_agent", fake_flush)

    instance = ext_mod.SwarmUnblockOnResume(agent=MagicMock())
    instance.agent.context.id = "ctx-1"
    await instance.execute()

    assert called == ["SA1_1"]
    assert reg.get_agent("SA1_1").status == SwarmAgentStatus.WORKING
