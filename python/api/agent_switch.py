from python.helpers.api import ApiHandler, Request, Response
from python.extensions.message_loop_start._35_sub_agent_manager import (
    get_sub_agents, SubAgentInfo, register_sub_agent
)
from python.tools.agent_bridge import discover_agent, AgentCapabilities
from agent import AgentContext, Agent
from datetime import datetime, timezone
from typing import Dict, Any, Optional


class AgentSwitch(ApiHandler):
    
    async def process(self, input: dict, request: Request) -> dict | Response:
        """
        Switch to a different agent context.
        
        Args:
            input: {
                'context': str - Current context ID
                'target_agent_id': str - ID of target agent to switch to
            }
            
        Returns:
            dict: {
                'success': bool,
                'agent_info': dict,
                'error': str (optional)
            }
        """
        try:
            ctxid = input.get("context", None)
            target_agent_id = input.get("target_agent_id", None)
            
            if not target_agent_id:
                return {
                    "success": False,
                    "error": "target_agent_id is required"
                }
            
            context = self.get_context(ctxid)
            agent = context.agent
            
            # Handle main agent switch
            if target_agent_id == "main":
                agent_info = {
                    "id": "main",
                    "type": "main",
                    "name": "Agent Zero",
                    "role": "main",
                    "status": "active",
                    "endpoint": "local",
                    "capabilities": ["reasoning", "tools", "memory", "planning"],
                    "last_contact": datetime.now(timezone.utc).isoformat(),
                    "task_count": 0,
                    "url": None
                }
                
                # Reset to main agent context
                await self._switch_to_main_agent(context)
                
                return {
                    "success": True,
                    "agent_info": agent_info
                }
            
            # Handle subordinate agent switch
            from python.api.agents_list import active_subordinate_agents
            
            if target_agent_id not in active_subordinate_agents:
                return {
                    "success": False,
                    "error": f"Agent {target_agent_id} not found or not active"
                }
            
            target_agent_data = active_subordinate_agents[target_agent_id]
            
            # Check if agent is online
            if target_agent_data["status"] not in ["working", "idle", "active"]:
                return {
                    "success": False,
                    "error": f"Agent {target_agent_id} is not available (status: {target_agent_data['status']})"
                }
            
            # Build agent info for response (use our new registry format)
            agent_info = target_agent_data.copy()
            
            # Set the active agent context for message routing
            await self._switch_to_subordinate_agent(context, target_agent_data, agent_info)
            
            # Store agent info for UI state persistence and routing
            context.set_data("selected_agent_id", target_agent_id)
            context.set_data("selected_agent_info", agent_info)
            context.set_data("agent_routing_enabled", True)
            context.set_data("subordinate_agent_endpoint", target_agent_data["endpoint"])
            
            return {
                "success": True,
                "agent_info": agent_info
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _switch_to_main_agent(self, context: AgentContext):
        """Switch back to the main agent context."""
        # Clear subordinate agent routing
        context.set_data("agent_routing_enabled", False)
        context.set_data("subordinate_agent_endpoint", None)
        context.set_data("selected_agent_id", "main")
        
        # Reset any agent bridge data
        context.agent.set_data("agent_bridge_target", None)
        
        # Log the switch
        context.log.log(
            type="system",
            heading="Agent Switch",
            content="Switched back to main agent (Agent Zero)",
            kvps={"target": "main", "action": "switch"}
        )
    
    async def _switch_to_subordinate_agent(
        self, 
        context: AgentContext, 
        target_agent_data: Dict[str, Any], 
        agent_info: Dict[str, Any]
    ):
        """Switch to a subordinate agent context."""
        try:
            # Enable agent routing
            context.set_data("agent_routing_enabled", True)
            context.set_data("subordinate_agent_endpoint", target_agent_data["endpoint"])
            
            # Set up agent bridge for message routing
            context.agent.set_data("agent_bridge_target", {
                "endpoint": target_agent_data["endpoint"],
                "agent_id": target_agent_data["id"],
                "capabilities": target_agent_data["capabilities"]
            })
            
            # Log the switch
            context.log.log(
                type="system",
                heading="Agent Switch",
                content=f"Switched to subordinate agent: {agent_info['name']}",
                kvps={
                    "target": target_agent_data["id"],
                    "endpoint": target_agent_data["endpoint"],
                    "action": "switch"
                }
            )
            
        except Exception as e:
            # If switch fails, ensure we stay on main agent
            await self._switch_to_main_agent(context)
            raise ValueError(f"Failed to switch to agent {target_agent_data['id']}: {str(e)}")