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
    _agent_stub.AgentContextType = types.SimpleNamespace(BACKGROUND="background")
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

# helpers.plugins.get_plugin_config — stub the submodule and ensure the
# `helpers` package exposes `plugins` as attribute (matches `from helpers import plugins`)
_plugins_stub = types.ModuleType("helpers.plugins")
_plugins_stub.get_plugin_config = MagicMock(return_value={})
sys.modules["helpers.plugins"] = _plugins_stub
if "helpers" not in sys.modules:
    _helpers_pkg = types.ModuleType("helpers")
    _helpers_pkg.__path__ = []
    sys.modules["helpers"] = _helpers_pkg
sys.modules["helpers"].plugins = _plugins_stub

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
    def fake_context(*, config, type=None, name=None):
        ctx = MagicMock()
        ctx.id = f"ctx-{len(sub_contexts)}"
        ctx.type = type
        ctx.name = name
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
    assert len(snap["runs"]) == 1
    assert len(snap["agents"]) == 2
    assert all(a["run_id"] == snap["runs"][0]["run_id"] for a in snap["agents"])
    assert all(a["status"] == "done" for a in snap["agents"])
    assert "result-ctx-0" in resp.message
    assert "result-ctx-1" in resp.message
    assert AC.remove.call_count == 2


@pytest.mark.asyncio
async def test_delegate_parallel_creates_background_subagent_contexts(monkeypatch):
    sub_contexts = []

    def fake_context(*, config, type=None, name=None):
        ctx = MagicMock()
        ctx.id = f"ctx-{len(sub_contexts)}"
        ctx.type = type
        ctx.name = name
        sub_agent = MagicMock()
        sub_agent.monologue = AsyncMock(return_value="ok")
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
    await tool.execute(tasks=[{"label": "A", "task": "do A"}])

    assert AC.call_args.kwargs["type"] == dp_mod.AgentContextType.BACKGROUND
    assert sub_contexts[0].type == dp_mod.AgentContextType.BACKGROUND
    assert sub_contexts[0].name == "Swarm: A"


@pytest.mark.asyncio
async def test_delegate_parallel_one_fails_others_succeed(monkeypatch):
    counter = {"i": 0}
    def fake_context(*, config, type=None, name=None):
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

    snap = sorted(SwarmRegistry.get().snapshot()["agents"], key=lambda a: a["agent_name"])
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

    def fake_context(*, config, type=None, name=None):
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


