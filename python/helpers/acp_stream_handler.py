# noqa: D401 (docstrings) - internal helper
"""ACP Stream Handler for Agent Zero.

Captures Agent Zero's streaming output and converts it to ACP session updates.
"""

from typing import Any, Callable, Coroutine
import uuid

from python.helpers.print_style import PrintStyle

try:
    from acp import (
        update_agent_message_text,
        update_agent_thought_text,
        start_tool_call,
        update_tool_call,
    )

    ACP_AVAILABLE = True
except ImportError:
    ACP_AVAILABLE = False

    def update_agent_message_text(text: str) -> dict:
        raise RuntimeError("ACP SDK not available")

    def update_agent_thought_text(text: str) -> dict:
        raise RuntimeError("ACP SDK not available")

    def start_tool_call(tool_call_id: str, title: str, **kwargs) -> dict:
        raise RuntimeError("ACP SDK not available")

    def update_tool_call(tool_call_id: str, **kwargs) -> dict:
        raise RuntimeError("ACP SDK not available")


_PRINTER = PrintStyle(italic=True, font_color="cyan", padding=False)


class ACPStreamHandler:
    def __init__(
        self,
        session_id: str,
        session_update: Callable[[str, Any], Coroutine[Any, Any, None]],
    ):
        self.session_id = session_id
        self._session_update = session_update
        self._buffer = ""
        self._reasoning_buffer = ""
        self._current_tool_id: str | None = None

    async def on_response_chunk(self, chunk: str, full: str) -> None:
        if not ACP_AVAILABLE:
            return

        self._buffer = full

        update = update_agent_message_text(chunk)
        await self._session_update(self.session_id, update)

    async def on_reasoning_chunk(self, chunk: str, full: str) -> None:
        if not ACP_AVAILABLE:
            return

        self._reasoning_buffer = full

        update = update_agent_thought_text(chunk)
        await self._session_update(self.session_id, update)

    async def on_tool_start(self, tool_name: str, tool_args: dict) -> None:
        if not ACP_AVAILABLE:
            return

        self._current_tool_id = str(uuid.uuid4())

        update = start_tool_call(
            tool_call_id=self._current_tool_id,
            title=tool_name,
            raw_input=tool_args,
        )
        await self._session_update(self.session_id, update)

    async def on_tool_result(self, tool_name: str, result: str) -> None:
        if not ACP_AVAILABLE:
            return

        tool_id = self._current_tool_id
        self._current_tool_id = None

        if tool_id is None:
            return

        update = update_tool_call(
            tool_call_id=tool_id,
            title=tool_name,
            raw_output=result,
        )
        await self._session_update(self.session_id, update)
