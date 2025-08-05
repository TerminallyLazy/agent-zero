import os
import asyncio
from typing import Optional

from agent import Agent, AgentConfig, AgentContext, UserMessage
from models import ModelConfig, ModelType
from helpers.dotenv import load_dotenv, get_dotenv_value


def create_default_config() -> AgentConfig:
    """
    Create a default agent configuration.
    """
    # Load environment variables
    load_dotenv()
    
    # Get OpenAI API key
    openai_api_key = get_dotenv_value("OPENAI_API_KEY")
    if not openai_api_key:
        print("Warning: OPENAI_API_KEY not found in environment variables.")
    
    # Get model provider and name from environment variables
    chat_provider = get_dotenv_value("CHAT_MODEL_PROVIDER") or "openai"
    chat_name = get_dotenv_value("CHAT_MODEL_NAME") or "gpt-4o"
    utility_provider = get_dotenv_value("UTILITY_MODEL_PROVIDER") or "openai"
    utility_name = get_dotenv_value("UTILITY_MODEL_NAME") or "gpt-3.5-turbo"
    
    # Create model configurations
    chat_model = ModelConfig(
        type=ModelType.CHAT,
        provider=chat_provider,
        name=chat_name,
        ctx_length=int(get_dotenv_value("CHAT_MODEL_CTX_LENGTH") or "128000"),
        limit_output=4000,
        kwargs={"temperature": float(get_dotenv_value("CHAT_MODEL_TEMPERATURE") or "0.7")},
    )
    
    utility_model = ModelConfig(
        type=ModelType.UTILITY,
        provider=utility_provider,
        name=utility_name,
        ctx_length=int(get_dotenv_value("UTILITY_MODEL_CTX_LENGTH") or "16000"),
        limit_output=2000,
        kwargs={"temperature": float(get_dotenv_value("UTILITY_MODEL_TEMPERATURE") or "0.2")},
    )
    
    # Create agent configuration
    config = AgentConfig(
        chat_model=chat_model,
        utility_model=utility_model,
        mcp_servers="",  # No MCP servers by default
        profile="",  # No profile by default
        memory_subdir="",  # No memory subdirectory by default
    )
    
    return config


async def initialize_agent(config: Optional[AgentConfig] = None) -> Agent:
    """
    Initialize an agent with the given configuration.
    
    Args:
        config: Agent configuration. If None, a default configuration is used.
    
    Returns:
        Initialized Agent instance
    """
    # Create default config if none provided
    if config is None:
        config = create_default_config()
    
    # Create agent context
    context = AgentContext(config=config)
    
    # Create agent
    agent = Agent(0, config, context)
    
    return agent


async def run_agent(agent: Agent, message: str) -> str:
    """
    Run an agent with a user message.
    
    Args:
        agent: Agent instance
        message: User message
    
    Returns:
        Agent response
    """
    # Add user message
    agent.hist_add_user_message(UserMessage(message=message))
    
    # Run agent monologue
    response = await agent.monologue()
    
    return response


async def main():
    """
    Main function to run the agent.
    """
    # Initialize agent
    agent = await initialize_agent()
    
    print("Agent Zero Lite initialized. Type 'exit' to quit.")
    
    # Main loop
    while True:
        # Get user input
        user_input = input("User: ")
        
        # Check if user wants to exit
        if user_input.lower() in ["exit", "quit"]:
            break
        
        # Run agent
        response = await run_agent(agent, user_input)
        
        # Print response
        print(f"Agent: {response}")


if __name__ == "__main__":
    asyncio.run(main())