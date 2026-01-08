"""ACP response stream extension.

Hooks into Agent Zero's response streaming to send real-time updates to ACP clients.
"""

from python.helpers.extension import Extension


class ACPResponseStream(Extension):
    """Extension that forwards response stream chunks to ACP clients."""

    async def execute(self, **kwargs):
        """Forward response chunks to ACP stream handler if active."""
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
            await handler.on_response_chunk(chunk, full)
