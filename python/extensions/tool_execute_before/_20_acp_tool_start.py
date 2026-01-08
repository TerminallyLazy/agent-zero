from python.helpers.extension import Extension


class ACPToolStart(Extension):
    async def execute(
        self, tool_name: str = "", tool_args: dict | None = None, **kwargs
    ):
        handler = self.agent.data.get("_acp_stream_handler")
        if not handler:
            return

        await handler.on_tool_start(tool_name, tool_args or {})
