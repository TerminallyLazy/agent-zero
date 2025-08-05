#!/usr/bin/env python3
"""
Simple Agent Zero Lite Example
"""
import asyncio
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from initialize import initialize_agent, run_agent


async def main():
    """
    Run a simple Agent Zero Lite example.
    """
    # Initialize agent
    print("Initializing Agent Zero Lite...")
    agent = await initialize_agent()
    
    # Run agent with a simple query
    print("\nRunning agent with a simple query...")
    response = await run_agent(agent, "What is your name and what can you do?")
    
    print("\nAgent response:")
    print(response)
    
    # Run agent with a tool execution request
    print("\nRunning agent with a tool execution request...")
    response = await run_agent(agent, "Can you run a simple Python calculation? What is 123 * 456?")
    
    print("\nAgent response:")
    print(response)
    
    # Run agent with a memory request
    print("\nRunning agent with a memory request...")
    response = await run_agent(agent, "Can you save a memory about today's weather?")
    
    print("\nAgent response:")
    print(response)
    
    # Run agent with a memory retrieval request
    print("\nRunning agent with a memory retrieval request...")
    response = await run_agent(agent, "What memories do you have?")
    
    print("\nAgent response:")
    print(response)


if __name__ == "__main__":
    asyncio.run(main())