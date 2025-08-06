# Agent Zero Lite - Installation Guide

## Installation via pip

### Option 1: Install from Local Build

```bash
# Build the package
python -m build

# Install the package
pip install dist/agent_zero_lite-1.0.0*.whl
```

### Option 2: Install from Source (Development)

```bash
# Clone/download the repository
git clone <repository-url>
cd agent-zero-lite

# Install in development mode
pip install -e .
```

### Option 3: Install from PyPI (when published)

```bash
pip install agent-zero-lite
```

## Quick Start

### 1. Initialize a new project

```bash
# Create a new directory for your project
mkdir my-agent-project
cd my-agent-project

# Initialize Agent Zero Lite project
agent-zero-lite init
```

This will create:
- `.agent-zero-lite` (project marker)
- `knowledge/` (for custom knowledge)
- `memory/` (for agent memory)
- `work_dir/` (for file operations)
- `logs/` (for logs)
- `tmp/` (for temporary files)
- `.env` (configuration file)
- `conf/` (configuration files)

### 2. Configure API keys

Edit the `.env` file to add your API keys:

```bash
# Example .env configuration
OPENAI_API_KEY=your_openai_api_key_here
ANTHROPIC_API_KEY=your_anthropic_api_key_here
GOOGLE_API_KEY=your_google_api_key_here

# Optional: Customize server settings
PORT=50001
FLASK_SECRET_KEY=your_secret_key_here
```

### 3. Start the server

```bash
agent-zero-lite start
```

Or with custom settings:

```bash
# Start on different host/port
agent-zero-lite start --host 0.0.0.0 --port 8080

# Start in debug mode
agent-zero-lite start --debug
```

### 4. Access the Web UI

Open your browser to: `http://localhost:50001`

## CLI Commands

### Initialize Project
```bash
agent-zero-lite init [directory]     # Initialize in specified directory (default: current)
agent-zero-lite init --force         # Force re-initialization
```

### Start Server
```bash
agent-zero-lite start                # Start on default host/port (127.0.0.1:50001)
agent-zero-lite start --host 0.0.0.0 # Make accessible from network
agent-zero-lite start --port 8080    # Use custom port
agent-zero-lite start --debug        # Enable debug mode
```

### Project Status
```bash
agent-zero-lite status               # Show current project status
```

### Version Information
```bash
agent-zero-lite --version            # Show version
```

### Short Alias
All commands can also be run using the short alias `azl`:

```bash
azl init
azl start
azl status
```

## Python API Usage

```python
from agent_zero_lite import AgentZeroLite

# Initialize in current directory
agent = AgentZeroLite()

# Initialize in specific directory
agent = AgentZeroLite("/path/to/project")

# Start the web server programmatically
agent.start_server(host="127.0.0.1", port=50001)

# Get the agent context
context = agent.get_agent_context()
```

## Directory Structure

After initialization, your project will have this structure:

```
my-agent-project/
├── .agent-zero-lite          # Project marker file
├── .env                      # Environment configuration
├── .env.example             # Template for environment variables
├── conf/                    # Configuration files
│   └── model_providers.yaml
├── knowledge/               # Knowledge base
│   └── custom/             # Your custom knowledge
│       ├── main/
│       ├── fragments/
│       ├── solutions/
│       └── instruments/
├── memory/                  # Agent memory storage
├── work_dir/               # Working directory for file operations
├── logs/                   # Application logs
└── tmp/                    # Temporary files
    ├── chats/             # Chat history
    └── settings.json      # UI settings
```

## Requirements

- Python 3.8 or higher
- Internet connection for API calls
- At least one LLM API key (OpenAI, Anthropic, Google, etc.)

## Troubleshooting

### Import Errors
If you encounter import errors, make sure you're running from an initialized project directory:

```bash
agent-zero-lite status  # Check if you're in a valid project
agent-zero-lite init    # Initialize if needed
```

### Port Already in Use
If port 50001 is already in use:

```bash
agent-zero-lite start --port 8080  # Use different port
```

### API Key Issues
Make sure your `.env` file contains valid API keys:

```bash
cat .env  # Check your configuration
```

### Permission Issues
Ensure the directory is writable:

```bash
chmod -R 755 .  # Fix permissions if needed
```

For more help, check the project documentation or file an issue on GitHub.