# Agent Zero Lite

A lightweight, cross-platform Python implementation of Agent Zero that maintains the core architecture and design patterns while removing non-essential features.

## Features

- **Core Agent System**: Agent, AgentContext, and AgentConfig classes
- **Extensible Tool Architecture**: Base Tool class with dynamic tool loading
- **Essential Tools**: Response, Code Execution, Memory, and Call Subordinate
- **Multi-provider LLM Support**: OpenAI, Anthropic, and local models via LiteLLM
- **MCP Integration**: Model Context Protocol support
- **Extension System**: Hook-based architecture for customization
- **Prompt Management**: Template-based system prompts
- **History Management**: Conversation tracking with token management

## Installation

```bash
pip install -r requirements.txt
```

## Usage

```python
import asyncio
from initialize import initialize_agent, run_agent

async def main():
    # Initialize agent
    agent = await initialize_agent()
    
    # Run agent with a user message
    response = await run_agent(agent, "Hello, Agent Zero Lite!")
    
    # Print response
    print(response)

if __name__ == "__main__":
    asyncio.run(main())
```

Or run the interactive CLI:

```bash
python initialize.py
```

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