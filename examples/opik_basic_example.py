#!/usr/bin/env python3
"""
Basic example of using Agent Zero with Opik tracing
"""

import os
import sys
import asyncio

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import ModelProvider
from agent import ModelConfig, Agent, AgentConfig
from python.helpers.opik_init import initialize_opik_integration

async def main():
    """Basic Agent Zero + Opik example"""
    
    print("🚀 Starting Agent Zero with Opik Integration")
    
    # Initialize Opik integration
    opik_tracker = initialize_opik_integration()
    
    if opik_tracker and opik_tracker.is_enabled():
        print("✅ Opik integration active - traces will be logged to http://localhost:5173")
    else:
        print("⚠️ Opik integration disabled")
    
    # Configure Agent Zero
    config = AgentConfig(
        chat_model=ModelConfig(
            provider=ModelProvider.OPENAI,
            name="gpt-4"
        ),
        utility_model=ModelConfig(
            provider=ModelProvider.OPENAI,
            name="gpt-3.5-turbo"
        ),
        embeddings_model=ModelConfig(
            provider=ModelProvider.OPENAI,
            name="text-embedding-3-small"
        )
    )
    
    # Create agent
    agent = Agent(0, config)
    
    print("\n📝 Sending message to agent...")
    
    # Send a message that will be traced
    response = await agent.message_loop("What is the capital of France? Please explain why it's important.")
    
    print(f"\n🤖 Agent Response: {response}")
    
    # Flush any pending traces
    if opik_tracker:
        opik_tracker.flush()
        print("\n✅ Traces flushed to Opik dashboard")
    
    print("\n🎉 Example completed! Check your Opik dashboard at http://localhost:5173")

if __name__ == "__main__":
    asyncio.run(main())
