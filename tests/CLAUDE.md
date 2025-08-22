# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Common Development Commands

### Running Agent Zero
- **Start Web UI**: `python run_ui.py` (default port 50101)
- **Start with custom port**: `python run_ui.py --port=5555`
- **Test FastA2A server**: `python tests/test_fasta2a_client.py`

### Development Setup
- **Install dependencies**: `pip install -r requirements.txt`
- **Install browser binaries**: `playwright install chromium`
- **Build local Docker image**: `docker build -f DockerfileLocal -t agent-zero-local --build-arg CACHE_DATE=$(date +%Y-%m-%d:%H:%M:%S) .`

### Testing
- **Run FastA2A tests**: `python tests/test_fasta2a_client.py`
- **Rate limiter tests**: `python tests/rate_limiter_test.py`

## Architecture Overview

Agent Zero is a dynamic, multi-agent AI framework built around these core concepts:

### Core Components

1. **Agent System (`agent.py`)**
   - `Agent` class: Core agent with message loop, tool processing, and LLM integration
   - `AgentContext` class: Manages agent instances, logging, and inter-agent communication
   - `AgentConfig` class: Configuration for models, SSH settings, and profiles
   - Multi-agent hierarchy with superior/subordinate relationships

2. **Model Integration (`models.py`)**
   - LiteLLM-based abstraction for multiple LLM providers
   - Support for chat, utility, browser, and embedding models
   - Rate limiting and provider configuration via `conf/model_providers.yaml`

3. **Tool System (`python/tools/`)**
   - Dynamic tool loading with hot-swappable functionality
   - Core tools: code execution, browser automation, memory, search, scheduling
   - Tools can be agent-specific (profile-based) or default
   - MCP (Model Context Protocol) server integration

4. **Extension Framework (`python/extensions/`)**
   - Hook-based system for extending agent behavior
   - Extensions organized by lifecycle events (e.g., `message_loop_start`, `tool_execute_before`)
   - Supports memory management, stream processing, and content masking

5. **Memory System (`python/helpers/memory.py`)**
   - FAISS-based vector storage with embedding search
   - Automatic memory consolidation and keyword extraction
   - Configurable memory subdirectories per agent profile

### Key Directories

- **`prompts/`**: System prompts, message templates, and agent behavior definitions
- **`agents/`**: Agent profiles with custom prompts, tools, and configurations
- **`python/api/`**: HTTP API endpoints for web UI and external integrations
- **`python/helpers/`**: Core utilities (file handling, crypto, browser automation, etc.)
- **`webui/`**: Frontend web interface with Alpine.js components
- **`docker/`**: Containerization with base and runtime configurations
- **`instruments/`**: Custom functions and procedures callable by agents

### Agent Behavior and Communication

- **Message Loop**: Continuous interaction cycle with intervention handling
- **Tool Processing**: JSON-based tool requests with argument validation
- **Multi-agent Communication**: Hierarchical structure with A2A (Agent-to-Agent) protocol
- **Context Management**: Persistent chat history with topic organization

### Development Patterns

1. **Profile-Based Customization**: Agent behavior is defined by profile directories in `agents/`
2. **Extension Points**: Use the extension system for cross-cutting concerns
3. **Tool Development**: Create tools in `python/tools/` or agent-specific `agents/{profile}/tools/`
4. **Prompt Engineering**: Modify behavior through prompt files in `prompts/` or `agents/{profile}/prompts/`

### Configuration and Settings

- **Settings**: Managed through `tmp/settings.json` and environment variables
- **Secrets**: Stored in `tmp/secrets.env` with automatic masking in logs
- **MCP Servers**: Configured via web UI for external tool integration
- **SSH/RFC**: Remote execution support for containerized environments

### Web UI and API

- **Flask-based**: REST API with real-time streaming capabilities
- **Authentication**: Support for basic auth, bearer tokens, and API keys
- **File Management**: Upload/download with work directory isolation
- **Chat Export**: JSON-based chat persistence and loading

This architecture enables Agent Zero to be a flexible, extensible framework for building autonomous AI agents that can adapt and learn through interaction.