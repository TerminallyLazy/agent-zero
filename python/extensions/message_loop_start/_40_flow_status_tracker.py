from python.helpers.extension import Extension
from agent import LoopData


class FlowStatusTracker(Extension):
    """Extension to track agent status updates in the flow visualization system."""

    async def execute(self, loop_data: LoopData = LoopData(), **kwargs):
        """Update agent status in the flow system during message loop."""
        try:
            from python.api.agent_flow import flow_tracker
            
            # Get flow ID for this agent
            flow_id = self.agent.get_data("_flow_id")
            if not flow_id:
                return
            
            # Update agent status based on loop iteration
            if loop_data.iteration == 1:
                # Agent is starting to process
                flow_tracker.update_agent_status(
                    flow_id, 
                    self.agent.agent_name, 
                    "running", 
                    10,  # 10% progress at start
                    "Processing user message"
                )
            elif loop_data.iteration > 1:
                # Agent is actively processing
                progress = min(90, 10 + (loop_data.iteration - 1) * 10)  # Cap at 90%
                flow_tracker.update_agent_status(
                    flow_id, 
                    self.agent.agent_name, 
                    "running", 
                    progress,
                    f"Processing (iteration {loop_data.iteration})"
                )
            
        except Exception as e:
            print(f"DEBUG: Error in FlowStatusTracker extension: {e}", flush=True)
