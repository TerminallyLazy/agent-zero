# tests/test_qmd_tools.py
"""Tests for QMD agent tools using mocked QMDClient."""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass
from typing import Any


# ---------------------------------------------------------------------------
# Stub the Agent Zero framework modules that require heavy deps (litellm, etc.)
# This mirrors the pattern used to keep tool tests self-contained.
# ---------------------------------------------------------------------------

@dataclass
class _Response:
    message: str
    break_loop: bool
    additional: dict[str, Any] | None = None


class _Tool:
    def __init__(self, agent, name, method, args, message, loop_data, **kwargs):
        self.agent = agent
        self.name = name
        self.method = method
        self.args = args
        self.message = message
        self.loop_data = loop_data


_tool_module = MagicMock()
_tool_module.Tool = _Tool
_tool_module.Response = _Response

sys.modules.setdefault("helpers.tool", _tool_module)

# helpers.plugins is needed by client_access but can be fully mocked here;
# the test patches get_or_create_client so plugins is never actually called.
_plugins_module = MagicMock()
sys.modules.setdefault("helpers.plugins", _plugins_module)

# helpers itself (needed so "from helpers import plugins" resolves)
_helpers_module = MagicMock()
_helpers_module.plugins = _plugins_module
sys.modules.setdefault("helpers", _helpers_module)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_agent():
    """Create a minimal mock agent."""
    agent = MagicMock()
    agent.get_data.return_value = None
    return agent


def _make_tool(tool_class, agent, args=None):
    """Instantiate a tool with a mock agent."""
    return tool_class(
        agent=agent,
        name="test",
        method=None,
        args=args or {},
        message="test",
        loop_data=None,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_status_tool_returns_message():
    """Status tool formats collections correctly."""
    from usr.plugins.qmd.tools.qmd_status import QMDStatus

    agent = _make_agent()
    mock_client = AsyncMock()
    mock_client.is_running.return_value = True
    mock_client.call.return_value = {
        "collections": [
            {"name": "notes", "doc_count": 42},
            {"name": "docs", "doc_count": 100},
        ]
    }

    with patch("usr.plugins.qmd.tools.qmd_status.get_or_create_client", new=AsyncMock(return_value=mock_client)):
        tool = _make_tool(QMDStatus, agent)
        response = await tool.execute()

    assert "QMD Index Status" in response.message
    assert "notes" in response.message
    assert "42" in response.message
    assert response.break_loop is False


@pytest.mark.asyncio
async def test_search_tool_returns_results():
    """Search tool formats results with title, path, docid, score."""
    from usr.plugins.qmd.tools.qmd_search import QMDSearch

    agent = _make_agent()
    mock_client = AsyncMock()
    mock_client.call.return_value = {
        "items": [
            {
                "title": "Authentication Guide",
                "path": "/notes/auth.md",
                "id": "abc123",
                "score": 0.87,
                "snippet": "This guide covers authentication patterns.",
            }
        ]
    }

    with patch("usr.plugins.qmd.tools.qmd_search.get_or_create_client", new=AsyncMock(return_value=mock_client)):
        tool = _make_tool(QMDSearch, agent, args={"q": "authentication", "mode": "query"})
        response = await tool.execute()

    assert "Authentication Guide" in response.message
    assert "#abc123" in response.message
    assert "87%" in response.message
    assert response.break_loop is False


@pytest.mark.asyncio
async def test_search_tool_no_results():
    """Search tool returns 'No results found.' for empty results."""
    from usr.plugins.qmd.tools.qmd_search import QMDSearch

    agent = _make_agent()
    mock_client = AsyncMock()
    mock_client.call.return_value = {"items": []}

    with patch("usr.plugins.qmd.tools.qmd_search.get_or_create_client", new=AsyncMock(return_value=mock_client)):
        tool = _make_tool(QMDSearch, agent, args={"q": "nothing"})
        response = await tool.execute()

    assert "No results found." in response.message
