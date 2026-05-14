import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest
from usr.plugins.a0_swarm.helpers.registry import (
    SwarmRegistry, SwarmAgent, SwarmAgentStatus,
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
