from python.helpers.api import ApiHandler, Request, Response


class AcpAgents(ApiHandler):
    """ACP Agents list endpoint."""
    
    @classmethod
    def requires_auth(cls) -> bool:
        return False
    
    @classmethod
    def get_methods(cls) -> list[str]:
        return ["GET", "POST"]
    
    async def process(self, input: dict, request: Request) -> dict | Response:
        return {
            "agents": [
                {
                    "name": "agent-zero",
                    "description": "Main Agent Zero instance",
                    "status": "active",
                    "capabilities": [
                        "reasoning", "tool_execution", "memory_management",
                        "planning", "sub_agent_creation"
                    ]
                }
            ]
        }