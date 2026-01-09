from python.helpers.extension import Extension


class ACPResponseStream(Extension):
    """Disabled - Agent Zero's raw JSON output is not suitable for streaming.

    The final clean response is sent via acp_adapter.py after processing completes.
    Tool calls are shown via the tool_execute_before/after extensions.
    """

    async def execute(self, **kwargs):
        pass
