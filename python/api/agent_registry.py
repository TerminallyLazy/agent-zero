"""
Persistent agent registry that survives module reloads
"""
import threading
from datetime import datetime, timezone
from typing import Dict, List, Any


class PersistentAgentRegistry:
    """Thread-safe singleton agent registry that persists across module reloads."""
    
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
        if not getattr(self, '_initialized', False):
            self.agents = {}
            self._lock = threading.Lock()
            self._initialized = True
    
    def register_agent(self, agent_id: str, agent_data: Dict[str, Any]) -> Dict[str, Any]:
        """Register a subordinate agent."""
        with self._lock:
            agent_entry = {
                "id": agent_id,
                "type": "subordinate",
                "name": agent_data.get("name", f"Subordinate {agent_id}"),
                "role": agent_data.get("role", "subordinate"),
                "status": agent_data.get("status", "active"),
                "endpoint": agent_data.get("endpoint", f"local://{agent_id}"),
                "capabilities": ["reasoning", "tools", "memory", "planning"],
                "protocol": "A2A",
                "last_contact": datetime.now(timezone.utc).isoformat(),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "task_count": agent_data.get("task_count", 0),
                "url": agent_data.get("url"),
                "parent_agent": agent_data.get("parent_agent", "main"),
                "profile": agent_data.get("profile", "default")
            }
            self.agents[agent_id] = agent_entry
            print(f"DEBUG: PersistentRegistry registered agent {agent_id}, total agents: {len(self.agents)}", flush=True)
            return agent_entry
    
    def update_agent(self, agent_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Update a subordinate agent's data."""
        with self._lock:
            if agent_id in self.agents:
                self.agents[agent_id].update(updates)
                self.agents[agent_id]["last_contact"] = datetime.now(timezone.utc).isoformat()
                return self.agents[agent_id]
            return None
    
    def unregister_agent(self, agent_id: str) -> bool:
        """Remove a subordinate agent from the registry."""
        with self._lock:
            if agent_id in self.agents:
                del self.agents[agent_id]
                return True
            return False
    
    def get_all_agents(self) -> List[Dict[str, Any]]:
        """Get all active subordinate agents."""
        with self._lock:
            print(f"DEBUG: PersistentRegistry.get_all_agents() called, found {len(self.agents)} agents", flush=True)
            return list(self.agents.values())
    
    def get_active_agents(self, max_age_seconds: int = 300) -> List[Dict[str, Any]]:
        """Get agents that are still active (contacted within max_age_seconds)."""
        with self._lock:
            active_agents = []
            stale_agents = []
            
            for agent_id, agent_data in self.agents.items():
                last_contact = datetime.fromisoformat(agent_data["last_contact"].replace('Z', '+00:00'))
                time_diff = (datetime.now(timezone.utc) - last_contact).total_seconds()
                
                if time_diff < max_age_seconds:
                    active_agents.append(agent_data)
                else:
                    stale_agents.append(agent_id)
            
            # Remove stale agents
            for agent_id in stale_agents:
                del self.agents[agent_id]
            
            print(f"DEBUG: PersistentRegistry.get_active_agents() found {len(active_agents)} active agents", flush=True)
            return active_agents


# Global singleton instance - this should persist across all imports
_global_registry = PersistentAgentRegistry()


def get_registry() -> PersistentAgentRegistry:
    """Get the global agent registry instance."""
    return _global_registry