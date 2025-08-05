#!/usr/bin/env python3
"""
Agent Zero Lite CLI
"""
import asyncio
import argparse
import sys
from typing import Optional

from initialize import initialize_agent, run_agent, create_default_config
from agent import AgentConfig
from models import ModelConfig, ModelType


async def main():
    """
    Main function to run the Agent Zero Lite CLI.
    """
    parser = argparse.ArgumentParser(description="Agent Zero Lite CLI")
    parser.add_argument("--model", type=str, help="Chat model to use (e.g., openai/gpt-4o)")
    parser.add_argument("--utility-model", type=str, help="Utility model to use (e.g., openai/gpt-3.5-turbo)")
    parser.add_argument("--mcp", type=str, help="MCP servers to use (comma-separated)")
    parser.add_argument("--profile", type=str, help="Agent profile to use")
    parser.add_argument("--message", type=str, help="Initial message to send to the agent")
    
    args = parser.parse_args()
    
    # Create default config
    config = create_default_config()
    
    # Override config with command line arguments
    if args.model:
        provider, model = args.model.split("/", 1)
        config.chat_model = ModelConfig(
            type=ModelType.CHAT,
            provider=provider,
            name=model,
            ctx_length=config.chat_model.ctx_length,
            limit_output=config.chat_model.limit_output,
        )
    
    if args.utility_model:
        provider, model = args.utility_model.split("/", 1)
        config.utility_model = ModelConfig(
            type=ModelType.UTILITY,
            provider=provider,
            name=model,
            ctx_length=config.utility_model.ctx_length,
            limit_output=config.utility_model.limit_output,
        )
    
    if args.mcp:
        config.mcp_servers = args.mcp
    
    if args.profile:
        config.profile = args.profile
    
    # Initialize agent
    agent = await initialize_agent(config)
    
    # If message is provided, run agent with it and exit
    if args.message:
        response = await run_agent(agent, args.message)
        print(response)
        return
    
    # Interactive mode
    print("Agent Zero Lite CLI")
    print("Type 'exit' to quit")
    
    while True:
        try:
            # Get user input
            user_input = input("\nUser: ")
            
            # Check if user wants to exit
            if user_input.lower() in ["exit", "quit"]:
                break
            
            # Run agent
            response = await run_agent(agent, user_input)
            
            # Print response
            print(f"\nAgent: {response}")
        
        except KeyboardInterrupt:
            print("\nExiting...")
            break
        except Exception as e:
            print(f"\nError: {str(e)}")


if __name__ == "__main__":
    asyncio.run(main())