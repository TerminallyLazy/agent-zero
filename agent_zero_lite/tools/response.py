from helpers.tool import Tool, Response


class ResponseTool(Tool):
    """
    Tool for providing a final response to the user.
    """
    async def execute(self, **kwargs):
        text = self.args.get("text", "") or self.args.get("message", "")
        return Response(message=text, break_loop=True)

    async def before_execution(self, **kwargs):
        # Minimal implementation - just print the tool name
        print(f"{self.agent.agent_name}: Responding to user")

    async def after_execution(self, response, **kwargs):
        # Don't add to history or do any additional processing
        pass