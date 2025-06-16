# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Common Development Commands

### Running the Application
- **Docker (Recommended)**: `docker pull frdel/agent-zero-run && docker run -p 50001:80 frdel/agent-zero-run` - Visit http://localhost:50001
- **Web UI**: `python run_ui.py` - Launches Flask web interface on port 50001
- **CLI Interface**: `python run_cli.py` - Runs command-line interface
- **Initialize**: `python initialize.py` - Sets up the agent framework

### Development Setup
- **Environment**: Copy `example.env` to `.env` and configure API keys for providers (OpenAI, Anthropic, Google, Groq, etc.)
- **Dependencies**: `pip install -r requirements.txt` - Installs 32 packages including Flask, LiteLLM, FAISS, Playwright
- **Playwright Setup**: `playwright install` - Required for browser automation tools

### Testing
- **No formal test framework** - Tests are ad-hoc scripts in root directory with `test_*.py` pattern
- Focus on LiteLLM integration and model provider compatibility testing
- When adding tests, follow existing pattern in test files

## High-Level Architecture

### Hierarchical Multi-Agent System
Agent Zero implements a superior-subordinate agent architecture where:
- **Agent 0** (user) → **Agent 1** → **Agent 2**, etc.
- Complex tasks are broken down and delegated through the hierarchy
- Each agent reports back to its superior with structured communication
- Context is maintained across the entire agent chain

### Core Components

#### Agent System (`agent.py`)
- `AgentContext`: Manages agent state, configuration, and lifecycle
- `Agent`: Core implementation with message processing loop
- Hierarchical communication and task delegation
- Automatic context management and cleanup

#### Model Integration (`models.py`) 
- **LiteLLM wrapper** providing unified interface for 20+ providers
- Separate models for different operations: chat, utility, embeddings, browser
- Built-in rate limiting and provider-specific configuration
- Base URL mappings for local/custom deployments

#### Tool System (`/python/tools/`)
- Standardized tool interface with JSON-based responses
- **Core tools**: code execution, web search, memory, browser automation, file management
- Dynamic tool discovery and loading
- Each tool has corresponding prompt instructions in `/prompts/default/`

#### Memory & Knowledge (`/python/helpers/memory.py`)
- **Vector-based memory** using FAISS with sentence-transformers embeddings
- Automatic memory consolidation and retrieval based on conversation importance
- Persistent knowledge base storage in `/knowledge/`
- Context-aware memory querying and summarization

#### Extension System (`/python/extensions/`)
- **Hook-based architecture** for customizing agent behavior
- Extensions run at specific lifecycle points (message start/end, prompts, etc.)
- Priority-based execution order using filename prefixes (`_10_`, `_50_`)
- Examples: history organization, memory recall, datetime injection

### Prompt-Driven Architecture
All agent behavior is defined through markdown prompts in `/prompts/`:
- `agent.system.main.md`: Core agent instructions and role definition
- `agent.system.tool.*.md`: Individual tool usage instructions
- `fw.*.md`: Framework messages and communication templates
- Template inclusion system with `{{ include }}` syntax for modular prompts

### Flask Web API (`/python/api/`)
- **40+ API endpoints** for chat, settings, file management, agent control
- Real-time streaming using Server-Sent Events
- File upload/download capabilities
- Settings management for dynamic configuration

### Docker Integration
- **Multi-stage builds** with base system dependencies and runtime image
- Persistent volume mounting for `/a0` (agent workspace)
- Integrated SearXNG container for web search
- Both standard and CUDA-enabled variants available

## Development Guidelines

### Working with Agents
- Agent behavior is **entirely prompt-driven** - modify files in `/prompts/` to change behavior
- Agents use structured communication: "Thoughts:", "Tool name:", responses
- Context is automatically managed but can be customized through prompts
- Test agent changes in isolated Docker containers for safety

### Tool Development
- Inherit from base `Tool` class in `/python/tools/`
- Implement standardized interface with JSON responses
- Create corresponding prompt file in `/prompts/default/agent.system.tool.[name].md`
- Tools are automatically discovered and loaded at runtime

### Memory System Usage
- Memory is automatically saved/loaded based on conversation importance scoring
- FAISS similarity search retrieves relevant historical context
- Knowledge base files in `/knowledge/` provide persistent information
- Memory queries use embedding-based similarity matching

### Model Configuration
- Configure providers via `.env` file with API keys
- LiteLLM handles provider-specific parameters and rate limiting
- Use different models for different operations (chat vs utility vs embeddings)
- Model selection can be overridden in Web UI settings

### Extension Development
- Create files in `/python/extensions/` with priority prefixes
- Hook into agent lifecycle events: `message_loop_start`, `message_loop_end`, etc.
- Can modify prompts, inject additional context, or trigger side effects
- Use `register_extension` pattern for proper integration

## Important Configuration

### Environment Variables (`.env`)
- **API Keys**: OpenAI, Anthropic, Google, Groq, Mistral, OpenRouter, etc.
- **Azure OpenAI**: Separate keys and endpoint configuration
- **Local Models**: Ollama, LM Studio base URLs
- **Web UI**: Port configuration, Cloudflare settings
- **System**: Tokenizer parallelism, development flags

### Key File Locations
- `/prompts/`: All agent behavior and tool instructions
- `/python/tools/`: Tool implementations
- `/python/helpers/`: Core systems (memory, settings, files, etc.)
- `/python/extensions/`: Behavior extensions
- `/memory/`: FAISS vector database storage
- `/knowledge/`: Persistent knowledge base
- `/logs/`: HTML chat logs for each session
- `/tmp/`: Runtime data (chats, downloads, playwright cache)

### Web UI Structure (`/webui/`)
- `/js/`: Alpine.js components and API clients
- `/css/`: Component stylesheets
- `/components/`: Reusable UI elements
- Real-time streaming interface with intervention capabilities

## Security Considerations
- Agents execute arbitrary code - **always run in Docker containers**
- File system access is sandboxed within container environment
- API keys must be properly configured and secured
- Web search goes through containerized SearXNG proxy
- Browser automation runs in isolated Playwright context