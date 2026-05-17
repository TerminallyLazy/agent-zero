import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if "agent" not in sys.modules:
    _agent_stub = types.ModuleType("agent")
    _agent_stub.AgentContext = MagicMock()
    _agent_stub.UserMessage = lambda message=None, **kw: {"message": message}
    sys.modules["agent"] = _agent_stub

import pytest

from usr.plugins.a0_swarm.helpers.registry import (
    SwarmAgent,
    SwarmAgentStatus,
    SwarmRegistry,
)


@pytest.fixture(autouse=True)
def fresh_registry():
    SwarmRegistry._instance = None
    yield
    SwarmRegistry._instance = None


def _agent(name="SA1_1", run_id="run-a", status=SwarmAgentStatus.WORKING, **kw):
    return SwarmAgent(
        agent_name=name,
        label=name,
        task="task",
        context_id=kw.get("context_id", f"ctx-{name}"),
        parent_context_id="P",
        status=status,
        started_at="t",
        run_id=run_id,
        delivery_mode=kw.get("delivery_mode", "local"),
        remote_label=kw.get("remote_label", ""),
        remote_base_url=kw.get("remote_base_url", ""),
        remote_task_id=kw.get("remote_task_id", ""),
        remote_auth_token=kw.get("remote_auth_token", ""),
    )


@pytest.mark.asyncio
async def test_deliver_local_message_marks_delivered(monkeypatch):
    from usr.plugins.a0_swarm.helpers import delivery

    reg = SwarmRegistry.get()
    run = reg.create_run("P", "A0")
    target = _agent(run_id=run.run_id)
    reg.register(target)
    msg = reg.create_message(run.run_id, "orchestrator", target.agent_name, "hello")

    ctx = MagicMock()
    ac = MagicMock()
    ac.get.return_value = ctx
    monkeypatch.setattr(delivery, "AgentContext", ac)
    monkeypatch.setattr(delivery, "UserMessage", lambda message: {"message": message})

    result = await delivery.deliver_message(msg.message_id)

    assert result.ok is True
    assert result.state == "delivered"
    ctx.communicate.assert_called_once()
    assert reg.get_message(msg.message_id).delivery_state == "delivered"


@pytest.mark.asyncio
async def test_deliver_local_missing_context_marks_failed(monkeypatch):
    from usr.plugins.a0_swarm.helpers import delivery

    reg = SwarmRegistry.get()
    run = reg.create_run("P", "A0")
    target = _agent(run_id=run.run_id)
    reg.register(target)
    msg = reg.create_message(run.run_id, "orchestrator", target.agent_name, "hello")

    ac = MagicMock()
    ac.get.return_value = None
    monkeypatch.setattr(delivery, "AgentContext", ac)

    result = await delivery.deliver_message(msg.message_id)

    assert result.ok is False
    assert result.state == "failed"
    assert "context not found" in result.reason
    assert reg.get_message(msg.message_id).delivery_state == "failed"


@pytest.mark.asyncio
async def test_orchestrator_message_marks_delivered():
    from usr.plugins.a0_swarm.helpers import delivery

    reg = SwarmRegistry.get()
    run = reg.create_run("P", "A0")
    sender = _agent(run_id=run.run_id)
    reg.register(sender)
    msg = reg.create_message(run.run_id, sender.agent_name, "orchestrator", "blocked")

    result = await delivery.deliver_message(msg.message_id)

    assert result.ok is True
    assert result.state == "delivered"
    assert reg.get_message(msg.message_id).delivery_state == "delivered"


@pytest.mark.asyncio
async def test_remote_delivery_uses_a2a_intervention(monkeypatch):
    from usr.plugins.a0_swarm.helpers import delivery

    reg = SwarmRegistry.get()
    run = reg.create_run("P", "A0")
    target = _agent(
        run_id=run.run_id,
        delivery_mode="remote_a2a",
        remote_label="rig",
        remote_base_url="http://rig:55000/a2a/t-token",
        remote_auth_token="secret-token",
        context_id="remote-ctx",
    )
    reg.register(target)
    msg = reg.create_message(run.run_id, "orchestrator", target.agent_name, "continue")

    monkeypatch.setattr(delivery.a2a_runner, "send_intervention", AsyncMock(return_value=True))

    result = await delivery.deliver_message(msg.message_id)

    assert result.ok is True
    assert result.state == "delivered"
    delivery.a2a_runner.send_intervention.assert_awaited_once()
    remote_arg = delivery.a2a_runner.send_intervention.await_args.args[0]
    assert remote_arg.auth_token == "secret-token"


@pytest.mark.asyncio
async def test_remote_delivery_failure_records_reason(monkeypatch):
    from usr.plugins.a0_swarm.helpers import delivery

    reg = SwarmRegistry.get()
    run = reg.create_run("P", "A0")
    target = _agent(
        run_id=run.run_id,
        delivery_mode="remote_a2a",
        remote_label="rig",
        remote_base_url="http://rig:55000/a2a/t-token",
        context_id="remote-ctx",
    )
    reg.register(target)
    msg = reg.create_message(run.run_id, "orchestrator", target.agent_name, "continue")

    monkeypatch.setattr(delivery.a2a_runner, "send_intervention", AsyncMock(return_value=False))

    result = await delivery.deliver_message(msg.message_id)

    assert result.ok is False
    assert result.state == "failed"
    assert "remote intervention failed" in result.reason
    assert reg.get_message(msg.message_id).failure_reason == result.reason