@pytest.mark.asyncio
async def test_delegate_parallel_truncates_large_result(monkeypatch):
    """Result over MAX_RESULT_BYTES gets a [...truncated] marker."""
    from usr.plugins.a0_swarm.helpers.registry import MAX_RESULT_BYTES
    huge = "x" * (MAX_RESULT_BYTES + 1000)

    def fake_context(*, config, type=None, name=None):
        ctx = MagicMock()
        ctx.id = "ctx-0"
        sub = MagicMock()
        sub.monologue = AsyncMock(return_value=huge)
        sub.hist_add_user_message = MagicMock()
        ctx.agent0 = sub
        return ctx

    AC = MagicMock(side_effect=fake_context); AC.remove = MagicMock()
    monkeypatch.setattr(dp_mod, "AgentContext", AC)
    monkeypatch.setattr(dp_mod, "initialize_agent", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(dp_mod, "UserMessage", lambda message: {"message": message})

    parent = MagicMock(); parent.number = 0; parent.context.id = "P"
    parent.context.log.log = MagicMock(); parent.agent_name = "A0"
    tool = dp_mod.DelegateParallel(
        agent=parent, name="x", method=None, args={}, message="", loop_data=None,
    )
    await tool.execute(tasks=[{"label": "A", "task": "t"}])

    a = SwarmRegistry.get().get_agent("SA1_1")
    assert a.result.endswith("[...truncated]")
    assert len(a.result.encode("utf-8")) <= MAX_RESULT_BYTES + len("\n[...truncated]")


@pytest.mark.asyncio
async def test_delegate_parallel_small_result_not_truncated(monkeypatch):
    def fake_context(*, config, type=None, name=None):
        ctx = MagicMock(); ctx.id = "ctx-0"
        sub = MagicMock()
        sub.monologue = AsyncMock(return_value="short result")
        sub.hist_add_user_message = MagicMock()
        ctx.agent0 = sub
        return ctx

    AC = MagicMock(side_effect=fake_context); AC.remove = MagicMock()
    monkeypatch.setattr(dp_mod, "AgentContext", AC)
    monkeypatch.setattr(dp_mod, "initialize_agent", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(dp_mod, "UserMessage", lambda message: {"message": message})

    parent = MagicMock(); parent.number = 0; parent.context.id = "P"
    parent.context.log.log = MagicMock(); parent.agent_name = "A0"
    tool = dp_mod.DelegateParallel(
        agent=parent, name="x", method=None, args={}, message="", loop_data=None,
    )
    await tool.execute(tasks=[{"label": "A", "task": "t"}])

    a = SwarmRegistry.get().get_agent("SA1_1")
    assert a.result == "short result"
    assert "[...truncated]" not in a.result


@pytest.mark.asyncio
async def test_delegate_parallel_max_parallel_cap_rejects(monkeypatch):
    """When plugin config max_parallel is set, fan-out above it is rejected."""
    _plugins_stub.get_plugin_config = MagicMock(return_value={"max_parallel": 2})
    monkeypatch.setattr(dp_mod, "plugins", _plugins_stub)

    parent = MagicMock(); parent.number = 0; parent.context.id = "P"
    parent.context.log.log = MagicMock(); parent.agent_name = "A0"
    tool = dp_mod.DelegateParallel(
        agent=parent, name="x", method=None, args={}, message="", loop_data=None,
    )
    resp = await tool.execute(tasks=[
        {"label": "A", "task": "t"},
        {"label": "B", "task": "t"},
        {"label": "C", "task": "t"},
    ])
    assert "rejected" in resp.message
    assert "max_parallel=2" in resp.message
    assert SwarmRegistry.get().snapshot()["agents"] == []

    _plugins_stub.get_plugin_config = MagicMock(return_value={})


@pytest.mark.asyncio
async def test_delegate_parallel_unknown_remote_endpoint_is_failed(monkeypatch):
    """If a task's `endpoint` doesn't resolve to any configured remote and isn't
    a raw URL, the entry is recorded as FAILED with a clear blocker."""
    _plugins_stub.get_plugin_config = MagicMock(return_value={"remotes": []})
    monkeypatch.setattr(dp_mod, "plugins", _plugins_stub)
    # resolve_endpoint is imported by name in delegate_parallel
    monkeypatch.setattr(dp_mod, "resolve_endpoint", lambda ep, agent=None: None)

    parent = MagicMock(); parent.number = 0; parent.context.id = "P"
    parent.context.log.log = MagicMock(); parent.agent_name = "A0"
    tool = dp_mod.DelegateParallel(
        agent=parent, name="x", method=None, args={}, message="", loop_data=None,
    )
    await tool.execute(tasks=[
        {"label": "Remote", "task": "ping", "endpoint": "does-not-exist"},
    ])

    a = SwarmRegistry.get().get_agent("SA1_1")
    assert a.status == SwarmAgentStatus.FAILED
    assert "Unknown remote endpoint" in a.blocker
    assert a.remote_label == "does-not-exist"

    _plugins_stub.get_plugin_config = MagicMock(return_value={})


@pytest.mark.asyncio
async def test_delegate_parallel_remote_happy_path(monkeypatch):
    """Configured remote endpoint: tool sends via a2a_runner, status flips
    PENDING -> WORKING -> DONE, result stored, remote_task_id captured."""
    from usr.plugins.a0_swarm.helpers.remotes import RemoteEndpoint
    fake_remote = RemoteEndpoint(label="rig", base_url="http://x:55000", auth_token="tok")
    monkeypatch.setattr(dp_mod, "resolve_endpoint",
                        lambda ep, agent=None: fake_remote if ep == "rig" else None)

    fake_conn = MagicMock()
    fake_conn.close = AsyncMock()
    runner = dp_mod.a2a_runner
    monkeypatch.setattr(runner, "is_available", lambda: True)
    monkeypatch.setattr(runner, "submit_task",
                        AsyncMock(return_value=(fake_conn, "task-xyz", "ctx-remote")))
    monkeypatch.setattr(runner, "wait_for_result",
                        AsyncMock(return_value=("completed", "remote result text")))

    parent = MagicMock(); parent.number = 0; parent.context.id = "P"
    parent.context.log.log = MagicMock(); parent.agent_name = "A0"
    tool = dp_mod.DelegateParallel(
        agent=parent, name="x", method=None, args={}, message="", loop_data=None,
    )
    resp = await tool.execute(tasks=[
        {"label": "Researcher", "task": "do it", "endpoint": "rig"},
    ])

    a = SwarmRegistry.get().get_agent("SA1_1")
    assert a.status == SwarmAgentStatus.DONE
    assert a.is_remote
    assert a.remote_label == "rig"
    assert a.remote_base_url == "http://x:55000"
    assert a.remote_auth_token == "tok"
    assert a.remote_task_id == "task-xyz"
    assert a.context_id == "ctx-remote"
    assert a.result == "remote result text"
    assert "via rig" in resp.message
