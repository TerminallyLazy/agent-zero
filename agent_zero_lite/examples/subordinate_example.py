#!/usr/bin/env python3
"""
Subordinate Agent Example for Agent Zero Lite
"""
import asyncio
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from initialize import initialize_agent, run_agent
from agent import AgentConfig, AgentContext


async def main():
    """
    Run a subordinate agent example for Agent Zero Lite.
    """
    # Initialize superior agent
    print("Initializing Superior Agent...")
    superior_agent = await initialize_agent()
    
    # Run superior agent with a task that requires a subordinate
    print("\nRunning superior agent with a task that requires a subordinate...")
    response = await run_agent(
        superior_agent, 
        "I need you to delegate a task to a subordinate agent. The task is to calculate the factorial of 5."
    )
    
    print("\nSuperior agent response:")
    print(response)
    
    # Run superior agent with a more complex task
    print("\nRunning superior agent with a more complex task...")
    response = await run_agent(
        superior_agent, 
        "I need you to delegate a research task to a subordinate agent. " +
        "The task is to find information about the benefits of exercise and summarize it in 3 bullet points."
    )
    
    print("\nSuperior agent response:")
    print(response)
    
    # Run superior agent with a task that requires multiple subordinates
    print("\nRunning superior agent with a task that requires multiple subordinates...")
    response = await run_agent(
        superior_agent, 
        "I need you to delegate two tasks to two different subordinate agents. " +
        "The first task is to write a haiku about the ocean. " +
        "The second task is to write a limerick about a programmer."
    )
    
    print("\nSuperior agent response:")
    print(response)


if __name__ == "__main__":
    asyncio.run(main())