from python.helpers.extension import Extension
import uuid


class FlowTracker(Extension):
    """Extension to track agent creation in the flow visualization system."""

    async def execute(self, **kwargs):
        """Track agent creation in the flow system."""
        try:
            from python.api.agent_flow import flow_tracker
            
            # Only track subordinate agents (not the main agent)
            if self.agent.number == 0:
                return
            
            # Get or create flow ID for this agent hierarchy
            superior = self.agent.get_data(self.agent.DATA_NAME_SUPERIOR)
            if not superior:
                return
            
            # Create a flow ID based on the superior agent
            flow_id = superior.get_data("_flow_id")
            if not flow_id:
                flow_id = f"flow_{superior.agent_name}_{uuid.uuid4().hex[:8]}"
                superior.set_data("_flow_id", flow_id)
                
                # Create the flow if it doesn't exist
                if not flow_tracker.get_flow(flow_id):
                    flow_tracker.create_flow(
                        flow_id=flow_id,
                        parent_agent=superior.agent_name,
                        task_description=f"Agent {superior.agent_name} delegation hierarchy"
                    )
                    
                    # Add the superior agent to the flow
                    flow_tracker.add_agent_to_flow(flow_id, {
                        "id": superior.agent_name,
                        "name": f"Agent {superior.agent_name}",
                        "type": "main" if superior.number == 0 else "subordinate",
                        "role": "coordinator",
                        "status": "active",
                        "endpoint": "local"
                    })
            
            # Inherit flow_id from superior
            self.agent.set_data("_flow_id", flow_id)
            
            # Add this agent to the flow
            agent_profile = getattr(self.agent.config, 'profile', 'default') or 'default'
            flow_tracker.add_agent_to_flow(flow_id, {
                "id": self.agent.agent_name,
                "name": f"Agent {self.agent.agent_name}",
                "type": "subordinate",
                "role": agent_profile,
                "status": "initializing",
                "endpoint": "local"
            })
            
            # Add connection from superior to this agent
            flow_tracker.add_connection(flow_id, superior.agent_name, self.agent.agent_name, "task_delegation")
            
            print(f"DEBUG: Added agent {self.agent.agent_name} to flow {flow_id}", flush=True)
            
        except Exception as e:
            print(f"DEBUG: Error in FlowTracker extension: {e}", flush=True)
