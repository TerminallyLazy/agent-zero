# noqa: D401 (docstrings) - internal helper
"""ACP (Agent Client Protocol) adapter for Agent Zero."""

import uuid
from typing import Any

try:
    from acp import Agent as ACPAgent
    from acp import (
        InitializeResponse,
        NewSessionResponse,
        PromptResponse,
        update_agent_message_text,
    )

    ACP_AVAILABLE = True
except ImportError:
    ACP_AVAILABLE = False
    ACPAgent = object  # type: ignore
    InitializeResponse = Any  # type: ignore
    NewSessionResponse = Any  # type: ignore
    PromptResponse = Any  # type: ignore

    def update_agent_message_text(text: str) -> dict:
        raise RuntimeError("ACP SDK not available")


class AgentZeroACP(ACPAgent if ACP_AVAILABLE else object):  # type: ignore[misc]
    """ACP Agent implementation wrapping Agent Zero."""

    def __init__(self):
        self._sessions: dict[str, str] = {}
        self.connection = None

    def on_connect(self, conn) -> None:
        """Called by ACP runtime when a client connects."""
        self.connection = conn

    async def initialize(self, protocol_version: int, **kwargs) -> "InitializeResponse":
        if not ACP_AVAILABLE:
            raise RuntimeError("ACP SDK not available")
        return InitializeResponse(protocol_version=protocol_version)

    async def new_session(
        self, cwd: str = "", mcp_servers: list | None = None, **kwargs
    ) -> "NewSessionResponse":
        if not ACP_AVAILABLE:
            raise RuntimeError("ACP SDK not available")

        acp_session_id = str(uuid.uuid4())

        from agent import AgentContext, AgentContextType
        from initialize import initialize_agent

        config = initialize_agent()
        context = AgentContext(config, type=AgentContextType.BACKGROUND)

        if cwd:
            context.data["acp_cwd"] = cwd
        if mcp_servers:
            context.data["acp_mcp_servers"] = mcp_servers

        self._sessions[acp_session_id] = context.id
        return NewSessionResponse(session_id=acp_session_id)

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

    async def prompt(self, prompt: list, session_id: str, **kwargs) -> "PromptResponse":
        if not ACP_AVAILABLE:
            raise RuntimeError("ACP SDK not available")

        from agent import AgentContext

        context_id = self._sessions.get(session_id)
        if not context_id:
            raise ValueError(f"Unknown session: {session_id}")

        context = AgentContext.get(context_id)
        if not context:
            raise ValueError(f"Context not found for session: {session_id}")

        user_message = self._convert_content_blocks(prompt)

        # Get session_update callback from kwargs or self.connection
        session_update = kwargs.get("session_update")
        if session_update is None and self.connection:
            session_update = self.connection.session_update

        if session_update:
            from python.helpers.acp_stream_handler import ACPStreamHandler

            stream_handler = ACPStreamHandler(
                session_id=session_id,
                session_update=session_update,
            )
            context.agent0.data["_acp_stream_handler"] = stream_handler

        try:
            context.log.log(
                type="user",
                heading="ACP user message",
                content=user_message.message,
                kvps={"from": "ACP"},
                temp=False,
            )

            task = context.communicate(user_message)
            result_text = await task.result()

            if session_update:
                await session_update(
                    session_id, update_agent_message_text(str(result_text))
                )

            return PromptResponse(stop_reason="end_turn")

        finally:
            context.agent0.data.pop("_acp_stream_handler", None)

    async def cancel_prompt(self, session_id: str, **kwargs) -> None:
        from agent import AgentContext

        context_id = self._sessions.get(session_id)
        if context_id:
            context = AgentContext.get(context_id)
            if context:
                context.kill_process()

    async def end_session(self, session_id: str) -> None:
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


def is_available() -> bool:
    return ACP_AVAILABLE
