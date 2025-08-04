import uuid
import hashlib
import json
from typing import List, Dict, Any
from datetime import datetime, timezone

def time_iso():
    return datetime.now(timezone.utc).isoformat()

def compute_card_signature(card: Dict, secret: str) -> str:
    payload = json.dumps(card, sort_keys=True).encode()
    return hashlib.sha256(payload + secret.encode()).hexdigest()

class AgentCard:
    def __init__(
        self,
        agent_id: str,
        role_description: str,
        tools: List[str],
        capabilities: Dict[str, bool],
        trust_level: str = "local",
        version: str = "1.0",
        metadata: Dict[str, Any] = None,
    ):
        self.agent_id = agent_id
        self.role_description = role_description
        self.tools = tools
        self.capabilities = capabilities
        self.trust_level = trust_level
        self.version = version
        self.metadata = metadata or {}
        self.card = self._build_card()

    def _build_card(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "role_description": self.role_description,
            "tools": self.tools,
            "capabilities": self.capabilities,
            "trust_level": self.trust_level,
            "version": self.version,
            "metadata": self.metadata,
            "generated_at": time_iso(),
        }

    def signed(self, secret: str) -> Dict[str, Any]:
        card = self._build_card()
        signature = compute_card_signature(card, secret)
        return {"agent_card": card, "signature": signature}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert agent card to dictionary"""
        return self._build_card()

    @staticmethod
    def validate(signed_card: Dict[str, Any], secret: str) -> bool:
        card = signed_card.get("agent_card", {})
        sig = signed_card.get("signature", "")
        expected = compute_card_signature(card, secret)
        return sig == expected

def minimal_agent_card_from_context(agent_context) -> AgentCard:
    # Hook to introspect existing Agent Zero context/system prompt/tools.
    agent_id = getattr(agent_context, "id", str(uuid.uuid4()))
    
    # Try to get agent name or use a default
    role_description = "Agent Zero instance"
    tools = []
    
    try:
        if hasattr(agent_context, "agent0") and hasattr(agent_context.agent0, "agent_name"):
            role_description = f"{agent_context.agent0.agent_name} - Agent Zero instance"
        
        # Extract tools from the agent's first instance
        if hasattr(agent_context, "agent0"):
            agent = agent_context.agent0
            
            # Try different ways to get tools
            if hasattr(agent, "config") and hasattr(agent.config, "additional"):
                # Tools are usually stored in the config
                tool_instances = agent.config.additional.get("tools", [])
                for tool in tool_instances:
                    if hasattr(tool, "name"):
                        tools.append(tool.name)
                    elif hasattr(tool, "__class__"):
                        tools.append(tool.__class__.__name__)
            
            # Fallback - get standard Agent Zero tools
            if not tools:
                # Agent Zero typically has these tools available
                tools = [
                    "call_subordinate",
                    "code_execution", 
                    "web_search",
                    "memory_tool",
                    "knowledge_tool",
                    "response"
                ]
    
    except Exception as e:
        print(f"[A2A] Warning: Could not extract full context info: {e}")
        # Use defaults if context extraction fails
        tools = ["call_subordinate", "code_execution", "web_search", "response"]
    
    # Define capabilities based on Agent Zero's features
    capabilities = {
        "text_generation": True,
        "tool_usage": bool(tools),
        "streaming": True,  # Agent Zero supports streaming
        "code_execution": True,  # Agent Zero can execute code
        "web_browsing": True,  # Agent Zero has browser capabilities
        "memory": True,  # Agent Zero has memory capabilities
        "task_delegation": True,  # Agent Zero can delegate to subordinates
    }
    
    return AgentCard(agent_id, role_description, tools, capabilities)