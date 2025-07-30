from python.helpers.api import ApiHandler, Request, Response
from python.api.agents_list import cleanup_orphaned_subordinates
from python.api.agent_flow import flow_tracker


class CleanupAgents(ApiHandler):
    """API handler for cleaning up orphaned agents and old flows."""
    
    @classmethod
    def requires_auth(cls) -> bool:
        return False
    
    async def process(self, input: dict, request: Request) -> dict | Response:
        """Handle cleanup requests."""
        try:
            cleanup_type = input.get("type", "all")
            results = {}
            
            if cleanup_type in ["all", "agents"]:
                # Clean up orphaned subordinate agents
                orphaned_count = cleanup_orphaned_subordinates()
                results["orphaned_agents_cleaned"] = orphaned_count
            
            if cleanup_type in ["all", "flows"]:
                # Clean up old flows (older than 24 hours)
                old_flows_count = flow_tracker.cleanup_old_flows(max_age_hours=24)
                results["old_flows_cleaned"] = old_flows_count
            
            return {
                "success": True,
                "message": f"Cleanup completed successfully",
                "results": results
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": "Cleanup failed"
            }
