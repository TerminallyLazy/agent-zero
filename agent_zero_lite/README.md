# Agent Zero Lite

A lightweight, cross-platform Python implementation of Agent Zero that maintains the core architecture and design patterns while removing non-essential features. Agent Zero Lite runs on any OS with minimal dependencies and focuses on the essential agent capabilities.

## Features

- **Core Agent System**: 
  - Agent class with message loop, tool execution, and LLM communication
  - AgentContext class for managing multiple agent instances
  - AgentConfig class for model and settings configuration
  - Multi-agent support with superior/subordinate relationships

- **Extensible Tool Architecture**: 
  - Base Tool class with execute(), before_execution(), after_execution() methods
  - Response dataclass for tool results
  - Dynamic tool loading from files

- **Essential Tools**: 
  - Response: Final response mechanism
  - Code Execution: Local Python/shell execution
  - Memory: Simple memory save/load
  - Call Subordinate: Agent delegation capability

- **Multi-provider LLM Support**: 
  - OpenAI, Anthropic, and local models via LiteLLM
  - Rate limiting and token management
  - ModelConfig for provider-agnostic configuration

- **MCP Integration**: 
  - Model Context Protocol support
  - MCP Client for stdio and HTTP connections
  - Dynamic MCP tool integration
  - Local fallback when MCP unavailable

- **Extension System**: 
  - Hook-based architecture for customization
  - Extension points: agent_init, monologue_start/end, message_loop_*, system_prompt
  - Dynamic extension loading from files

- **Prompt Management**: 
  - Template-based system prompts
  - JSON communication protocol
  - Dynamic system prompt assembly

- **History Management**: 
  - Conversation tracking with message history
  - Tool result integration
  - Context window management with token-based truncation

## Installation

### From Source

Clone the repository and install the dependencies:

```bash
git clone https://github.com/TerminallyLazy/agent-zero.git
cd agent-zero/agent_zero_lite
pip install -r requirements.txt
```

### Using pip

```bash
pip install agent-zero-lite
```

## Usage

### Quick Start

Run the interactive CLI:

```bash
python run.py
```

### Programmatic Usage

```python
import asyncio
from agent_zero_lite.initialize import initialize_agent, run_agent

async def main():
    # Initialize agent with default configuration
    agent = await initialize_agent()
    
    # Run agent with a user message
    response = await run_agent(agent, "Hello, Agent Zero Lite!")
    
    # Print response
    print(response)

if __name__ == "__main__":
    asyncio.run(main())
```

### Custom Configuration

```python
import asyncio
from agent_zero_lite.initialize import initialize_agent, create_default_config, run_agent
from agent_zero_lite.agent import AgentConfig
from agent_zero_lite.models import ModelConfig, ModelType

async def main():
    # Create a custom configuration
    config = create_default_config()
    
    # Customize the configuration
    config.chat_model = ModelConfig(
        type=ModelType.CHAT,
        provider="openai",
        name="gpt-4o",
        ctx_length=128000,
    )
    
    # Initialize agent with custom configuration
    agent = await initialize_agent(config)
    
    # Run agent with a user message
    response = await run_agent(agent, "Hello, Agent Zero Lite!")
    
    # Print response
    print(response)

if __name__ == "__main__":
    asyncio.run(main())
```

### Example Scripts

Check out the `examples` directory for more usage examples:

- `simple_agent.py`: Basic agent usage
- `memory_example.py`: Using memory tools
- `subordinate_example.py`: Using subordinate agents

## Configuration

Agent Zero Lite can be configured using environment variables:

- `OPENAI_API_KEY`: OpenAI API key
- `ANTHROPIC_API_KEY`: Anthropic API key
- `API_KEY_<PROVIDER>`: API key for other providers

Create a `.env` file in the project directory to set these variables.

## Extending Agent Zero Lite

### Adding New Tools

Create a new Python file in the `tools` directory:

```python
from helpers.tool import Tool, Response

class MyTool(Tool):
    async def execute(self, **kwargs):
        # Tool implementation
        return Response(message="Tool result", break_loop=False)
```

### Adding Extensions

Create a new Python file in the `extensions/<extension_point>` directory:

```python
from helpers.extension import Extension

class MyExtension(Extension):
    async def execute(self, **kwargs):
        # Extension implementation
        pass
```

## License

MIT