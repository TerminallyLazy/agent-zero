"""
Helper to register Agent Zero contexts with the A2A registry.
"""

from python.helpers.registry_broker import AgentRegistry
from python.helpers.agent_card import AgentCard
from agent import AgentContext
import uuid
import os

# Secret for signing agent cards
AGENT_CARD_SECRET = os.environ.get("A2A_CARD_SECRET", "agent-zero-secret")

def register_agent_context(context: AgentContext, custom_id: str = None) -> str:
    """
    Register an Agent Zero context with the A2A registry.
    
    Args:
        context: The Agent Zero context to register
        custom_id: Optional custom agent ID
        
    Returns:
        The registered agent ID
    """
    registry = AgentRegistry()
    
    # Generate agent ID
    agent_id = custom_id or f"agent-zero-{context.id[:8]}"
    
    # Create agent card
    card = AgentCard(
        agent_id=agent_id,
        role_description=f"Agent Zero Context {context.id[:8]} - AI Assistant with code execution, web browsing, and file management",
        tools=["code_execution", "web_search", "file_management", "data_analysis", "system_automation"],
        capabilities={
            "programming": True,
            "web_browsing": True,
            "file_management": True,
            "data_analysis": True,
            "system_automation": True,
            "context_id": context.id
        },
        trust_level="local",
        version="1.0"
    )
    
    # Sign and register
    signed_card = card.signed(AGENT_CARD_SECRET)
    registry.register(agent_id, signed_card)
    
    print(f"[A2A] Registered Agent Zero context {context.id} as {agent_id}")
    
    return agent_id

def unregister_agent_context(context: AgentContext) -> bool:
    """
    Unregister an Agent Zero context from the A2A registry.
    
    Args:
        context: The Agent Zero context to unregister
        
    Returns:
        True if unregistered successfully
    """
    registry = AgentRegistry()
    
    # Try multiple possible agent IDs
    possible_ids = [
        f"agent-zero-{context.id[:8]}",
        f"agent-zero-{context.id}",
        context.id
    ]
    
    for agent_id in possible_ids:
        if registry.unregister(agent_id):
            print(f"[A2A] Unregistered Agent Zero context {context.id}")
            return True
    
    return False

def get_all_registered_contexts() -> list:
    """Get all registered Agent Zero contexts."""
    registry = AgentRegistry()
    agents = registry.list_agents()
    
    contexts = []
    for agent in agents:
        if agent.agent_id.startswith("agent-zero-"):
            contexts.append({
                "agent_id": agent.agent_id,
                "card": agent.signed_card.get("agent_card", {}),
                "context_id": agent.signed_card.get("agent_card", {}).get("capabilities", {}).get("context_id")
            })
    
    return contexts