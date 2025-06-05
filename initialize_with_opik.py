from models import ModelProvider
from agent import ModelConfig, Agent, AgentConfig  
from python.helpers.opik_init import initialize_opik_integration  
  
def main():  
    # Initialize Opik integration first  
    initialize_opik_integration()  
      
    # Continue with normal Agent Zero initialization  
    config = AgentConfig(  
        chat_model=ModelConfig(  
            provider=ModelProvider.OPENAI,  
            name="gpt-4.1"  
        ),  
        utility_model=ModelConfig(  
            provider=ModelProvider.OPENAI,   
            name="gpt-4.1"  
        ),  
        embeddings_model=ModelConfig(  
            provider=ModelProvider.OPENAI,  
            name="text-embedding-3-small"  
        ),  
        browser_model=ModelConfig(  
            provider=ModelProvider.OPENAI,  
            name="gpt-4.1"  
        ),
        mcp_servers='{"mcpServers": {}}'
    )  
      
    agent = Agent(0, config)  
    return agent  
  
if __name__ == "__main__":  
    agent = main()
