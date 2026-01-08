from python.helpers.extension import Extension


class ACPToolResult(Extension):
    async def execute(
        self, tool_name: str = "", response: object | None = None, **kwargs
    ):
        handler = self.agent.data.get("_acp_stream_handler")
        if not handler:
            return

        result_text = ""
        if response and hasattr(response, "message"):
            result_text = str(response.message)

        await handler.on_tool_result(tool_name, result_text)
