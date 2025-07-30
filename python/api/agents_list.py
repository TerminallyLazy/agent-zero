from python.helpers.api import ApiHandler, Request, Response
from datetime import datetime, timezone
from typing import Dict, List, Any
import aiohttp
from python.api.agent_registry import get_registry

# Legacy global variable for backwards compatibility - DEPRECATED
# Use get_registry() instead
active_subordinate_agents = {}


class AgentsList(ApiHandler):
    
    @classmethod
    def requires_auth(cls) -> bool:
        return False
    
    async def process(self, input: dict, request: Request) -> dict | Response:
        """Return list of available agents including main agent and network agents."""
        print("DEBUG: AgentsList.process() called!", flush=True)
        try:
            agents = []
            
            # Main agent entry
            main_agent = {
                "id": "main",
                "type": "main",
                "name": "Agent Zero",
                "role": "main",
                "status": "active",
                "endpoint": "local",
                "capabilities": ["reasoning", "tools", "memory", "planning"],
                "last_contact": datetime.now(timezone.utc).isoformat(),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "task_count": 0,
                "url": None
            }
            agents.append(main_agent)
            
            # Add active subordinate agents using persistent registry
            registry = get_registry()
            print(f"DEBUG: AgentsList calling get_active_agents()", flush=True)
            subordinate_agents = registry.get_active_agents(max_age_seconds=300)
            print(f"DEBUG: AgentsList got {len(subordinate_agents)} subordinate agents", flush=True)
            agents.extend(subordinate_agents)
            
            statistics = {
                "total_agents": len(agents),
                "status_counts": {"active": len(agents)},
                "total_tasks": 0,
                "pending_tasks": 0,
                "online_agents": len(agents)
            }
            
            return {
                "success": True,
                "agents": agents,
                "active_agent": "main",
                "statistics": statistics
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "agents": [],
                "active_agent": "main",
                "statistics": {
                    "total_agents": 1,
                    "status_counts": {"active": 1},
                    "total_tasks": 0,
                    "pending_tasks": 0,
                    "online_agents": 1
                }
            }


def register_subordinate_agent(agent_id: str, agent_data: Dict[str, Any]):
    """Register a subordinate agent in the global registry and create flow tracking."""
    print(f"DEBUG: register_subordinate_agent called for {agent_id}", flush=True)
    registry = get_registry() 
    agent_entry = registry.register_agent(agent_id, agent_data)
    print(f"DEBUG: Agent registered, now creating flow...", flush=True)
    
    # Auto-create flow entry for visualization
    try:
        print(f"DEBUG: About to import flow_tracker for {agent_id}", flush=True)
        from python.api.agent_flow import flow_tracker
        import uuid
        print(f"DEBUG: Successfully imported flow_tracker: {flow_tracker}", flush=True)
        
        # Create or get existing flow for this parent agent
        parent_agent = agent_data.get("parent_agent", "main")
        flow_id = f"flow_{parent_agent}_{agent_id}"
        
        # Create flow if it doesn't exist
        existing_flow = flow_tracker.get_flow(flow_id)
        if not existing_flow:
            flow_tracker.create_flow(
                flow_id=flow_id,
                parent_agent=parent_agent,
                task_description=f"Agent delegation: {agent_data.get('role', 'subordinate')} task"
            )
            
            # Add parent agent to flow
            flow_tracker.add_agent_to_flow(flow_id, {
                "id": parent_agent,
                "name": "Agent Zero" if parent_agent == "main" else parent_agent,
                "type": "main" if parent_agent == "main" else "subordinate",
                "role": "coordinator",
                "status": "active"
            })
        
        # Add subordinate agent to flow
        flow_tracker.add_agent_to_flow(flow_id, {
            "id": agent_id,
            "name": agent_data.get("name", f"Subordinate {agent_id}"),
            "type": "subordinate",
            "role": agent_data.get("role", "subordinate"),
            "status": agent_data.get("status", "active"),
            "endpoint": agent_data.get("endpoint", f"local://{agent_id}")
        })
        
        # Add connection from parent to subordinate
        flow_tracker.add_connection(flow_id, parent_agent, agent_id, "task_delegation")
        
        print(f"DEBUG: Created flow {flow_id} for agent {agent_id}", flush=True)
        
    except Exception as e:
        print(f"DEBUG: Flow creation failed for {agent_id}: {e}", flush=True)
    
    return agent_entry


def update_subordinate_agent(agent_id: str, updates: Dict[str, Any]):
    """Update a subordinate agent's data."""
    registry = get_registry()
    return registry.update_agent(agent_id, updates)


def unregister_subordinate_agent(agent_id: str):
    """Remove a subordinate agent from the registry."""
    registry = get_registry()
    return registry.unregister_agent(agent_id)


def get_subordinate_agents() -> List[Dict[str, Any]]:
    """Get all active subordinate agents."""
    registry = get_registry()
    return registry.get_all_agents()


def update_subordinate_agent(agent_id: str, updates: dict):
    """Update subordinate agent information in the registry."""
    try:
        registry = get_registry()

        # Add timestamp to updates
        updates["last_contact"] = datetime.now(timezone.utc).isoformat()

        registry.update_agent(agent_id, updates)
        print(f"Updated subordinate agent: {agent_id}")

    except Exception as e:
        print(f"Error updating subordinate agent {agent_id}: {e}")


def remove_subordinate_agent(agent_id: str):
    """Remove subordinate agent from the registry."""
    try:
        registry = get_registry()
        registry.remove_agent(agent_id)
        print(f"Removed subordinate agent: {agent_id}")

    except Exception as e:
        print(f"Error removing subordinate agent {agent_id}: {e}")


def cleanup_orphaned_subordinates():
    """Clean up subordinate agents that are no longer active."""
    try:
        registry = get_registry()

        # Get all agents
        all_agents = registry.get_all_agents()

        # Find subordinate agents that haven't been contacted recently
        cutoff_time = datetime.now(timezone.utc).timestamp() - 600  # 10 minutes
        orphaned_agents = []

        for agent in all_agents:
            if agent.get("type") == "subordinate":
                last_contact = agent.get("last_contact")
                if last_contact:
                    try:
                        contact_time = datetime.fromisoformat(last_contact.replace('Z', '+00:00')).timestamp()
                        if contact_time < cutoff_time:
                            orphaned_agents.append(agent["id"])
                    except:
                        # If we can't parse the time, consider it orphaned
                        orphaned_agents.append(agent["id"])

        # Remove orphaned agents
        for agent_id in orphaned_agents:
            registry.remove_agent(agent_id)

        print(f"Cleaned up {len(orphaned_agents)} orphaned subordinate agents")
        return len(orphaned_agents)

    except Exception as e:
        print(f"Error cleaning up orphaned subordinates: {e}")
        return 0