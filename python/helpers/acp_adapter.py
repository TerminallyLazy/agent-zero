# noqa: D401 (docstrings) - internal helper
"""ACP (Agent Client Protocol) adapter for Agent Zero.

This module provides an ACP-compliant adapter that exposes Agent Zero's
capabilities to ACP clients while maintaining full compatibility with
Agent Zero's existing architecture and patterns.
"""

import asyncio
import uuid
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

    def text_block(text: str) -> dict:
        raise RuntimeError("ACP SDK not available")

    def update_agent_message_text(text: str) -> dict:
        raise RuntimeError("ACP SDK not available")

    def update_agent_thought_text(text: str) -> dict:
        raise RuntimeError("ACP SDK not available")


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

    async def new_session(
        self, cwd: str = "", mcp_servers: list | None = None, **kwargs
    ) -> "NewSessionResponse":
        """Create a new ACP session mapped to an Agent Zero context."""
        if not ACP_AVAILABLE:
            raise RuntimeError("ACP SDK not available")

        from agent import AgentContext, AgentContextType
        from initialize import initialize_agent

        acp_session_id = str(uuid.uuid4())
        config = initialize_agent()
        context = AgentContext(config, type=AgentContextType.BACKGROUND)

        if cwd:
            context.data["acp_cwd"] = cwd
        if mcp_servers:
            context.data["acp_mcp_servers"] = mcp_servers

        self._sessions[acp_session_id] = context.id
        _PRINTER.print(
            f"[ACP] Created session {acp_session_id} -> context {context.id}"
        )

        return NewSessionResponse(session_id=acp_session_id)

    async def end_session(self, session_id: str) -> None:
        """End an ACP session and clean up the Agent Zero context."""
        from agent import AgentContext
        from python.helpers.persist_chat import remove_chat

        context_id = self._sessions.pop(session_id, None)
        if context_id:
            context = AgentContext.get(context_id)
            if context:
                context.reset()
                AgentContext.remove(context_id)
                remove_chat(context_id)
                _PRINTER.print(
                    f"[ACP] Ended session {session_id}, cleaned up context {context_id}"
                )
        else:
            _PRINTER.print(f"[ACP] Session {session_id} not found for cleanup")


def is_available() -> bool:
    """Check if ACP SDK is available."""
    return ACP_AVAILABLE
