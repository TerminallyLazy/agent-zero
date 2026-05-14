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
