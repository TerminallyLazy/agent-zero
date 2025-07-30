"""
Integration helper between Agent Bridge and Agent Flow Tracker.
Provides utilities for creating and managing subordinate agents with flow visualization.
"""

import asyncio
import json
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone

from python.tools.agent_bridge import AgentBridge, AgentCapabilities, discover_agent
from python.api.agent_flow import AgentFlowTracker


class AgentFlowBridge:
    """
    Helper class that integrates Agent Bridge with Flow Tracker for
    creating and managing subordinate agents with real-time visualization.
    """
    
    def __init__(self, agent_context=None):
        self.agent_context = agent_context
        self.flow_tracker = AgentFlowTracker()
        self.active_subordinates: Dict[str, Dict[str, Any]] = {}  # flow_id -> agent_info
    
    async def create_subordinate_agent(self, 
                                     parent_agent_name: str,
                                     task_description: str,
                                     agent_endpoint: str,
                                     initial_message: str = None,
                                     timeout: float = 30) -> Dict[str, Any]:
        """
        Create a subordinate agent and track it in the flow visualization.
        
        Args:
            parent_agent_name: Name of the parent agent
            task_description: Description of the task for subordinate
            agent_endpoint: Endpoint URL of the subordinate agent
            initial_message: Initial message to send to the agent
            timeout: Communication timeout
            
        Returns:
            Dict containing flow_id, agent_id, and creation status
        """
        try:
            # Step 1: Discover the agent capabilities
            print(f"🔍 Discovering agent at {agent_endpoint}...")
            agent_capabilities = await discover_agent(agent_endpoint, timeout)
            
            if not agent_capabilities:
                return {
                    "success": False,
                    "error": f"Could not discover agent at {agent_endpoint}",
                    "flow_id": None,
                    "agent_id": None
                }
            
            print(f"✅ Discovered {agent_capabilities.protocol} agent: {agent_capabilities.agent_id}")
            
            # Step 2: Create flow with subordinate agent
            flow_id = self.flow_tracker.create_subordinate_agent_flow(
                parent_agent_name=parent_agent_name,
                task_description=task_description,
                agent_endpoint=agent_endpoint,
                agent_capabilities=agent_capabilities
            )
            
            agent_id = agent_capabilities.agent_id or f"subordinate_{flow_id[-8:]}"
            
            # Step 3: Store subordinate info for tracking
            self.active_subordinates[flow_id] = {
                "agent_id": agent_id,
                "endpoint": agent_endpoint,
                "capabilities": agent_capabilities,
                "parent_agent": parent_agent_name,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "status": "initializing"
            }
            
            # Step 4: Send initial message if provided
            if initial_message:
                await self.send_message_to_subordinate(flow_id, initial_message, timeout)
            
            return {
                "success": True,
                "flow_id": flow_id,
                "agent_id": agent_id,
                "protocol": agent_capabilities.protocol,
                "capabilities": agent_capabilities.capabilities,
                "message": f"Subordinate agent created and tracked in flow {flow_id}"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to create subordinate agent: {str(e)}",
                "flow_id": None,
                "agent_id": None
            }
    
    async def send_message_to_subordinate(self, 
                                        flow_id: str, 
                                        message: str, 
                                        timeout: float = 30) -> Dict[str, Any]:
        """
        Send a message to a subordinate agent and update flow tracking.
        
        Args:
            flow_id: ID of the flow containing the subordinate
            message: Message to send
            timeout: Communication timeout
            
        Returns:
            Dict containing response and updated status
        """
        if flow_id not in self.active_subordinates:
            return {
                "success": False,
                "error": f"No active subordinate found for flow {flow_id}"
            }
        
        subordinate_info = self.active_subordinates[flow_id]
        agent_id = subordinate_info["agent_id"]
        endpoint = subordinate_info["endpoint"]
        
        try:
            # Create agent bridge instance
            bridge = AgentBridge(
                agent=self.agent_context,
                name="agent_bridge",
                method=None,
                args={
                    "endpoint": endpoint,
                    "action": "send",
                    "message": message,
                    "timeout": str(timeout)
                },
                message="",
                loop_data=None
            )
            
            # Send message
            print(f"📤 Sending message to subordinate {agent_id}...")
            response = await bridge.execute()
            
            # Parse response
            if response.message:
                try:
                    bridge_response = json.loads(response.message)
                    
                    # Update flow tracker with response
                    self.flow_tracker.update_subordinate_agent_from_bridge(
                        flow_id, agent_id, bridge_response
                    )
                    
                    # Update local tracking
                    subordinate_info["status"] = "active"
                    subordinate_info["last_message"] = message
                    subordinate_info["last_response"] = bridge_response
                    subordinate_info["last_communication"] = datetime.now(timezone.utc).isoformat()
                    
                    return {
                        "success": True,
                        "response": bridge_response,
                        "agent_id": agent_id,
                        "flow_id": flow_id
                    }
                    
                except json.JSONDecodeError:
                    return {
                        "success": False,
                        "error": "Invalid JSON response from agent bridge",
                        "raw_response": response.message
                    }
            else:
                return {
                    "success": False,
                    "error": "Empty response from agent bridge"
                }
                
        except Exception as e:
            # Update flow tracker with failure
            self.flow_tracker.update_subordinate_agent_from_bridge(
                flow_id, agent_id, {"status": 500, "error": str(e)}
            )
            
            return {
                "success": False,
                "error": f"Failed to communicate with subordinate: {str(e)}"
            }
    
    async def complete_subordinate_task(self, 
                                      flow_id: str, 
                                      success: bool = True,
                                      final_message: str = None) -> Dict[str, Any]:
        """
        Mark a subordinate agent task as completed and clean up.
        
        Args:
            flow_id: ID of the flow containing the subordinate
            success: Whether the task completed successfully
            final_message: Optional final message to send
            
        Returns:
            Dict containing completion status
        """
        if flow_id not in self.active_subordinates:
            return {
                "success": False,
                "error": f"No active subordinate found for flow {flow_id}"
            }
        
        subordinate_info = self.active_subordinates[flow_id]
        agent_id = subordinate_info["agent_id"]
        
        try:
            # Send final message if provided
            if final_message:
                await self.send_message_to_subordinate(flow_id, final_message)
            
            # Mark as completed in flow tracker
            self.flow_tracker.complete_subordinate_agent(flow_id, agent_id, success)
            
            # Update local tracking
            subordinate_info["status"] = "completed" if success else "failed"
            subordinate_info["completed_at"] = datetime.now(timezone.utc).isoformat()
            
            # Schedule cleanup (remove from active tracking after delay)
            asyncio.create_task(self._cleanup_subordinate(flow_id, delay=60))
            
            return {
                "success": True,
                "flow_id": flow_id,
                "agent_id": agent_id,
                "status": "completed" if success else "failed",
                "message": f"Subordinate agent {agent_id} marked as {'completed' if success else 'failed'}"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to complete subordinate task: {str(e)}"
            }
    
    async def _cleanup_subordinate(self, flow_id: str, delay: int = 60):
        """Clean up subordinate tracking after delay."""
        await asyncio.sleep(delay)
        if flow_id in self.active_subordinates:
            print(f"🧹 Cleaning up subordinate tracking for flow {flow_id}")
            del self.active_subordinates[flow_id]
    
    def get_active_subordinates(self) -> Dict[str, Dict[str, Any]]:
        """Get all currently active subordinate agents."""
        return self.active_subordinates.copy()
    
    def get_subordinate_status(self, flow_id: str) -> Optional[Dict[str, Any]]:
        """Get status of a specific subordinate agent."""
        return self.active_subordinates.get(flow_id)


# Global instance for easy access
agent_flow_bridge = AgentFlowBridge()


# Convenience functions
async def create_subordinate_agent(parent_agent_name: str,
                                 task_description: str,
                                 agent_endpoint: str,
                                 initial_message: str = None,
                                 timeout: float = 30) -> Dict[str, Any]:
    """Convenience function to create a subordinate agent with flow tracking."""
    return await agent_flow_bridge.create_subordinate_agent(
        parent_agent_name, task_description, agent_endpoint, initial_message, timeout
    )


async def send_to_subordinate(flow_id: str, message: str, timeout: float = 30) -> Dict[str, Any]:
    """Convenience function to send message to subordinate agent."""
    return await agent_flow_bridge.send_message_to_subordinate(flow_id, message, timeout)


async def complete_subordinate(flow_id: str, success: bool = True, final_message: str = None) -> Dict[str, Any]:
    """Convenience function to complete subordinate agent task."""
    return await agent_flow_bridge.complete_subordinate_task(flow_id, success, final_message)
