import asyncio
from datetime import datetime, timezone
from python.helpers.extension import Extension
from agent import Agent, LoopData


class SubordinateCleanup(Extension):
    """Extension to periodically clean up orphaned subordinate agents and old flows."""
    
    def __init__(self, agent: Agent):
        super().__init__(agent)
        self.last_cleanup = None
        self.cleanup_interval = 300  # 5 minutes
    
    async def execute(self, loop_data: LoopData = LoopData(), **kwargs):
        """
        Execute periodic cleanup during message loop start.
        
        This method runs cleanup every 5 minutes to:
        1. Remove orphaned subordinate agents
        2. Archive completed flows
        3. Clean up old flow data
        """
        current_time = datetime.now(timezone.utc)
        
        # Only run cleanup every 5 minutes
        if (self.last_cleanup is None or 
            (current_time - self.last_cleanup).total_seconds() >= self.cleanup_interval):
            
            await self._perform_cleanup()
            self.last_cleanup = current_time
    
    async def _perform_cleanup(self):
        """Perform the actual cleanup operations."""
        try:
            # Clean up orphaned subordinate agents
            from python.api.agents_list import cleanup_orphaned_subordinates
            orphaned_count = cleanup_orphaned_subordinates()
            
            if orphaned_count > 0:
                print(f"Cleaned up {orphaned_count} orphaned subordinate agents")
            
            # Clean up old flows
            from python.api.agent_flow import flow_tracker
            old_flows_count = flow_tracker.cleanup_old_flows(max_age_hours=2)  # 2 hours for automatic cleanup
            
            if old_flows_count > 0:
                print(f"Cleaned up {old_flows_count} old flows")
            
            # Clean up completed subordinate agent references
            await self._cleanup_completed_subordinates()
            
        except Exception as e:
            print(f"Error during periodic cleanup: {e}")
    
    async def _cleanup_completed_subordinates(self):
        """Clean up completed subordinate agent references from parent agents."""
        try:
            # Check if this agent has a completed subordinate
            subordinate = self.agent.get_data(Agent.DATA_NAME_SUBORDINATE)
            
            if subordinate:
                # Check if subordinate has been idle for too long
                subordinate_data = getattr(subordinate, 'data', {})
                created_at = subordinate_data.get('created_at')
                
                if created_at:
                    try:
                        created_time = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                        age_minutes = (datetime.now(timezone.utc) - created_time).total_seconds() / 60
                        
                        # If subordinate is older than 10 minutes and not actively being used
                        if age_minutes > 10:
                            # Check if subordinate has recent activity
                            last_message_time = getattr(subordinate, 'last_message_time', None)
                            
                            if (not last_message_time or 
                                (datetime.now(timezone.utc) - last_message_time).total_seconds() > 600):
                                
                                # Clean up the subordinate reference
                                self.agent.set_data(Agent.DATA_NAME_SUBORDINATE, None)
                                print(f"Cleaned up idle subordinate reference for agent {self.agent.agent_name}")
                    
                    except Exception as e:
                        print(f"Error parsing subordinate creation time: {e}")
        
        except Exception as e:
            print(f"Error cleaning up subordinate references: {e}")
