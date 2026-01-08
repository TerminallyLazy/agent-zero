"""Tests for ACP stream handler."""

import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from unittest.mock import AsyncMock


def test_stream_handler_initialization():
    """Test that ACPStreamHandler can be initialized."""
    from python.helpers.acp_stream_handler import ACPStreamHandler

    mock_session_update = AsyncMock()
    handler = ACPStreamHandler(
        session_id="test-session", session_update=mock_session_update
    )

    assert handler.session_id == "test-session"
    assert handler._buffer == ""


@pytest.mark.asyncio
async def test_stream_handler_sends_text_update():
    """Test that stream handler sends text updates via callback."""
    from python.helpers.acp_stream_handler import ACPStreamHandler, ACP_AVAILABLE

    if not ACP_AVAILABLE:
        pytest.skip("ACP SDK not installed")

    mock_session_update = AsyncMock()
    handler = ACPStreamHandler(
        session_id="test-session", session_update=mock_session_update
    )

    await handler.on_response_chunk("Hello", "Hello")

    mock_session_update.assert_called_once()
    call_args = mock_session_update.call_args
    assert call_args[0][0] == "test-session"


@pytest.mark.asyncio
async def test_stream_handler_sends_reasoning_update():
    """Test that stream handler sends reasoning/thought updates."""
    from python.helpers.acp_stream_handler import ACPStreamHandler, ACP_AVAILABLE

    if not ACP_AVAILABLE:
        pytest.skip("ACP SDK not installed")

    mock_session_update = AsyncMock()
    handler = ACPStreamHandler(
        session_id="test-session", session_update=mock_session_update
    )

    await handler.on_reasoning_chunk("Thinking...", "Thinking...")

    mock_session_update.assert_called_once()
    call_args = mock_session_update.call_args
    assert call_args[0][0] == "test-session"


@pytest.mark.asyncio
async def test_stream_handler_sends_tool_start():
    """Test that stream handler sends tool start notifications."""
    from python.helpers.acp_stream_handler import ACPStreamHandler, ACP_AVAILABLE

    if not ACP_AVAILABLE:
        pytest.skip("ACP SDK not installed")

    mock_session_update = AsyncMock()
    handler = ACPStreamHandler(
        session_id="test-session", session_update=mock_session_update
    )

    await handler.on_tool_start("code_execution", {"code": "print('hello')"})

    mock_session_update.assert_called_once()
    call_args = mock_session_update.call_args
    assert call_args[0][0] == "test-session"
    assert handler._current_tool_id is not None


@pytest.mark.asyncio
async def test_stream_handler_sends_tool_result():
    """Test that stream handler sends tool result notifications."""
    from python.helpers.acp_stream_handler import ACPStreamHandler, ACP_AVAILABLE

    if not ACP_AVAILABLE:
        pytest.skip("ACP SDK not installed")

    mock_session_update = AsyncMock()
    handler = ACPStreamHandler(
        session_id="test-session", session_update=mock_session_update
    )

    await handler.on_tool_start("code_execution", {"code": "print('hello')"})
    mock_session_update.reset_mock()

    await handler.on_tool_result("code_execution", "hello\n")

    mock_session_update.assert_called_once()
    call_args = mock_session_update.call_args
    assert call_args[0][0] == "test-session"
    assert handler._current_tool_id is None


@pytest.mark.asyncio
async def test_stream_handler_tracks_buffer():
    """Test that stream handler tracks accumulated text in buffer."""
    from python.helpers.acp_stream_handler import ACPStreamHandler, ACP_AVAILABLE

    if not ACP_AVAILABLE:
        pytest.skip("ACP SDK not installed")

    mock_session_update = AsyncMock()
    handler = ACPStreamHandler(
        session_id="test-session", session_update=mock_session_update
    )

    await handler.on_response_chunk("Hello", "Hello")
    assert handler._buffer == "Hello"

    await handler.on_response_chunk(" World", "Hello World")
    assert handler._buffer == "Hello World"


@pytest.mark.asyncio
async def test_stream_handler_no_op_when_acp_unavailable():
    """Test that handler methods are no-ops when ACP is unavailable."""
    from python.helpers import acp_stream_handler

    original = acp_stream_handler.ACP_AVAILABLE
    try:
        acp_stream_handler.ACP_AVAILABLE = False

        mock_session_update = AsyncMock()
        handler = acp_stream_handler.ACPStreamHandler(
            session_id="test-session", session_update=mock_session_update
        )

        await handler.on_response_chunk("Hello", "Hello")
        await handler.on_reasoning_chunk("Thinking", "Thinking")
        await handler.on_tool_start("test", {})
        await handler.on_tool_result("test", "result")

        mock_session_update.assert_not_called()
    finally:
        acp_stream_handler.ACP_AVAILABLE = original
