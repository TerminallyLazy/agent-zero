import time
import threading
import os
import tempfile
from typing import Dict, List
from dataclasses import dataclass, field

# Simple semantic overlap scorer (replace with real embedding-based model as needed)
def semantic_score(goal: str, role_description: str) -> float:
    goal_tokens = set(goal.lower().split())
    role_tokens = set(role_description.lower().split())
    overlap = goal_tokens.intersection(role_tokens)
    return len(overlap) / max(1, len(goal_tokens))

@dataclass
class RegisteredAgent:
    agent_id: str
    signed_card: Dict
    last_heartbeat: float = field(default_factory=time.time)
    score_cache: Dict[str, float] = field(default_factory=dict)

class AgentRegistry:
    _instance = None
    _lockfile_path = os.path.join(tempfile.gettempdir(), "agent_zero_registry.lock")

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._agents = {}
            cls._instance._lock = threading.Lock()
            # NUCLEAR OPTION: Clear any existing lockfile to force reset
            if os.path.exists(cls._lockfile_path):
                try:
                    os.remove(cls._lockfile_path)
                    print("[A2A] Removed stale registry lockfile")
                except:
                    pass
        return cls._instance

    def register(self, agent_id: str, signed_card: Dict):
        with self._lock:
            # Always update/overwrite existing registrations to handle restarts
            if agent_id in self._agents:
                print(f"[A2A] Updating existing agent registration: {agent_id}")
            else:
                print(f"[A2A] Registering new agent: {agent_id}")
            self._agents[agent_id] = RegisteredAgent(agent_id=agent_id, signed_card=signed_card)

    def heartbeat(self, agent_id: str):
        with self._lock:
            if agent_id in self._agents:
                self._agents[agent_id].last_heartbeat = time.time()

    def unregister(self, agent_id: str):
        """Explicitly remove an agent from the registry"""
        with self._lock:
            if agent_id in self._agents:
                print(f"[A2A] Unregistering agent: {agent_id}")
                del self._agents[agent_id]
                return True
            return False

    def prune_stale(self, ttl: float = 120.0):
        with self._lock:
            cutoff = time.time() - ttl
            stale = [aid for aid, a in self._agents.items() if a.last_heartbeat < cutoff]
            if stale:
                print(f"[A2A] Pruning {len(stale)} stale agents: {stale}")
            for aid in stale:
                del self._agents[aid]

    def list_agents(self) -> List[RegisteredAgent]:
        with self._lock:
            return list(self._agents.values())

    def match(self, goal: str, top_k: int = 3) -> List[RegisteredAgent]:
        candidates = []
        with self._lock:
            for reg in self._agents.values():
                card = reg.signed_card.get("agent_card", {})
                role_desc = card.get("role_description", "")
                score = semantic_score(goal, role_desc)
                reg.score_cache[goal] = score
                candidates.append((score, reg))
        candidates.sort(key=lambda x: x[0], reverse=True)
        return [r for _, r in candidates[:top_k]]