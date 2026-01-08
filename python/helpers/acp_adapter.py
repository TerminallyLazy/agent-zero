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

        acp_session_id = str(uuid.uuid4())

        try:
            from agent import AgentContext, AgentContextType
            from initialize import initialize_agent

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

        except Exception as e:
            _PRINTER.print(f"[ACP] Failed to create session: {e}")
            raise

    def _convert_content_blocks(self, blocks: list[Any]) -> "UserMessage":
        from agent import UserMessage

        text_parts: list[str] = []
        attachments: list[str] = []

        for block in blocks:
            block_type = (
                block.get("type")
                if isinstance(block, dict)
                else getattr(block, "type", None)
            )

            if block_type == "text":
                text = (
                    block.get("text", "")
                    if isinstance(block, dict)
                    else getattr(block, "text", "")
                )
                text_parts.append(text)
            elif block_type == "image":
                url = (
                    block.get("url")
                    if isinstance(block, dict)
                    else getattr(block, "url", None)
                )
                if url:
                    attachments.append(url)
            elif block_type in ("resource", "resource_link"):
                uri = (
                    block.get("uri")
                    if isinstance(block, dict)
                    else getattr(block, "uri", None)
                )
                if uri:
                    attachments.append(uri)

        message_text = "\n".join(text_parts)

        return UserMessage(message=message_text, attachments=attachments)

    async def end_session(self, session_id: str) -> None:
        """End an ACP session and clean up the Agent Zero context."""
        context_id = self._sessions.pop(session_id, None)
        if context_id:
            from agent import AgentContext
            from python.helpers.persist_chat import remove_chat

            context = AgentContext.get(context_id)
            if context:
                try:
                    context.reset()
                finally:
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
