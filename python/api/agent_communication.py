from python.helpers.api import ApiHandler, Request, Response
from datetime import datetime, timezone
from typing import Dict, List, Any
import json
import uuid


class AgentCommunication(ApiHandler):
    """API handler for A2A/ACP agent-to-agent communication."""
    
    @classmethod
    def requires_auth(cls) -> bool:
        return False
    
    async def process(self, input: dict, request: Request) -> dict | Response:
        """Handle agent communication requests (A2A/ACP protocol)."""
        try:
            action = input.get("action", "send")
            
            if action == "send":
                return await self._handle_send_message(input)
            elif action == "discover":
                return await self._handle_discover_agents(input)
            elif action == "get_agent_card":
                return await self._handle_get_agent_card(input)
            else:
                return {
                    "success": False,
                    "error": f"Unknown action: {action}"
                }
        
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _handle_send_message(self, input: dict) -> dict:
        """Handle sending a message to another agent."""
        from_agent = input.get("from_agent")
        to_agent = input.get("to_agent")
        message = input.get("message", "")
        
        if not from_agent or not to_agent:
            return {
                "success": False,
                "error": "from_agent and to_agent required"
            }
        
        # Get subordinate agents registry
        from python.api.agents_list import get_subordinate_agents, update_subordinate_agent
        subordinate_agents = get_subordinate_agents()
        
        # Find target agent
        target_agent = None
        for agent in subordinate_agents:
            if agent["id"] == to_agent or agent["name"] == to_agent:
                target_agent = agent
                break
        
        if not target_agent:
            return {
                "success": False,
                "error": f"Target agent {to_agent} not found"
            }
        
        # For now, we'll simulate message delivery by updating agent status
        # In a full implementation, this would route to the actual agent process
        message_id = str(uuid.uuid4())
        
        # Update target agent with new message
        update_subordinate_agent(target_agent["id"], {
            "task_count": target_agent.get("task_count", 0) + 1,
            "status": "working"
        })
        
        # Log the communication in flow tracking
        from python.api.agent_flow import flow_tracker
        # Create a communication flow
        comm_flow_id = str(uuid.uuid4())
        flow_tracker.create_flow(
            flow_id=comm_flow_id,
            parent_agent=from_agent,
            task_description=f"A2A Communication: {from_agent} → {to_agent}"
        )
        
        return {
            "success": True,
            "message_id": message_id,
            "status": "delivered",
            "target_agent": target_agent["name"],
            "communication_flow": comm_flow_id
        }
    
    async def _handle_discover_agents(self, input: dict) -> dict:
        """Handle agent discovery requests."""
        from python.api.agents_list import get_subordinate_agents
        
        subordinate_agents = get_subordinate_agents()
        
        # Filter out the requesting agent
        requesting_agent = input.get("requesting_agent")
        available_agents = [
            agent for agent in subordinate_agents 
            if agent["id"] != requesting_agent
        ]
        
        return {
            "success": True,
            "discovered_agents": available_agents,
            "total_agents": len(available_agents),
            "protocol": "A2A",
            "discovery_time": datetime.now(timezone.utc).isoformat()
        }
    
    async def _handle_get_agent_card(self, input: dict) -> dict:
        """Handle agent card requests (ACP protocol)."""
        agent_id = input.get("agent_id")
        
        if not agent_id:
            return {
                "success": False,
                "error": "agent_id required"
            }
        
        from python.api.agents_list import active_subordinate_agents
        
        if agent_id in active_subordinate_agents:
            agent = active_subordinate_agents[agent_id]
            return {
                "success": True,
                "agent_card": {
                    "id": agent["id"],
                    "name": agent["name"],
                    "role": agent["role"],
                    "capabilities": agent["capabilities"],
                    "status": agent["status"],
                    "protocol": agent["protocol"],
                    "endpoint": agent["endpoint"],
                    "created_at": agent["created_at"],
                    "last_contact": agent["last_contact"]
                }
            }
        else:
            return {
                "success": False,
                "error": f"Agent {agent_id} not found"
            }