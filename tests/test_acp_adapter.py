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


def test_convert_content_blocks_text_only(acp_adapter, mock_agent_modules):
    """Test converting ACP content blocks with text to UserMessage."""
    from dataclasses import dataclass, field

    @dataclass
    class FakeUserMessage:
        message: str
        attachments: list[str] = field(default_factory=list)

    mock_agent_modules["agent"].UserMessage = FakeUserMessage

    blocks = [{"type": "text", "text": "Hello, Agent Zero!"}]

    user_message = acp_adapter._convert_content_blocks(blocks)

    assert user_message.message == "Hello, Agent Zero!"
    assert user_message.attachments == []


def test_convert_content_blocks_multiple_text(acp_adapter, mock_agent_modules):
    """Test converting ACP content blocks with multiple text blocks."""
    from dataclasses import dataclass, field

    @dataclass
    class FakeUserMessage:
        message: str
        attachments: list[str] = field(default_factory=list)

    mock_agent_modules["agent"].UserMessage = FakeUserMessage

    blocks = [
        {"type": "text", "text": "First part."},
        {"type": "text", "text": "Second part."},
    ]

    user_message = acp_adapter._convert_content_blocks(blocks)

    assert user_message.message == "First part.\nSecond part."


@pytest.mark.asyncio
async def test_prompt_processes_message_and_returns_response(
    acp_adapter, mock_agent_modules
):
    """Test that prompt() processes content blocks and returns PromptResponse."""
    from python.helpers.acp_adapter import ACP_AVAILABLE
    from dataclasses import dataclass, field

    if not ACP_AVAILABLE:
        pytest.skip("ACP SDK not installed")

    @dataclass
    class FakeUserMessage:
        message: str
        attachments: list[str] = field(default_factory=list)

    mock_agent_modules["agent"].UserMessage = FakeUserMessage

    # Setup mock context
    mock_context = MagicMock()
    mock_context.id = "ctx-789"
    mock_context.data = {}
    mock_context.agent0 = MagicMock()
    mock_context.agent0.data = {}
    mock_context.log = MagicMock()
    mock_agent_modules["agent"].AgentContext.return_value = mock_context
    mock_agent_modules["agent"].AgentContext.get.return_value = mock_context

    # Mock the communicate method to return a result
    mock_task = MagicMock()

    async def mock_result():
        return "Hello! How can I help?"

    mock_task.result = mock_result
    mock_context.communicate.return_value = mock_task

    # Create session
    session_response = await acp_adapter.new_session()
    session_id = session_response.session_id

    # Create ACP content blocks
    prompt_blocks = [{"type": "text", "text": "Hello"}]

    # Process prompt
    response = await acp_adapter.prompt(prompt_blocks, session_id)

    assert response is not None
    assert response.stop_reason == "end_turn"


@pytest.mark.asyncio
async def test_cancel_prompt_kills_process(acp_adapter, mock_agent_modules):
    """Test that cancel_prompt() calls kill_process on the context."""
    from python.helpers.acp_adapter import ACP_AVAILABLE

    if not ACP_AVAILABLE:
        pytest.skip("ACP SDK not installed")

    # Setup mock context
    mock_context = MagicMock()
    mock_context.id = "ctx-cancel-test"
    mock_context.data = {}
    mock_agent_modules["agent"].AgentContext.return_value = mock_context
    mock_agent_modules["agent"].AgentContext.get.return_value = mock_context

    # Create session
    session_response = await acp_adapter.new_session()
    session_id = session_response.session_id

    # Cancel prompt
    await acp_adapter.cancel_prompt(session_id)

    mock_context.kill_process.assert_called_once()
