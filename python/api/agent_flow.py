from python.helpers.api import ApiHandler, Request, Response
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional
import json
import os
import threading
import uuid
from python.helpers import files
from python.tools.agent_bridge import AgentCapabilities


class AgentFlowTracker:
    """Singleton class to track agent flows and paths for real-time visualization."""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized') and self._initialized:
            return

        self.flows = {}  # flow_id -> flow_data
        self.active_flows = set()
        self.agent_colors = {}  # Dynamic color assignment
        self.color_index = 0
        self.available_colors = [
            "#3B82F6", "#10B981", "#F59E0B", "#EF4444", "#8B5CF6",
            "#F97316", "#06B6D4", "#84CC16", "#EC4899", "#14B8A6",
            "#F43F5E", "#6366F1", "#059669", "#DC2626", "#7C3AED"
        ]
        self.data_file = files.get_abs_path("memory", "agent_flows.json")
        self._load_flows()
        self._initialized = True

    def _load_flows(self):
        """Load flows from persistent storage."""
        try:
            if os.path.exists(self.data_file):
                with open(self.data_file, 'r') as f:
                    data = json.load(f)
                    self.flows = data.get('flows', {})
                    self.active_flows = set(data.get('active_flows', []))
                    self.agent_colors = data.get('agent_colors', {})
                    self.color_index = data.get('color_index', 0)
                    print(f"Loaded {len(self.flows)} flows from persistent storage")
        except Exception as e:
            print(f"Error loading flows: {e}")
            self.flows = {}
            self.active_flows = set()
            self.agent_colors = {}
            self.color_index = 0

    def _save_flows(self):
        """Save flows to persistent storage."""
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(self.data_file), exist_ok=True)

            data = {
                'flows': self.flows,
                'active_flows': list(self.active_flows),
                'agent_colors': self.agent_colors,
                'color_index': self.color_index,
                'last_updated': datetime.now(timezone.utc).isoformat()
            }

            with open(self.data_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Error saving flows: {e}")
    
    def create_flow(self, flow_id: str, parent_agent: str, task_description: str) -> Dict[str, Any]:
        """Create a new agent flow."""
        flow_data = {
            "id": flow_id,
            "parent_agent": parent_agent,
            "task_description": task_description,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "initializing",
            "agents": [],
            "connections": [],
            "progress": 0,
            "total_operations": 0,
            "completed_operations": 0
        }
        
        self.flows[flow_id] = flow_data
        self.active_flows.add(flow_id)
        self._save_flows()  # Persist changes
        return flow_data
    
    def add_agent_to_flow(self, flow_id: str, agent_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Add an agent to a flow with visual properties and Agent Card information."""
        if flow_id not in self.flows:
            return None

        # Dynamically assign color to agent type
        agent_type = agent_data.get("type", agent_data.get("role", "default"))
        if agent_type not in self.agent_colors:
            self.agent_colors[agent_type] = self.available_colors[self.color_index % len(self.available_colors)]
            self.color_index += 1

        agent_node = {
            "id": agent_data.get("id", str(uuid.uuid4())),
            "name": agent_data.get("name", "Unknown Agent"),
            "type": agent_type,
            "role": agent_data.get("role", "worker"),
            "status": agent_data.get("status", "initializing"),
            "color": self.agent_colors[agent_type],
            "endpoint": agent_data.get("endpoint", "local"),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "progress": 0,
            "current_task": agent_data.get("message", ""),
            "x": 0,  # Will be calculated by frontend
            "y": 0,  # Will be calculated by frontend
            # Hierarchical relationship tracking
            "parent_id": agent_data.get("parent_id"),
            "superior_id": agent_data.get("superior_id"),
            "subordinate_ids": agent_data.get("subordinate_ids", []),
            "hierarchy_level": agent_data.get("hierarchy_level", 0),
            # Enhanced Agent Card information
            "agent_card": agent_data.get("agent_card", {}),
            "skills": agent_data.get("skills", []),
            "capabilities": agent_data.get("capabilities", {}),
            "protocol": agent_data.get("protocol", "local"),
            "version": agent_data.get("version", "unknown"),
            "description": agent_data.get("description", ""),
        }

        self.flows[flow_id]["agents"].append(agent_node)
        self._save_flows()  # Persist changes
        return agent_node
    
    def add_connection(self, flow_id: str, from_agent: str, to_agent: str, connection_type: str = "task_delegation"):
        """Add a connection between agents."""
        if flow_id not in self.flows:
            return
        
        connection = {
            "id": str(uuid.uuid4()),
            "from": from_agent,
            "to": to_agent,
            "type": connection_type,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "active",
            "data_flow": []
        }
        
        self.flows[flow_id]["connections"].append(connection)
        self._save_flows()  # Persist changes
        return connection
    
    def update_agent_status(self, flow_id: str, agent_id: str, status: str, progress: int = None, current_task: str = None):
        """Update agent status and progress."""
        if flow_id not in self.flows:
            return
        
        for agent in self.flows[flow_id]["agents"]:
            if agent["id"] == agent_id:
                agent["status"] = status
                agent["last_updated"] = datetime.now(timezone.utc).isoformat()
                
                if progress is not None:
                    agent["progress"] = min(100, max(0, progress))
                
                if current_task is not None:
                    agent["current_task"] = current_task

                self._save_flows()  # Persist changes
                break
    
    def update_flow_progress(self, flow_id: str, completed_operations: int, total_operations: int):
        """Update overall flow progress."""
        if flow_id not in self.flows:
            return
        
        flow = self.flows[flow_id]
        flow["completed_operations"] = completed_operations
        flow["total_operations"] = total_operations
        flow["progress"] = int((completed_operations / total_operations) * 100) if total_operations > 0 else 0
        flow["last_updated"] = datetime.now(timezone.utc).isoformat()
        
        if completed_operations >= total_operations:
            flow["status"] = "completed"
            if flow_id in self.active_flows:
                self.active_flows.remove(flow_id)
    
    def complete_flow(self, flow_id: str, success: bool = True):
        """Mark a flow as completed."""
        if flow_id not in self.flows:
            return
        
        self.flows[flow_id]["status"] = "completed" if success else "failed"
        self.flows[flow_id]["completed_at"] = datetime.now(timezone.utc).isoformat()
        
        if flow_id in self.active_flows:
            self.active_flows.remove(flow_id)
    
    def get_flow(self, flow_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific flow."""
        return self.flows.get(flow_id)
    
    def get_active_flows(self) -> List[Dict[str, Any]]:
        """Get all active flows."""
        return [self.flows[flow_id] for flow_id in self.active_flows if flow_id in self.flows]
    
    def get_all_flows(self) -> List[Dict[str, Any]]:
        """Get all flows (active and completed)."""
        return list(self.flows.values())

    def clear_all_flows(self):
        """Clear all flows - useful for testing and cleanup."""
        self.flows.clear()
        self.active_flows.clear()
        self.agent_colors.clear()
        self.color_index = 0
        self._save_flows()

    def create_subordinate_agent_flow(self, parent_agent_name: str, task_description: str,
                                    agent_endpoint: str = None, agent_capabilities: AgentCapabilities = None) -> str:
        """
        Create a new flow for a subordinate agent created via agent bridge.

        Args:
            parent_agent_name: Name of the parent agent creating the subordinate
            task_description: Description of the task for the subordinate agent
            agent_endpoint: Endpoint of the subordinate agent (if remote)
            agent_capabilities: Discovered capabilities of the agent

        Returns:
            flow_id: ID of the created flow
        """
        flow_id = f"flow_{parent_agent_name}_subordinate_{uuid.uuid4().hex[:8]}"

        # Create the flow
        flow_data = self.create_flow(flow_id, parent_agent_name, task_description)

        # Add the parent agent to the flow
        parent_agent_data = {
            "id": f"{parent_agent_name}_main",
            "name": parent_agent_name,
            "type": "main",
            "role": "coordinator",
            "status": "running",
            "progress": 0,
            "endpoint": "local"
        }
        self.add_agent_to_flow(flow_id, parent_agent_data)

        # If we have agent capabilities, add the subordinate agent
        if agent_capabilities:
            subordinate_agent_data = {
                "id": agent_capabilities.agent_id or f"subordinate_{uuid.uuid4().hex[:8]}",
                "name": agent_capabilities.capabilities.get("name", "Subordinate Agent"),
                "type": agent_capabilities.protocol.lower(),
                "role": "subordinate",
                "status": "initializing",
                "progress": 0,
                "parent_id": f"{parent_agent_name}_main",
                "superior_id": f"{parent_agent_name}_main",
                "endpoint": agent_endpoint or agent_capabilities.endpoint,
                "protocol": agent_capabilities.protocol,
                "capabilities": agent_capabilities.capabilities,
                "lifecycle_stage": "spawning"
            }
            self.add_agent_to_flow(flow_id, subordinate_agent_data)

        return flow_id

    def update_subordinate_agent_from_bridge(self, flow_id: str, agent_id: str,
                                           bridge_response: Dict[str, Any]):
        """
        Update subordinate agent status based on agent bridge response.

        Args:
            flow_id: ID of the flow containing the agent
            agent_id: ID of the agent to update
            bridge_response: Response from agent bridge communication
        """
        if flow_id not in self.flows:
            return

        flow = self.flows[flow_id]

        # Find the agent in the flow
        for agent in flow.get("agents", []):
            if agent["id"] == agent_id:
                # Update status based on bridge response
                if bridge_response.get("status") == 200:
                    if "response" in bridge_response:
                        response_data = bridge_response["response"]

                        # Update agent status based on response
                        if "error" in response_data:
                            agent["status"] = "failed"
                            agent["lifecycle_stage"] = "failed_cleanup_pending"
                        else:
                            agent["status"] = "running"
                            agent["lifecycle_stage"] = "active"

                        # Extract progress if available
                        if "progress" in response_data:
                            agent["progress"] = response_data["progress"]

                        # Store last communication
                        agent["last_communication"] = {
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "protocol": bridge_response.get("protocol"),
                            "status": bridge_response.get("status"),
                            "message_sent": bridge_response.get("message_sent", "")
                        }
                else:
                    agent["status"] = "failed"
                    agent["lifecycle_stage"] = "failed_cleanup_pending"

                break

        self._save_flows()

    def complete_subordinate_agent(self, flow_id: str, agent_id: str, success: bool = True):
        """
        Mark a subordinate agent as completed and schedule cleanup.

        Args:
            flow_id: ID of the flow containing the agent
            agent_id: ID of the agent to complete
            success: Whether the agent completed successfully
        """
        if flow_id not in self.flows:
            return

        flow = self.flows[flow_id]

        # Find and update the agent
        for agent in flow.get("agents", []):
            if agent["id"] == agent_id:
                if success:
                    agent["status"] = "completed"
                    agent["progress"] = 100
                    agent["lifecycle_stage"] = "completed_cleanup_scheduled"
                else:
                    agent["status"] = "failed"
                    agent["lifecycle_stage"] = "failed_cleanup_pending"

                agent["completed_at"] = datetime.now(timezone.utc).isoformat()
                break

        # Check if all subordinate agents are completed
        subordinate_agents = [a for a in flow.get("agents", []) if a.get("parent_id")]
        completed_subordinates = [a for a in subordinate_agents if a["status"] in ["completed", "failed"]]

        if len(completed_subordinates) == len(subordinate_agents) and len(subordinate_agents) > 0:
            # All subordinates done, update main agent
            main_agents = [a for a in flow.get("agents", []) if not a.get("parent_id")]
            for main_agent in main_agents:
                main_agent["status"] = "completed"
                main_agent["progress"] = 100

            # Mark flow as completed
            flow["status"] = "completed"
            flow["completed_at"] = datetime.now(timezone.utc).isoformat()

            if flow_id in self.active_flows:
                self.active_flows.remove(flow_id)

        self._save_flows()

    def archive_flow(self, flow_id: str):
        """Archive a flow (mark as archived and remove from active tracking)."""
        if flow_id in self.flows:
            self.flows[flow_id]["status"] = "archived"
            self.flows[flow_id]["archived_at"] = datetime.now(timezone.utc).isoformat()

            if flow_id in self.active_flows:
                self.active_flows.remove(flow_id)

            print(f"Archived flow: {flow_id}")

    def cleanup_old_flows(self, max_age_hours: int = 24):
        """Clean up flows older than specified hours."""
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        flows_to_remove = []

        for flow_id, flow_data in self.flows.items():
            try:
                created_at = datetime.fromisoformat(flow_data["created_at"].replace('Z', '+00:00'))
                if created_at < cutoff_time and flow_data.get("status") in ["completed", "failed", "archived"]:
                    flows_to_remove.append(flow_id)
            except:
                # If we can't parse the date, consider it for removal if it's not active
                if flow_data.get("status") in ["completed", "failed", "archived"]:
                    flows_to_remove.append(flow_id)

        for flow_id in flows_to_remove:
            del self.flows[flow_id]
            if flow_id in self.active_flows:
                self.active_flows.remove(flow_id)

        print(f"Cleaned up {len(flows_to_remove)} old flows")
        return len(flows_to_remove)


# Global tracker instance
flow_tracker = AgentFlowTracker()


class AgentFlow(ApiHandler):
    """API handler for agent flow tracking and visualization."""
    
    @classmethod
    def requires_auth(cls) -> bool:
        return False
    
    async def process(self, input: dict, request: Request) -> dict | Response:
        """Handle agent flow API requests."""
        try:
            action = input.get("action", "get_active_flows")
            
            if action == "get_active_flows":
                return {
                    "success": True,
                    "flows": flow_tracker.get_active_flows()
                }
            
            elif action == "get_all_flows":
                return {
                    "success": True,
                    "flows": flow_tracker.get_all_flows()
                }
            
            elif action == "get_flow":
                flow_id = input.get("flow_id")
                if not flow_id:
                    return {"success": False, "error": "flow_id required"}

                flow = flow_tracker.get_flow(flow_id)
                if not flow:
                    return {"success": False, "error": "Flow not found"}

                return {
                    "success": True,
                    "flow": flow
                }

            elif action == "clear_flows":
                flow_tracker.clear_all_flows()
                return {
                    "success": True,
                    "message": "All flows cleared"
                }

            elif action == "create_subordinate_flow":
                parent_agent = input.get("parent_agent")
                task_description = input.get("task_description")
                agent_endpoint = input.get("agent_endpoint")

                if not parent_agent or not task_description:
                    return {"success": False, "error": "parent_agent and task_description required"}

                # Create agent capabilities if provided
                agent_capabilities = None
                if input.get("agent_capabilities"):
                    caps_data = input["agent_capabilities"]
                    agent_capabilities = AgentCapabilities(
                        protocol=caps_data.get("protocol", "A2A"),
                        endpoint=caps_data.get("endpoint", agent_endpoint),
                        capabilities=caps_data.get("capabilities", {}),
                        version=caps_data.get("version"),
                        agent_id=caps_data.get("agent_id")
                    )

                flow_id = flow_tracker.create_subordinate_agent_flow(
                    parent_agent, task_description, agent_endpoint, agent_capabilities
                )

                return {
                    "success": True,
                    "flow_id": flow_id,
                    "message": f"Subordinate agent flow created: {flow_id}"
                }

            elif action == "update_subordinate_agent":
                flow_id = input.get("flow_id")
                agent_id = input.get("agent_id")
                bridge_response = input.get("bridge_response", {})

                if not flow_id or not agent_id:
                    return {"success": False, "error": "flow_id and agent_id required"}

                flow_tracker.update_subordinate_agent_from_bridge(flow_id, agent_id, bridge_response)

                return {
                    "success": True,
                    "message": f"Agent {agent_id} updated in flow {flow_id}"
                }

            elif action == "complete_subordinate_agent":
                flow_id = input.get("flow_id")
                agent_id = input.get("agent_id")
                success = input.get("success", True)

                if not flow_id or not agent_id:
                    return {"success": False, "error": "flow_id and agent_id required"}

                flow_tracker.complete_subordinate_agent(flow_id, agent_id, success)

                return {
                    "success": True,
                    "message": f"Agent {agent_id} marked as {'completed' if success else 'failed'}"
                }

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