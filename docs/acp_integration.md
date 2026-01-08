# Agent Zero ACP Integration

The Agent Client Protocol (ACP) integration allows Agent Zero to function as a standardized agent that can be used by any ACP-compliant client. This is particularly useful for integrating Agent Zero directly into IDEs like [Zed](https://zed.dev/).

## Overview

ACP is a standard protocol for AI agent communication, similar to how LSP (Language Server Protocol) works for IDE features. By implementing ACP, Agent Zero becomes accessible to a wider range of tools and environments without needing custom integrations for each.

Key benefits of ACP integration:
- **Standardized Communication**: Uses JSON-RPC over stdio.
- **IDE Integration**: Works seamlessly with Zed IDE's assistant panel.
- **Real-time Streaming**: Supports streaming of reasoning (thoughts) and responses.
- **Tool Visibility**: Displays tool calls and their results directly in the client.

## Quick Start

### 1. Prerequisites
Install the ACP Python SDK:
```bash
pip install agent-client-protocol
```

### 2. Running in ACP Mode
You can run Agent Zero in ACP mode using the provided entry point:
```bash
python run_acp.py
```
This starts the agent using stdio communication. Since stdio is used for the protocol, all other output (logs, errors) is redirected to `/tmp/agent-zero-acp.log`.

## Zed IDE Integration

To use Agent Zero in Zed, you need to add it to your `settings.json`.

1. Open Zed.
2. Open settings (`Cmd+,` or `Ctrl+,`).
3. Add Agent Zero to your `agents` configuration:

```json
{
  "agents": {
    "agent-zero": {
      "command": {
        "program": "python3",
        "args": ["/absolute/path/to/agent-zero/run_acp.py"]
      }
    }
  }
}
```
*Note: Replace `/absolute/path/to/agent-zero/` with the actual path to your Agent Zero installation.*

## Architecture

The ACP integration consists of three main components:

1.  **`run_acp.py`**: The entry point that sets up the environment and launches the ACP agent.
2.  **`AgentZeroACP` (`python/helpers/acp_adapter.py`)**: An adapter that maps ACP sessions to Agent Zero's `AgentContext`. Each new ACP session creates a background Agent Zero context.
3.  **`ACPStreamHandler` (`python/helpers/acp_stream_handler.py`)**: Handles the conversion of Agent Zero's internal streaming events (response chunks, reasoning chunks, tool starts/results) into ACP session updates.

### Mapping
- **ACP Session** → **Agent Zero Context**: Each conversation in the client is isolated in its own Agent Zero context.
- **ACP Prompt** → **`communicate()`**: User messages are sent to the agent's communication loop.
- **ACP Thoughts** → **LLM Reasoning**: Streaming reasoning from models is displayed as "thoughts" in the client.
- **ACP Tool Calls** → **AZ Tool Execution**: When the agent uses a tool, it's displayed as a tool call in the client interface.

## Features Supported

- [x] **Full Streaming**: Both reasoning and final response are streamed in real-time.
- [x] **Tool Notifications**: Clients are notified when a tool starts and when it finishes with a result.
- [x] **Conversation Persistence**: Sessions are mapped to persistent contexts until ended.
- [x] **Cancellation**: Ongoing prompts can be cancelled from the client.

## Troubleshooting

### Logs
Check `/tmp/agent-zero-acp.log` for any internal errors or logs during ACP execution.

### Path Issues
Ensure the path in Zed's `settings.json` is absolute and points to the correct `python3` executable and `run_acp.py` script.

### Missing SDK
If you see an error about `acp` module not found, ensure you've installed `agent-client-protocol`.
