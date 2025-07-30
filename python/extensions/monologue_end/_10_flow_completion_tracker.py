from python.helpers.extension import Extension
from agent import LoopData


class FlowCompletionTracker(Extension):
    """Extension to track agent completion in the flow visualization system."""

    async def execute(self, loop_data: LoopData = LoopData(), **kwargs):
        """Mark agent as completed in the flow system when monologue ends."""
        try:
            from python.api.agent_flow import flow_tracker
            
            # Get flow ID for this agent
            flow_id = self.agent.get_data("_flow_id")
            if not flow_id:
                return
            
            # Mark agent as completed
            flow_tracker.update_agent_status(
                flow_id, 
                self.agent.agent_name, 
                "completed", 
                100,
                "Task completed"
            )
            
            print(f"DEBUG: Marked agent {self.agent.agent_name} as completed in flow {flow_id}", flush=True)
            
        except Exception as e:
            print(f"DEBUG: Error in FlowCompletionTracker extension: {e}", flush=True)
