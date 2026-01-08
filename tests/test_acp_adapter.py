"""Tests for ACP adapter module."""

import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from unittest.mock import patch, MagicMock, Mock
from types import ModuleType


@pytest.fixture
def acp_adapter():
    """Create a fresh ACP adapter instance."""
    from python.helpers.acp_adapter import AgentZeroACP

    return AgentZeroACP()


@pytest.fixture
def mock_agent_modules():
    """Mock the agent and initialize modules to avoid heavy imports."""
    mock_agent = ModuleType("agent")
    mock_agent.AgentContext = MagicMock()
    mock_agent.AgentContextType = MagicMock()
    mock_agent.AgentContextType.BACKGROUND = "background"
    mock_agent.UserMessage = MagicMock()

    mock_initialize = ModuleType("initialize")
    mock_initialize.initialize_agent = MagicMock(return_value=MagicMock())

    mock_persist_chat = ModuleType("python.helpers.persist_chat")
    mock_persist_chat.remove_chat = MagicMock()

    with patch.dict(
        sys.modules,
        {
            "agent": mock_agent,
            "initialize": mock_initialize,
            "python.helpers.persist_chat": mock_persist_chat,
        },
    ):
        yield {
            "agent": mock_agent,
            "initialize": mock_initialize,
            "persist_chat": mock_persist_chat,
        }


def test_acp_availability_check():
    """Test ACP availability reflects actual SDK state."""
    from python.helpers import acp_adapter

    result = acp_adapter.is_available()
    assert isinstance(result, bool)


def test_acp_adapter_module_imports():
    """Test that the acp_adapter module can be imported without errors."""
    from python.helpers import acp_adapter

    assert hasattr(acp_adapter, "AgentZeroACP")
    assert hasattr(acp_adapter, "is_available")
    assert hasattr(acp_adapter, "ACP_AVAILABLE")


@pytest.mark.asyncio
async def test_new_session_creates_agent_context(acp_adapter, mock_agent_modules):
    """Test that new_session creates an AgentContext and returns NewSessionResponse."""
    mock_context = MagicMock()
    mock_context.id = "test-context-123"
    mock_context.data = {}
    mock_agent_modules["agent"].AgentContext.return_value = mock_context

    session_response = await acp_adapter.new_session(cwd="/tmp", mcp_servers=[])

    assert session_response is not None
    assert session_response.session_id is not None
    assert len(acp_adapter._sessions) == 1


@pytest.mark.asyncio
async def test_end_session_cleans_up_context(acp_adapter, mock_agent_modules):
    """Test that end_session removes the AgentContext."""
    mock_context = MagicMock()
    mock_context.id = "test-context-456"
    mock_context.data = {}
    mock_agent_modules["agent"].AgentContext.return_value = mock_context
    mock_agent_modules["agent"].AgentContext.get.return_value = mock_context
    mock_agent_modules["agent"].AgentContext.remove.return_value = mock_context

    session_info = await acp_adapter.new_session()
    session_id = session_info.session_id

    await acp_adapter.end_session(session_id)

    mock_context.reset.assert_called_once()
    mock_agent_modules["agent"].AgentContext.remove.assert_called_once_with(
        "test-context-456"
    )
    mock_agent_modules["persist_chat"].remove_chat.assert_called_once_with(
        "test-context-456"
    )
    assert session_id not in acp_adapter._sessions
