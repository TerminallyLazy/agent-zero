import json
import sys, types
from pathlib import Path
from unittest.mock import MagicMock

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Stub framework deps before importing handlers
if "agent" not in sys.modules:
    _agent_stub = types.ModuleType("agent")
    _agent_stub.AgentContext = MagicMock()
    _agent_stub.UserMessage = lambda message=None, **kw: {"message": message}
    sys.modules["agent"] = _agent_stub

if "helpers.api" not in sys.modules:
    _api_stub = types.ModuleType("helpers.api")

    class _ApiHandler:
        def __init__(self, app=None, thread_lock=None):
            self.app = app
            self.thread_lock = thread_lock

    _api_stub.ApiHandler = _ApiHandler
    _api_stub.Request = object
    sys.modules["helpers.api"] = _api_stub

import pytest
from usr.plugins.a0_swarm.helpers.registry import (
    SwarmRegistry, SwarmAgent, SwarmAgentStatus,
)


@pytest.fixture(autouse=True)
def fresh_registry():
    SwarmRegistry._instance = None
    yield
    SwarmRegistry._instance = None


def _new(name, status=SwarmAgentStatus.WORKING, parent="P", **kw):
    return SwarmAgent(
        agent_name=name, label="x", task="t",
        context_id=kw.get("ctx", f"ctx-{name}"),
        parent_context_id=parent,
        status=status, started_at="t",
        **{k: v for k, v in kw.items() if k in {"blocker", "result"}},
    )


# ---- swarm_status ----------------------------------------------------------

@pytest.mark.asyncio
async def test_swarm_status_filters_by_parent():
    from usr.plugins.a0_swarm.api.swarm_status import SwarmStatus
    reg = SwarmRegistry.get()
    reg.register(_new("SA1_1", parent="P1"))
    reg.register(_new("SA2_1", parent="P2"))

    handler = SwarmStatus(app=MagicMock(), thread_lock=MagicMock())
    out = await handler.process({"parent_context_id": "P1"}, MagicMock())
    assert isinstance(out["agents"], list)
    assert isinstance(json.loads(json.dumps(out))["agents"], list)
    assert len(out["agents"]) == 1 and out["agents"][0]["agent_name"] == "SA1_1"
    assert "runs" in out

    out_all = await handler.process({}, MagicMock())
    assert isinstance(out_all["agents"], list)
    assert len(out_all["agents"]) == 2


# ---- swarm_send_message ----------------------------------------------------

@pytest.mark.asyncio
async def test_swarm_send_message_validates_input():
    from usr.plugins.a0_swarm.api.swarm_send_message import SwarmSendMessage
    handler = SwarmSendMessage(app=MagicMock(), thread_lock=MagicMock())
    out = await handler.process({"agent_name": "", "content": ""}, MagicMock())
    assert out.get("ok") is False
    assert "required" in out.get("error", "").lower()


@pytest.mark.asyncio
async def test_swarm_send_message_records_and_communicates(monkeypatch):
    from usr.plugins.a0_swarm.api import swarm_send_message as sm

    reg = SwarmRegistry.get()
    reg.register(_new("SA1_1", status=SwarmAgentStatus.BLOCKED, ctx="ctx-1", blocker="stuck"))

    target_ctx = MagicMock()
    AC = MagicMock(); AC.get.return_value = target_ctx
    monkeypatch.setattr(sm, "AgentContext", AC)
    monkeypatch.setattr(sm, "UserMessage", lambda message: {"message": message})

    handler = sm.SwarmSendMessage(app=MagicMock(), thread_lock=MagicMock())
    out = await handler.process(
        {"agent_name": "SA1_1", "content": "use this key", "unblock": True},
        MagicMock(),
    )
    assert out == {"ok": True}
    a = reg.get_agent("SA1_1")
    assert a.status == SwarmAgentStatus.WORKING
    assert a.blocker == ""
    assert any(m.content == "use this key" for m in a.messages)
    target_ctx.communicate.assert_called_once()


# ---- swarm_cancel ----------------------------------------------------------

@pytest.mark.asyncio
async def test_swarm_cancel_sets_status_then_kills(monkeypatch):
    from usr.plugins.a0_swarm.api import swarm_cancel as sc

    reg = SwarmRegistry.get()
    reg.register(_new("SA1_1", ctx="ctx-1"))

    call_order = []
    ctx = MagicMock()
    ctx.kill_process = MagicMock(side_effect=lambda: call_order.append("kill"))
    AC = MagicMock(); AC.get.return_value = ctx
    monkeypatch.setattr(sc, "AgentContext", AC)

    handler = sc.SwarmCancel(app=MagicMock(), thread_lock=MagicMock())

    # capture status at moment of get call (before kill_process)
    orig_get = AC.get
    def get_then_check(*a, **kw):
        # status should already be CANCELLED at this point
        call_order.append(("status_at_get", reg.get_agent("SA1_1").status))
        return orig_get(*a, **kw)
    AC.get = get_then_check

    out = await handler.process({"agent_name": "SA1_1"}, MagicMock())
    assert out == {"ok": True}
    assert reg.get_agent("SA1_1").status == SwarmAgentStatus.CANCELLED
    ctx.kill_process.assert_called_once()
    # Verify ordering: status was CANCELLED before kill_process was called
    assert call_order[0][1] == SwarmAgentStatus.CANCELLED
    assert call_order[1] == "kill"


# ---- swarm_clear_completed -------------------------------------------------

@pytest.mark.asyncio
async def test_swarm_clear_completed():
    from usr.plugins.a0_swarm.api.swarm_clear_completed import SwarmClearCompleted

    reg = SwarmRegistry.get()
    reg.register(_new("SA1_1", status=SwarmAgentStatus.DONE))
    reg.register(_new("SA1_2", status=SwarmAgentStatus.WORKING))

    handler = SwarmClearCompleted(app=MagicMock(), thread_lock=MagicMock())
    out = await handler.process({"parent_context_id": "P"}, MagicMock())
    assert out == {"ok": True}
    assert reg.get_agent("SA1_1") is None
    assert reg.get_agent("SA1_2") is not None
