import asyncio
import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest
from usr.plugins.a0_swarm.helpers.registry import (
    SwarmRegistry, SwarmAgent, SwarmAgentStatus, SwarmMessage,
)


@pytest.fixture(autouse=True)
def fresh_registry():
    SwarmRegistry._instance = None
    yield
    SwarmRegistry._instance = None


def test_singleton_returns_same_instance():
    a = SwarmRegistry.get()
    b = SwarmRegistry.get()
    assert a is b


def test_register_and_get():
    reg = SwarmRegistry.get()
    agent = SwarmAgent(
        agent_name="SA1_1", label="Researcher", task="research X",
        context_id="ctx-a", parent_context_id="ctx-parent",
        status=SwarmAgentStatus.PENDING, started_at="2026-05-14T00:00:00+00:00",
    )
    reg.register(agent)
    assert reg.get_agent("SA1_1") is agent
    assert reg.get_agent("missing") is None


def _new_agent(name="SA1_1", status=SwarmAgentStatus.PENDING):
    return SwarmAgent(
        agent_name=name, label="X", task="t", context_id=f"ctx-{name}",
        parent_context_id="P", status=status, started_at="2026-05-14T00:00:00+00:00",
    )


def test_update_status_transition_and_finished_at():
    reg = SwarmRegistry.get()
    reg.register(_new_agent())
    reg.update_status("SA1_1", SwarmAgentStatus.WORKING)
    assert reg.get_agent("SA1_1").status == SwarmAgentStatus.WORKING
    assert reg.get_agent("SA1_1").finished_at == ""
    reg.update_status("SA1_1", SwarmAgentStatus.DONE, result="ok")
    a = reg.get_agent("SA1_1")
    assert a.status == SwarmAgentStatus.DONE
    assert a.result == "ok"
    assert a.finished_at != ""


def test_update_status_terminal_absorbing():
    """Once terminal, further updates are silently ignored — race-safe cancel."""
    reg = SwarmRegistry.get()
    reg.register(_new_agent())
    reg.update_status("SA1_1", SwarmAgentStatus.CANCELLED)
    reg.update_status("SA1_1", SwarmAgentStatus.FAILED, blocker="boom")
    assert reg.get_agent("SA1_1").status == SwarmAgentStatus.CANCELLED
    assert reg.get_agent("SA1_1").blocker == ""


def test_update_status_unknown_agent_is_noop():
    reg = SwarmRegistry.get()
    reg.update_status("nobody", SwarmAgentStatus.DONE)  # must not raise


def test_update_activity():
    reg = SwarmRegistry.get()
    reg.register(_new_agent())
    reg.update_activity("SA1_1", "Thinking...")
    assert reg.get_agent("SA1_1").current_activity == "Thinking..."


def test_add_message_attaches_to_recipient():
    reg = SwarmRegistry.get()
    reg.register(_new_agent("SA1_1"))
    reg.add_message(SwarmMessage(sender="orchestrator", recipient="SA1_1", content="hi"))
    msgs = reg.get_agent("SA1_1").messages
    assert len(msgs) == 1 and msgs[0].content == "hi"


def test_add_message_from_swarm_to_orchestrator_attaches_to_sender():
    reg = SwarmRegistry.get()
    reg.register(_new_agent("SA1_1"))
    reg.add_message(SwarmMessage(sender="SA1_1", recipient="orchestrator", content="blocked"))
    assert len(reg.get_agent("SA1_1").messages) == 1


def test_get_agent_by_context():
    reg = SwarmRegistry.get()
    a = _new_agent("SA1_1")
    a.context_id = "ctx-xyz"
    reg.register(a)
    assert reg.get_agent_by_context("ctx-xyz") is a
    assert reg.get_agent_by_context("nope") is None


def test_snapshot_filters_by_parent():
    reg = SwarmRegistry.get()
    a = _new_agent("SA1_1"); a.parent_context_id = "P1"; reg.register(a)
    b = _new_agent("SA2_1"); b.parent_context_id = "P2"; reg.register(b)
    snap = reg.snapshot(parent_ctx_id="P1")
    assert len(snap) == 1 and snap[0]["agent_name"] == "SA1_1"
    assert len(reg.snapshot()) == 2  # no filter → all


def test_clear_completed_removes_terminal_only_for_parent():
    reg = SwarmRegistry.get()
    a = _new_agent("SA1_1"); reg.register(a)
    b = _new_agent("SA1_2"); reg.register(b)
    reg.update_status("SA1_1", SwarmAgentStatus.DONE)
    reg.clear_completed(parent_ctx_id="P")
    assert reg.get_agent("SA1_1") is None
    assert reg.get_agent("SA1_2") is not None


def test_clear_for_parent_removes_all_for_that_parent():
    reg = SwarmRegistry.get()
    a = _new_agent("SA1_1"); a.parent_context_id = "P1"; reg.register(a)
    b = _new_agent("SA2_1"); b.parent_context_id = "P2"; reg.register(b)
    reg.clear_for_parent("P1")
    assert reg.get_agent("SA1_1") is None
    assert reg.get_agent("SA2_1") is not None


@pytest.mark.asyncio
async def test_subscriber_called_on_mutation():
    reg = SwarmRegistry.get()
    loop = asyncio.get_running_loop()
    fired = asyncio.Event()

    async def cb():
        fired.set()

    reg.add_subscriber(loop, cb)
    reg.register(_new_agent("SA1_1"))
    await asyncio.wait_for(fired.wait(), timeout=1.0)


@pytest.mark.asyncio
async def test_remove_subscriber_stops_callbacks():
    reg = SwarmRegistry.get()
    loop = asyncio.get_running_loop()
    calls = 0

    async def cb():
        nonlocal calls
        calls += 1

    reg.add_subscriber(loop, cb)
    reg.register(_new_agent("SA1_1"))
    await asyncio.sleep(0.05)
    reg.remove_subscriber(cb)
    reg.update_status("SA1_1", SwarmAgentStatus.WORKING)
    await asyncio.sleep(0.05)
    assert calls == 1
