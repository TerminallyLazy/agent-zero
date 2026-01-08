#!/usr/bin/env python3
"""Run Agent Zero as an ACP (Agent Client Protocol) agent.

This script starts Agent Zero in ACP mode using stdio communication,
making it accessible to ACP clients like Zed IDE.

Usage:
    python run_acp.py

For Zed IDE integration, add to your agent configuration:
    {
        "command": "python",
        "args": ["/path/to/agent-zero/run_acp.py"]
    }
"""

import asyncio
import sys
import os

# stderr must be redirected to keep stdio clean for ACP JSON-RPC protocol
log_file = open("/tmp/agent-zero-acp.log", "a")
sys.stderr = log_file

from python.helpers import runtime, dotenv

runtime.initialize()
dotenv.load_dotenv()

from python.helpers.print_style import PrintStyle

try:
    from acp import run_agent
    from python.helpers.acp_adapter import AgentZeroACP, is_available

    ACP_AVAILABLE = True
except ImportError:
    ACP_AVAILABLE = False


async def main():
    if not ACP_AVAILABLE:
        print(
            "Error: ACP SDK not installed. Run: pip install agent-client-protocol",
            file=log_file,
        )
        sys.exit(1)

    if not is_available():
        print("Error: ACP adapter not available.", file=log_file)
        sys.exit(1)

    print("Starting Agent Zero ACP agent (stdio mode)...", file=log_file)

    agent = AgentZeroACP()

    try:
        await run_agent(agent)
    except Exception as e:
        print(f"Error: {e}", file=log_file)
        sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Agent Zero ACP shutting down...", file=log_file)
    finally:
        log_file.close()
