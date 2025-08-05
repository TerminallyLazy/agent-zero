#!/usr/bin/env python3
"""
Memory Example for Agent Zero Lite
"""
import asyncio
import sys
import os
import json
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from initialize import initialize_agent, run_agent


async def main():
    """
    Run a memory example for Agent Zero Lite.
    """
    # Initialize agent
    print("Initializing Agent Zero Lite...")
    agent = await initialize_agent()
    
    # Save a memory
    print("\nSaving a memory...")
    response = await run_agent(
        agent, 
        "Save this memory: The weather today is sunny with a high of 75°F."
    )
    print("\nAgent response:")
    print(response)
    
    # Save another memory
    print("\nSaving another memory...")
    response = await run_agent(
        agent, 
        "Save this memory: I learned about quantum computing today."
    )
    print("\nAgent response:")
    print(response)
    
    # List all memories
    print("\nListing all memories...")
    response = await run_agent(agent, "List all memories you have.")
    print("\nAgent response:")
    print(response)
    
    # Search for specific memory
    print("\nSearching for specific memory...")
    response = await run_agent(agent, "Find memories about weather.")
    print("\nAgent response:")
    print(response)
    
    # Print memory files
    print("\nMemory files in the system:")
    memory_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "memory", "main")
    for filename in os.listdir(memory_dir):
        if filename.endswith(".json"):
            with open(os.path.join(memory_dir, filename), "r") as f:
                memory = json.load(f)
                print(f"- {memory['id']}: {memory['text']}")


if __name__ == "__main__":
    asyncio.run(main())