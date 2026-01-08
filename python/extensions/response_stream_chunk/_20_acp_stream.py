from python.helpers.extension import Extension


class ACPResponseStream(Extension):
    async def execute(self, **kwargs):
        stream_data = kwargs.get("stream_data")
        if not stream_data:
            return

        handler = self.agent.data.get("_acp_stream_handler")
        if not handler:
            return

        chunk = stream_data.get("chunk", "")
        full = stream_data.get("full", "")

        if chunk:
            await handler.on_response_chunk(chunk, full)
