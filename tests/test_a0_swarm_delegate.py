import sys, types, asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Stub framework modules whose transitive imports (models -> litellm) are not
# installed in the test environment. These stubs run BEFORE the tool module
# imports them.
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

if "initialize" not in sys.modules:
    _init_stub = types.ModuleType("initialize")
    _init_stub.initialize_agent = MagicMock(return_value=MagicMock())
    sys.modules["initialize"] = _init_stub

import pytest

from usr.plugins.a0_swarm.helpers.registry import (
    SwarmRegistry, SwarmAgentStatus,
)
from usr.plugins.a0_swarm.tools import delegate_parallel as dp_mod


@pytest.fixture(autouse=True)
def fresh_registry():
    SwarmRegistry._instance = None
    yield
    SwarmRegistry._instance = None


@pytest.mark.asyncio
async def test_delegate_parallel_runs_two_tasks(monkeypatch):
    sub_contexts = []
    def fake_context(*, config):
        ctx = MagicMock()
        ctx.id = f"ctx-{len(sub_contexts)}"
        sub_agent = MagicMock()
        sub_agent.monologue = AsyncMock(return_value=f"result-{ctx.id}")
        sub_agent.hist_add_user_message = MagicMock()
        ctx.agent0 = sub_agent
        sub_contexts.append(ctx)
        return ctx

    AC = MagicMock(side_effect=fake_context)
    AC.remove = MagicMock()
    monkeypatch.setattr(dp_mod, "AgentContext", AC)
    monkeypatch.setattr(dp_mod, "initialize_agent", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(dp_mod, "UserMessage", lambda message: {"message": message})

    parent_agent = MagicMock()
    parent_agent.number = 0
    parent_agent.context.id = "PARENT"
    parent_agent.context.log.log = MagicMock()
    parent_agent.agent_name = "A0"

    tool = dp_mod.DelegateParallel(
        agent=parent_agent, name="delegate_parallel",
        method=None, args={}, message="", loop_data=None,
    )
    resp = await tool.execute(tasks=[
        {"label": "A", "task": "do A"},
        {"label": "B", "task": "do B"},
    ])

    snap = SwarmRegistry.get().snapshot()
    assert len(snap) == 2
    assert all(a["status"] == "done" for a in snap)
    assert "result-ctx-0" in resp.message
    assert "result-ctx-1" in resp.message
    assert AC.remove.call_count == 2


@pytest.mark.asyncio
async def test_delegate_parallel_one_fails_others_succeed(monkeypatch):
    counter = {"i": 0}
    def fake_context(*, config):
        ctx = MagicMock()
        ctx.id = f"ctx-{counter['i']}"
        sub = MagicMock()
        if counter["i"] == 0:
            sub.monologue = AsyncMock(return_value="ok")
        else:
            sub.monologue = AsyncMock(side_effect=RuntimeError("boom"))
        sub.hist_add_user_message = MagicMock()
        ctx.agent0 = sub
        counter["i"] += 1
        return ctx

    AC = MagicMock(side_effect=fake_context)
    AC.remove = MagicMock()
    monkeypatch.setattr(dp_mod, "AgentContext", AC)
    monkeypatch.setattr(dp_mod, "initialize_agent", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(dp_mod, "UserMessage", lambda message: {"message": message})

    parent = MagicMock()
    parent.number = 0
    parent.context.id = "P"
    parent.context.log.log = MagicMock()
    parent.agent_name = "A0"
    tool = dp_mod.DelegateParallel(
        agent=parent, name="x", method=None, args={}, message="", loop_data=None,
    )
    resp = await tool.execute(tasks=[{"label": "A", "task": "t"}, {"label": "B", "task": "t"}])

    snap = sorted(SwarmRegistry.get().snapshot(), key=lambda a: a["agent_name"])
    assert snap[0]["status"] == "done"
    assert snap[1]["status"] == "failed"
    assert "boom" in snap[1]["blocker"]
    assert "FAILED" in resp.message and "DONE" in resp.message


@pytest.mark.asyncio
async def test_delegate_parallel_pre_cancelled_is_absorbed(monkeypatch):
    """If status is set to CANCELLED mid-flight, the eventual DONE/FAILED is dropped."""
    started = asyncio.Event()
    proceed = asyncio.Event()

    async def slow_monologue():
        started.set()
        await proceed.wait()
        return "late"

    def fake_context(*, config):
        ctx = MagicMock()
        ctx.id = "ctx-0"
        sub = MagicMock()
        sub.monologue = slow_monologue
        sub.hist_add_user_message = MagicMock()
        ctx.agent0 = sub
        return ctx

    AC = MagicMock(side_effect=fake_context)
    AC.remove = MagicMock()
    monkeypatch.setattr(dp_mod, "AgentContext", AC)
    monkeypatch.setattr(dp_mod, "initialize_agent", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(dp_mod, "UserMessage", lambda message: {"message": message})

    parent = MagicMock()
    parent.number = 0
    parent.context.id = "P"
    parent.context.log.log = MagicMock()
    parent.agent_name = "A0"
    tool = dp_mod.DelegateParallel(
        agent=parent, name="x", method=None, args={}, message="", loop_data=None,
    )
    task = asyncio.create_task(tool.execute(tasks=[{"label": "A", "task": "t"}]))

    await started.wait()
    SwarmRegistry.get().update_status("SA1_1", SwarmAgentStatus.CANCELLED)
    proceed.set()
    await task

    assert SwarmRegistry.get().get_agent("SA1_1").status == SwarmAgentStatus.CANCELLED
