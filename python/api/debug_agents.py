from python.helpers.api import ApiHandler, Request, Response
from python.api.agents_list import active_subordinate_agents


class DebugAgents(ApiHandler):
    """Debug endpoint to check subordinate agents registry."""
    
    @classmethod
    def requires_auth(cls) -> bool:
        return False
    
    async def process(self, input: dict, request: Request) -> dict | Response:
        """Debug subordinate agents registry."""
        try:
            return {
                "success": True,
                "active_subordinate_agents": dict(active_subordinate_agents),
                "count": len(active_subordinate_agents)
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }