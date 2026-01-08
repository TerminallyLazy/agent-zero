# noqa: D401 (docstrings) - internal helper
"""ACP (Agent Client Protocol) adapter for Agent Zero.

This module provides an ACP-compliant adapter that exposes Agent Zero's
capabilities to ACP clients while maintaining full compatibility with
Agent Zero's existing architecture and patterns.
"""

import asyncio
from typing import Any, AsyncIterator

from python.helpers.print_style import PrintStyle

try:
    from acp import Agent as ACPAgent
    from acp import (
        InitializeResponse,
        NewSessionResponse,
        PromptResponse,
        text_block,
        update_agent_message_text,
        update_agent_thought_text,
    )

    ACP_AVAILABLE = True
except ImportError:
    ACP_AVAILABLE = False
    ACPAgent = object  # type: ignore
    InitializeResponse = Any  # type: ignore
    NewSessionResponse = Any  # type: ignore
    PromptResponse = Any  # type: ignore

_PRINTER = PrintStyle(italic=True, font_color="cyan", padding=False)


class AgentZeroACP(ACPAgent if ACP_AVAILABLE else object):  # type: ignore[misc]
    """ACP Agent implementation wrapping Agent Zero."""

    def __init__(self):
        self._sessions: dict[str, str] = {}  # acp_session_id -> agent_context_id
        self.connection = None  # Set by ACP runtime for streaming

    async def initialize(self, protocol_version: int, **kwargs) -> "InitializeResponse":
        """Handle ACP initialization and version negotiation."""
        if not ACP_AVAILABLE:
            raise RuntimeError("ACP SDK not available")

        _PRINTER.print(f"[ACP] Initializing with protocol version {protocol_version}")
        return InitializeResponse(protocol_version=protocol_version)


def is_available() -> bool:
    """Check if ACP SDK is available."""
    return ACP_AVAILABLE
