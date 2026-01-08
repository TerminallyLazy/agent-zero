"""ACP reasoning stream extension.

Hooks into Agent Zero's reasoning streaming to send thoughts to ACP clients.
"""

from python.helpers.extension import Extension


class ACPReasoningStream(Extension):
    """Extension that forwards reasoning chunks to ACP clients."""

    async def execute(self, **kwargs):
        """Forward reasoning chunks to ACP stream handler if active."""
        stream_data = kwargs.get("stream_data")
        if not stream_data:
            return

        # Check if this agent has an active ACP stream handler
        handler = self.agent.data.get("_acp_stream_handler")
        if not handler:
            return

        chunk = stream_data.get("chunk", "")
        full = stream_data.get("full", "")

        if chunk:
            await handler.on_reasoning_chunk(chunk, full)
