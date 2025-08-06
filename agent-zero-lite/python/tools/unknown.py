from python.helpers.tool import Tool, Response


class Unknown(Tool):
    async def execute(self, **kwargs):
        # Simplified tools list for lite version
        tools_list = [
            "response - Provide final response to user", 
            "code_execution_tool - Execute Python/Node.js/terminal commands",
            "memory_save - Save information to memory",
            "memory_load - Load information from memory", 
            "document_query - Query uploaded documents",
            "call_subordinate - Create subordinate agent"
        ]
        tools_prompt = "\n".join([f"- {tool}" for tool in tools_list])
        
        return Response(
            message=self.agent.read_prompt(
                "fw.tool_not_found.md", tool_name=self.name, tools_prompt=tools_prompt
            ),
            break_loop=False,
        )
