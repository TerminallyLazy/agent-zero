#!/usr/bin/env python3
"""
Test script for Agent Zero Lite
"""
import asyncio
import sys
from initialize import initialize_agent, run_agent


async def test_agent():
    """
    Test the Agent Zero Lite implementation.
    """
    print("Initializing Agent Zero Lite...")
    agent = await initialize_agent()
    
    print("Testing agent with a simple query...")
    response = await run_agent(agent, "What is 2+2?")
    
    print("\nAgent response:")
    print(response)
    
    print("\nTesting tool execution...")
    response = await run_agent(agent, "Run this Python code: print('Hello, Agent Zero Lite!')")
    
    print("\nAgent response:")
    print(response)
    
    print("\nTest completed successfully!")


if __name__ == "__main__":
    asyncio.run(test_agent())