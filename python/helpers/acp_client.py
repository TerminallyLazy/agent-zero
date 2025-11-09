# noqa: D401 (docstrings) – internal helper
"""
ACP Client implementation for Agent Zero.

Allows Agent Zero to connect to external ACP agents as a client,
enabling Agent-to-Agent communication via ACP protocol.
"""

import asyncio
import json
import uuid
from typing import List, Optional, Dict, Any

from python.helpers.print_style import PrintStyle

_PRINTER = PrintStyle(italic=True, font_color="cyan", padding=False)


class ACPConnection:
    """
    Client connection to an external ACP agent via subprocess.

    Implements JSON-RPC communication over stdio pipes following
    the ACP protocol specification.
    """

    def __init__(self, command: List[str]):
        """
        Initialize ACP connection.

        Args:
            command: Command to spawn ACP agent subprocess (e.g., ["python", "agent.py"])
        """
        self.command = command
        self.process: Optional[asyncio.subprocess.Process] = None
        self.session_id: Optional[str] = None
        self.request_id_counter = 0
        self._read_lock = asyncio.Lock()
        self._write_lock = asyncio.Lock()

    async def connect(self):
        """
        Connect to ACP agent by spawning subprocess and initializing session.

        Performs:
        1. Spawn subprocess with stdin/stdout pipes
        2. Send initialize() request
        3. Send newSession() request
        """
        _PRINTER.print(f"[ACP Client] Connecting to: {' '.join(self.command)}")

        # Spawn subprocess with stdio pipes
        self.process = await asyncio.create_subprocess_exec(
            *self.command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        _PRINTER.print(f"[ACP Client] Process spawned with PID {self.process.pid}")

        # Initialize protocol
        init_response = await self.send_request("initialize", {
            "protocolVersion": "0.1.0",
            "clientInfo": {
                "name": "Agent Zero ACP Client",
                "version": "1.0.0"
            }
        })

        _PRINTER.print(f"[ACP Client] Initialized: {init_response.get('result', {}).get('serverInfo', {}).get('name')}")

        # Create session
        session_response = await self.send_request("session/newSession", {
            "persistent": False
        })

        self.session_id = session_response.get("result", {}).get("sessionId")
        _PRINTER.print(f"[ACP Client] Session created: {self.session_id}")

    async def send_request(self, method: str, params: dict) -> dict:
        """
        Send JSON-RPC request and wait for response.

        Args:
            method: JSON-RPC method name
            params: Method parameters

        Returns:
            JSON-RPC response dict
        """
        if not self.process or not self.process.stdin:
            raise RuntimeError("Not connected - call connect() first")

        request_id = self.request_id_counter
        self.request_id_counter += 1

        request = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": request_id
        }

        # Write request (serialize to JSON and add newline)
        async with self._write_lock:
            request_json = json.dumps(request) + "\n"
            self.process.stdin.write(request_json.encode())
            await self.process.stdin.drain()

        _PRINTER.print(f"[ACP Client] Sent request {request_id}: {method}")

        # Read response
        async with self._read_lock:
            if not self.process.stdout:
                raise RuntimeError("stdout pipe not available")

            response_line = await self.process.stdout.readline()
            if not response_line:
                raise RuntimeError("Connection closed by remote agent")

            response = json.loads(response_line.decode())

        _PRINTER.print(f"[ACP Client] Received response {request_id}")

        # Check for errors
        if "error" in response:
            error = response["error"]
            raise RuntimeError(f"ACP Error {error.get('code')}: {error.get('message')}")

        return response

    async def prompt(self, message: str, attachments: Optional[List[str]] = None) -> str:
        """
        Send user prompt to ACP agent.

        Args:
            message: User message text
            attachments: Optional list of file paths

        Returns:
            Agent response as string
        """
        if not self.session_id:
            raise RuntimeError("Not connected - call connect() first")

        # Build ACP content blocks
        content = [{"kind": "text", "text": message}]

        if attachments:
            for path in attachments:
                content.append({"kind": "file", "path": path})

        # Send prompt request
        response = await self.send_request("session/prompt", {
            "sessionId": self.session_id,
            "message": content
        })

        result = response.get("result", {})
        return result.get("response", "")

    async def close(self):
        """
        Close ACP connection gracefully.

        Performs graceful shutdown sequence:
        1. Close session if exists
        2. Close stdin pipe
        3. Wait for process to exit (5s timeout)
        4. Terminate if still running (2s timeout)
        5. Kill if still running
        """
        if not self.process:
            return

        _PRINTER.print("[ACP Client] Closing connection...")

        # Close session if we have one
        if self.session_id:
            try:
                await self.send_request("session/close", {
                    "sessionId": self.session_id
                })
                _PRINTER.print("[ACP Client] Session closed")
            except Exception as e:
                _PRINTER.print(f"[ACP Client] Error closing session: {e}")

        # Close stdin to signal shutdown
        if self.process.stdin:
            self.process.stdin.close()

        # Wait for process to exit (5s timeout)
        try:
            await asyncio.wait_for(self.process.wait(), timeout=5.0)
            _PRINTER.print("[ACP Client] Process exited cleanly")
            return
        except asyncio.TimeoutError:
            _PRINTER.print("[ACP Client] Process didn't exit, terminating...")

        # Terminate process (2s timeout)
        self.process.terminate()
        try:
            await asyncio.wait_for(self.process.wait(), timeout=2.0)
            _PRINTER.print("[ACP Client] Process terminated")
            return
        except asyncio.TimeoutError:
            _PRINTER.print("[ACP Client] Process didn't terminate, killing...")

        # Kill process as last resort
        self.process.kill()
        await self.process.wait()
        _PRINTER.print("[ACP Client] Process killed")

    async def __aenter__(self):
        """Context manager entry - connect to agent."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - close connection."""
        await self.close()
