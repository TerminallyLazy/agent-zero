import sys, types
from pathlib import Path
from unittest.mock import MagicMock

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if "agent" not in sys.modules:
    _agent_stub = types.ModuleType("agent")
    _agent_stub.AgentContext = MagicMock()
    _agent_stub.UserMessage = lambda message=None, **kw: {"message": message}
    _agent_stub.Agent = MagicMock()
    _agent_stub.LoopData = MagicMock()
    sys.modules["agent"] = _agent_stub

if "helpers.tool" not in sys.modules:
    _tool_stub = types.ModuleType("helpers.tool")

    class _Response:
        def __init__(self, message, break_loop=False, additional=None):
            self.message = message
            self.break_loop = break_loop
            self.additional = additional

    class _Tool:
        def __init__(self, agent=None, name="", method=None, args=None,
                     message="", loop_data=None, **kwargs):
            self.agent = agent
            self.name = name
            self.method = method
            self.args = args or {}
            self.message = message
            self.loop_data = loop_data

    _tool_stub.Tool = _Tool
    _tool_stub.Response = _Response
    sys.modules["helpers.tool"] = _tool_stub

import pytest

from usr.plugins.a0_swarm.helpers.registry import (
    SwarmRegistry, SwarmAgent, SwarmAgentStatus,
)
from usr.plugins.a0_swarm.tools import swarm_message as sm_mod


@pytest.fixture(autouse=True)
def fresh_registry():
    SwarmRegistry._instance = None
    yield
    SwarmRegistry._instance = None


@pytest.mark.asyncio
async def test_swarm_message_to_orchestrator_records_message(monkeypatch):
    reg = SwarmRegistry.get()
    run = reg.create_run("P", "A0")
    reg.register(SwarmAgent(
        agent_name="SA1_1", label="x", task="t",
        context_id="ctx-1", parent_context_id="P",
        status=SwarmAgentStatus.WORKING, started_at="t", run_id=run.run_id,
    ))

    sender_ctx = MagicMock(); sender_ctx.id = "ctx-1"
    agent = MagicMock(); agent.context = sender_ctx; agent.agent_name = "SA1_1"
    agent.context.log.log = MagicMock()

    tool = sm_mod.SwarmMessageTool(
        agent=agent, name="x", method=None, args={}, message="", loop_data=None,
    )
    resp = await tool.execute(recipient="orchestrator", content="need help", is_blocker=True)

    a = reg.get_agent("SA1_1")
    assert a.status == SwarmAgentStatus.BLOCKED
    assert a.blocker == "need help"
    assert len(a.messages) == 1


@pytest.mark.asyncio
async def test_swarm_message_to_peer_injects_via_communicate(monkeypatch):
    reg = SwarmRegistry.get()
    run = reg.create_run("P", "A0")
    reg.register(SwarmAgent(agent_name="SA1_1", label="x", task="t",
        context_id="ctx-1", parent_context_id="P",
        status=SwarmAgentStatus.WORKING, started_at="t", run_id=run.run_id))
    reg.register(SwarmAgent(agent_name="SA1_2", label="x", task="t",
        context_id="ctx-2", parent_context_id="P",
        status=SwarmAgentStatus.WORKING, started_at="t", run_id=run.run_id))

    target_ctx = MagicMock()
    monkeypatch.setattr(sm_mod.delivery, "UserMessage", lambda message: {"message": message})
    AgentContext_mock = MagicMock()
    AgentContext_mock.get.return_value = target_ctx
    monkeypatch.setattr(sm_mod.delivery, "AgentContext", AgentContext_mock)

    sender_ctx = MagicMock(); sender_ctx.id = "ctx-1"
    agent = MagicMock(); agent.context = sender_ctx; agent.agent_name = "SA1_1"
    agent.context.log.log = MagicMock()

    tool = sm_mod.SwarmMessageTool(
        agent=agent, name="x", method=None, args={}, message="", loop_data=None,
    )
    resp = await tool.execute(recipient="SA1_2", content="hand-off")

    target_ctx.communicate.assert_called_once()
    payload = target_ctx.communicate.call_args[0][0]
    assert payload["message"].startswith("[Message from SA1_1]:")
    assert "delivered" in resp.message


@pytest.mark.asyncio
async def test_swarm_message_rejects_cross_run_peer(monkeypatch):
    reg = SwarmRegistry.get()
    run_a = reg.create_run("P", "A0")
    run_b = reg.create_run("P", "A0")
    reg.register(SwarmAgent(agent_name="SA1_1", label="x", task="t",
        context_id="ctx-1", parent_context_id="P",
        status=SwarmAgentStatus.WORKING, started_at="t", run_id=run_a.run_id))
    reg.register(SwarmAgent(agent_name="SA1_2", label="x", task="t",
        context_id="ctx-2", parent_context_id="P",
        status=SwarmAgentStatus.WORKING, started_at="t", run_id=run_b.run_id))

    sender_ctx = MagicMock()
    sender_ctx.id = "ctx-1"
    agent = MagicMock()
    agent.context = sender_ctx
    agent.agent_name = "SA1_1"
    agent.context.log.log = MagicMock()

    tool = sm_mod.SwarmMessageTool(agent=agent, name="x", method=None, args={}, message="", loop_data=None)
    resp = await tool.execute(recipient="SA1_2", content="bad handoff")

    assert "recipient is not in this swarm run" in resp.message


@pytest.mark.asyncio
async def test_swarm_message_response_includes_delivery_state(monkeypatch):
    reg = SwarmRegistry.get()
    run = reg.create_run("P", "A0")
    reg.register(SwarmAgent(agent_name="SA1_1", label="x", task="t",
        context_id="ctx-1", parent_context_id="P",
        status=SwarmAgentStatus.WORKING, started_at="t", run_id=run.run_id))
    reg.register(SwarmAgent(agent_name="SA1_2", label="x", task="t",
        context_id="ctx-2", parent_context_id="P",
        status=SwarmAgentStatus.WORKING, started_at="t", run_id=run.run_id))

    async def fake_deliver(message_id):
        reg.mark_message_delivered(message_id)
        return MagicMock(ok=True, state="delivered", reason="", message_id=message_id)

    monkeypatch.setattr(sm_mod.delivery, "deliver_message", fake_deliver)

    sender_ctx = MagicMock()
    sender_ctx.id = "ctx-1"
    agent = MagicMock()
    agent.context = sender_ctx
    agent.agent_name = "SA1_1"
    agent.context.log.log = MagicMock()

    tool = sm_mod.SwarmMessageTool(agent=agent, name="x", method=None, args={}, message="", loop_data=None)
    resp = await tool.execute(recipient="SA1_2", content="handoff")

    assert "delivered" in resp.message
    assert "msg-" in resp.message
