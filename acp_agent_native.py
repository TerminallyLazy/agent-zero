#!/usr/bin/env python3
"""
Native ACP agent implementation for Agent Zero using the official Python SDK.

This is a direct stdio-based ACP agent that wraps Agent Zero's core functionality,
following the official agent-client-protocol SDK patterns.

Usage in Zed/IDE configuration:
    {
        "agent_servers": {
            "Agent Zero": {
                "command": "/path/to/python",
                "args": ["/path/to/agent-zero/acp_agent_native.py"]
            }
        }
    }

Prerequisites:
    pip install agent-client-protocol
"""

import asyncio
import os
import sys
from pathlib import Path
from typing import Any, Optional

# Add Agent Zero to path
sys.path.insert(0, str(Path(__file__).parent))

try:
    from acp import (
        Agent,
        AgentSideConnection,
        AuthenticateRequest,
        AuthenticateResponse,
        CancelNotification,
        InitializeRequest,
        InitializeResponse,
        LoadSessionRequest,
        LoadSessionResponse,
        NewSessionRequest,
        NewSessionResponse,
        PromptRequest,
        PromptResponse,
        SessionNotification,
        SetSessionModelRequest,
        SetSessionModelResponse,
        SetSessionModeRequest,
        SetSessionModeResponse,
        stdio_streams,
        text_block,
        update_agent_message_text,
    )
except ImportError as e:
    print(
        f"Error: agent-client-protocol not installed or import failed: {e}",
        file=sys.stderr,
    )
    print("Install with: pip install agent-client-protocol", file=sys.stderr)
    import traceback

    traceback.print_exc(file=sys.stderr)
    sys.exit(1)

from agent import AgentContext, AgentContextType, UserMessage
from initialize import initialize_agent
from python.helpers.persist_chat import remove_chat
from python.helpers.print_style import PrintStyle

_PRINTER = PrintStyle(italic=True, font_color="cyan", padding=False)


class AgentZeroACP(Agent):
    """
    Native ACP agent wrapping Agent Zero.

    Implements the Agent Client Protocol by delegating to Agent Zero's
    core functionality while maintaining ACP-compliant interfaces.
    """

    def __init__(self, connection=None):
        super().__init__()
        self.sessions: dict[str, AgentContext] = {}
        self.connection = connection  # Store connection for sending updates
        self._request_id_counter = 0  # For generating unique request IDs
        self._log("Agent Zero ACP agent initialized")

    def _log(self, message: str):
        """Log to stderr (stdout is for ACP protocol)."""
        print(f"[Agent Zero ACP] {message}", file=sys.stderr, flush=True)

    async def _send_client_request(self, method: str, params: dict) -> dict:
        """
        Send a request to the client and wait for response.

        This enables bidirectional JSON-RPC - the agent can call client methods
        like fs/read_text_file, terminal/create, etc.
        """
        if not self.connection:
            raise ValueError("No connection available to send client request")

        self._request_id_counter += 1
        request_id = f"agent_req_{self._request_id_counter}"

        self._log(f"Sending client request: {method} (id: {request_id})")

        # The connection object from ACP SDK should support calling client methods
        # We'll use the extMethod interface to call client-side methods
        try:
            result = await self.connection.extMethod(method, params)
            self._log(f"Client request {method} completed")
            return result
        except Exception as e:
            self._log(f"Error calling client method {method}: {e}")
            raise

    def _generate_tool_call_id(self, tool_name: str) -> str:
        """Generate unique tool call ID."""
        import uuid

        return f"{tool_name}_{uuid.uuid4().hex[:8]}"

    def _get_tool_kind(self, tool_name: str) -> str:
        """
        Map tool name to ACP ToolKind enum.

        ToolKind values: read, edit, delete, move, search, execute, think, fetch, switch_mode, other
        """
        # Normalize tool name to lowercase for matching
        tool_lower = tool_name.lower()

        # File operations
        if "read" in tool_lower and "file" in tool_lower:
            return "read"
        if any(x in tool_lower for x in ["write", "edit", "patch", "replace"]):
            return "edit"
        if "delete" in tool_lower or "remove" in tool_lower:
            return "delete"
        if "move" in tool_lower or "rename" in tool_lower:
            return "move"

        # Search operations
        if any(x in tool_lower for x in ["search", "find", "grep", "glob"]):
            return "search"

        # Execution
        if any(
            x in tool_lower for x in ["bash", "execute", "run", "command", "terminal"]
        ):
            return "execute"

        # External
        if any(x in tool_lower for x in ["web", "fetch", "http", "url"]):
            return "fetch"

        # Internal/thinking
        if any(x in tool_lower for x in ["think", "plan", "task", "todo"]):
            return "think"

        # Mode switching
        if "mode" in tool_lower:
            return "switch_mode"

        # Default
        return "other"

    def _extract_locations(self, tool_name: str, arguments: dict) -> list:
        """
        Extract file/directory locations from tool arguments.

        Returns list of location objects: [{"path": "/absolute/path", "line": null}, ...]
        """
        locations = []

        # Common argument names that contain paths
        path_keys = [
            "path",
            "file_path",
            "filepath",
            "file",
            "directory",
            "dir",
            "folder",
            "source",
            "destination",
            "dest",
            "input_file",
            "output_file",
        ]

        for key in path_keys:
            if key in arguments:
                path_value = arguments[key]
                if isinstance(path_value, str) and path_value:
                    locations.append({"path": path_value, "line": None})

        # Check for line numbers
        if "line" in arguments or "line_number" in arguments:
            line_num = arguments.get("line") or arguments.get("line_number")
            if locations and line_num is not None:
                locations[0]["line"] = line_num

        return locations

    async def _execute_tool_with_notifications(
        self, session_id: str, tool_name: str, arguments: dict, title: str = None
    ):
        """
        Execute a tool with proper ACP notification lifecycle.

        Lifecycle:
        1. Send tool_call notification (status=pending)
        2. Update to in_progress
        3. Execute the tool
        4. Send tool_call_update (status=completed/failed)

        Returns the tool execution result.
        """
        # Generate tool call metadata
        tool_call_id = self._generate_tool_call_id(tool_name)
        kind = self._get_tool_kind(tool_name)
        locations = self._extract_locations(tool_name, arguments)
        display_title = title or f"Using {tool_name}"

        try:
            # 1. Announce tool call (pending)
            await self.connection.sessionUpdate(
                SessionNotification(
                    sessionId=session_id,
                    update={
                        "sessionUpdate": "tool_call",
                        "toolCallId": tool_call_id,
                        "title": display_title,
                        "kind": kind,
                        "status": "pending",
                        "rawInput": arguments,
                        "locations": locations,
                    },
                )
            )
            self._log(f"Tool call announced: {tool_name} ({tool_call_id})")

            # 2. Update to in_progress
            await self.connection.sessionUpdate(
                SessionNotification(
                    sessionId=session_id,
                    update={
                        "sessionUpdate": "tool_call_update",
                        "toolCallId": tool_call_id,
                        "status": "in_progress",
                    },
                )
            )

            # 3. Execute (will be implemented by specific tool methods)
            # This is a placeholder - subclasses or callers will provide actual execution
            result = {"toolCallId": tool_call_id, "arguments": arguments}

            # Return result for caller to handle execution
            return result

        except Exception as e:
            # Send failure notification
            await self.connection.sessionUpdate(
                SessionNotification(
                    sessionId=session_id,
                    update={
                        "sessionUpdate": "tool_call_update",
                        "toolCallId": tool_call_id,
                        "status": "failed",
                        "content": [{"kind": "text", "text": f"Error: {str(e)}"}],
                    },
                )
            )
            self._log(f"Tool call failed: {tool_name} - {e}")
            raise

    async def _complete_tool_call(
        self, session_id: str, tool_call_id: str, result: dict, content: list = None
    ):
        """
        Mark a tool call as completed with results.

        Args:
            session_id: Session ID
            tool_call_id: Tool call ID from _execute_tool_with_notifications
            result: Raw result dict
            content: Optional content blocks for display
        """
        if content is None:
            # Default: convert result to text
            content = [{"kind": "text", "text": str(result)}]

        await self.connection.sessionUpdate(
            SessionNotification(
                sessionId=session_id,
                update={
                    "sessionUpdate": "tool_call_update",
                    "toolCallId": tool_call_id,
                    "status": "completed",
                    "rawOutput": result,
                    "content": content,
                },
            )
        )
        self._log(f"Tool call completed: {tool_call_id}")

    async def read_file(
        self, session_id: str, path: str, line: int = None, limit: int = None
    ) -> str:
        """
        Read a file using the IDE's file system capability.

        Args:
            session_id: Session ID
            path: Absolute path to file
            line: Optional starting line number
            limit: Optional number of lines to read

        Returns:
            File content as string
        """
        # Start tool call notifications
        arguments = {"path": path}
        if line is not None:
            arguments["line"] = line
        if limit is not None:
            arguments["limit"] = limit

        tool_result = await self._execute_tool_with_notifications(
            session_id=session_id,
            tool_name="read_file",
            arguments=arguments,
            title=f"Reading {path}",
        )
        tool_call_id = tool_result["toolCallId"]

        try:
            # Call IDE's file system capability
            params = {"sessionId": session_id, "path": path}
            if line is not None:
                params["line"] = line
            if limit is not None:
                params["limit"] = limit

            result = await self._send_client_request("fs/read_text_file", params)

            # Extract content
            content = result.get("content", "")

            # Complete tool call
            await self._complete_tool_call(
                session_id=session_id,
                tool_call_id=tool_call_id,
                result=result,
                content=[{"kind": "text", "text": content}],
            )

            return content

        except Exception as e:
            # Failure notification already sent by _execute_tool_with_notifications
            self._log(f"Error reading file {path}: {e}")
            raise

    async def write_file(self, session_id: str, path: str, content: str) -> dict:
        """
        Write a file using the IDE's file system capability.

        Args:
            session_id: Session ID
            path: Absolute path to file
            content: Content to write

        Returns:
            Result dict from IDE
        """
        # Start tool call notifications
        arguments = {"path": path, "content": content}

        tool_result = await self._execute_tool_with_notifications(
            session_id=session_id,
            tool_name="write_file",
            arguments=arguments,
            title=f"Writing {path}",
        )
        tool_call_id = tool_result["toolCallId"]

        try:
            # Call IDE's file system capability
            result = await self._send_client_request(
                "fs/write_text_file",
                {"sessionId": session_id, "path": path, "content": content},
            )

            # Complete tool call
            await self._complete_tool_call(
                session_id=session_id,
                tool_call_id=tool_call_id,
                result=result,
                content=[
                    {
                        "kind": "text",
                        "text": f"Wrote {len(content)} characters to {path}",
                    }
                ],
            )

            return result

        except Exception as e:
            self._log(f"Error writing file {path}: {e}")
            raise

    async def execute_command(
        self,
        session_id: str,
        command: str,
        args: list = None,
        cwd: str = None,
        env: dict = None,
    ) -> dict:
        """
        Execute a command using the IDE's terminal capability.

        Args:
            session_id: Session ID
            command: Command to execute
            args: Optional command arguments
            cwd: Optional working directory
            env: Optional environment variables

        Returns:
            Dict with 'output', 'exitStatus', 'terminalId'
        """
        # Start tool call notifications
        arguments = {"command": command, "args": args or [], "cwd": cwd}

        tool_result = await self._execute_tool_with_notifications(
            session_id=session_id,
            tool_name="execute_command",
            arguments=arguments,
            title=f"Running {command}",
        )
        tool_call_id = tool_result["toolCallId"]

        terminal_id = None

        try:
            # 1. Create terminal
            create_params = {"sessionId": session_id, "command": command}
            if args:
                create_params["args"] = args
            if cwd:
                create_params["cwd"] = cwd
            if env:
                create_params["env"] = env

            create_result = await self._send_client_request(
                "terminal/create", create_params
            )
            terminal_id = create_result.get("terminalId")

            self._log(f"Terminal created: {terminal_id}")

            # 2. Wait for exit
            wait_result = await self._send_client_request(
                "terminal/wait_for_exit",
                {"sessionId": session_id, "terminalId": terminal_id},
            )
            exit_status = wait_result.get("exitStatus")

            # 3. Get output
            output_result = await self._send_client_request(
                "terminal/output", {"sessionId": session_id, "terminalId": terminal_id}
            )
            output = output_result.get("output", "")
            truncated = output_result.get("truncated", False)

            # Complete tool call with terminal content
            await self._complete_tool_call(
                session_id=session_id,
                tool_call_id=tool_call_id,
                result={
                    "output": output,
                    "exitStatus": exit_status,
                    "terminalId": terminal_id,
                    "truncated": truncated,
                },
                content=[{"kind": "terminal", "terminalId": terminal_id}],
            )

            return {
                "output": output,
                "exitStatus": exit_status,
                "terminalId": terminal_id,
                "truncated": truncated,
            }

        except Exception as e:
            self._log(f"Error executing command {command}: {e}")
            # Try to clean up terminal if it was created
            if terminal_id:
                try:
                    await self._send_client_request(
                        "terminal/release",
                        {"sessionId": session_id, "terminalId": terminal_id},
                    )
                except:
                    pass
            raise

    async def request_permission(
        self, session_id: str, tool_call_id: str, operation: str, details: dict = None
    ) -> str:
        """
        Request permission from the user for a sensitive operation.

        Args:
            session_id: Session ID
            tool_call_id: ID of the tool call requiring permission
            operation: Description of the operation (e.g., "write file", "execute command")
            details: Optional details about the operation

        Returns:
            Permission result: "allow_once", "allow_always", or "reject"
        """
        self._log(f"Requesting permission for: {operation}")

        # Build tool call details
        tool_call = {"toolCallId": tool_call_id, "operation": operation}
        if details:
            tool_call.update(details)

        # Build permission options
        options = [
            {"optionId": "allow_once", "name": "Allow Once", "kind": "allow_once"},
            {
                "optionId": "allow_always",
                "name": "Always Allow",
                "kind": "allow_always",
            },
            {"optionId": "reject", "name": "Reject", "kind": "reject_once"},
        ]

        try:
            # Request permission via client
            result = await self._send_client_request(
                "session/request_permission",
                {"sessionId": session_id, "toolCall": tool_call, "options": options},
            )

            # Extract outcome
            outcome = result.get("outcome")
            if outcome == "cancelled":
                self._log(f"Permission request cancelled by user")
                return "reject"

            if isinstance(outcome, dict) and "selected" in outcome:
                selected = outcome["selected"]
                self._log(f"Permission granted: {selected}")
                return selected

            # Default to reject if unclear
            self._log(f"Unclear permission response, defaulting to reject")
            return "reject"

        except Exception as e:
            self._log(f"Error requesting permission: {e}")
            # Default to reject on error
            return "reject"

    async def initialize(self, params: InitializeRequest) -> InitializeResponse:
        """Handle ACP initialize request."""
        self._log(f"Initialize request (protocol v{params.protocolVersion})")

        return InitializeResponse(
            protocolVersion=1,
            serverInfo={"name": "Agent Zero", "version": "1.0.0"},
            agentCapabilities={
                "promptCapabilities": {
                    "image": True,  # Agent Zero supports images
                    "audio": False,  # Not supported yet
                    "embeddedContext": True,  # Supports @-mentions
                },
                "mcpCapabilities": {
                    "http": True,  # Agent Zero has MCP HTTP support
                    "sse": True,  # Agent Zero has MCP SSE support
                },
            },
        )

    async def newSession(self, params: NewSessionRequest) -> NewSessionResponse:
        """Create new Agent Zero session."""
        self._log(f"Creating new session (cwd: {params.cwd})")

        # Initialize Agent Zero context
        config = initialize_agent()
        context = AgentContext(
            config=config, type=AgentContextType.BACKGROUND, name="ACP-Session"
        )

        session_id = context.id
        self.sessions[session_id] = context

        self._log(f"Session created: {session_id}")

        return NewSessionResponse(
            sessionId=session_id, cwd=params.cwd or str(Path.cwd())
        )

    async def prompt(self, params: PromptRequest) -> PromptResponse:
        """Process user prompt through Agent Zero."""
        session_id = params.sessionId
        self._log(f"Prompt for session {session_id[:8]}...")

        context = self.sessions.get(session_id)
        if not context:
            raise ValueError(f"Session not found: {session_id}")

        # Convert ACP prompt to UserMessage
        message_text = ""
        attachments = []

        for content in params.prompt:
            # Content blocks are pydantic models, not dicts
            content_type = getattr(content, "type", getattr(content, "kind", None))

            if content_type == "text":
                message_text += getattr(content, "text", "")
            elif content_type == "file":
                attachments.append(getattr(content, "path", ""))

        self._log(f"Processing prompt: {message_text[:50]}...")

        user_message = UserMessage(message=message_text, attachments=attachments)

        # Log to UI
        context.log.log(
            type="user",
            heading="ACP User Message",
            content=user_message.message,
            kvps={"from": "ACP", "session": session_id[:8]},
            temp=False,
        )

        self._log(f"Communicating with Agent Zero (this may take time on first run)...")

        # Process through Agent Zero
        # Note: This can take a while on first run (model initialization, etc.)
        try:
            task = context.communicate(user_message)
            self._log(f"Waiting for Agent Zero response...")

            result = await asyncio.wait_for(
                task.result(), timeout=120.0
            )  # 2 minute timeout

            self._log(
                f"Agent Zero response received: {result[:100] if result else 'None'}..."
            )

            # Send response back to client via sessionUpdate
            if result and self.connection:
                try:
                    # Send the agent's response
                    await self.connection.sessionUpdate(
                        SessionNotification(
                            sessionId=session_id,
                            update=update_agent_message_text(result),
                        )
                    )
                    self._log(f"Response sent to client via sessionUpdate")
                except Exception as e:
                    self._log(f"Error sending sessionUpdate: {e}")
            else:
                if not result:
                    self._log(f"WARNING: No result from Agent Zero")
                if not self.connection:
                    self._log(f"WARNING: No connection available to send response")

        except asyncio.TimeoutError:
            self._log(f"WARNING: Agent Zero response timed out after 120s")
        except Exception as e:
            self._log(f"ERROR processing prompt: {e}")
            import traceback

            traceback.print_exc(file=sys.stderr)

        self._log(f"Prompt completed for session {session_id[:8]}")

        return PromptResponse(stopReason="end_turn")

    async def loadSession(
        self, params: LoadSessionRequest
    ) -> Optional[LoadSessionResponse]:
        """Load existing session - not implemented."""
        self._log(f"loadSession called - not implemented")
        return None

    async def setSessionMode(
        self, params: SetSessionModeRequest
    ) -> Optional[SetSessionModeResponse]:
        """Set session mode - not implemented."""
        self._log(f"setSessionMode called - not implemented")
        return None

    async def setSessionModel(
        self, params: SetSessionModelRequest
    ) -> Optional[SetSessionModelResponse]:
        """Set session model - not implemented."""
        self._log(f"setSessionModel called - not implemented")
        return None

    async def authenticate(
        self, params: AuthenticateRequest
    ) -> Optional[AuthenticateResponse]:
        """Authentication - not required for stdio agent."""
        self._log(f"authenticate called - not implemented")
        return None

    async def cancel(self, params: CancelNotification) -> None:
        """Cancel current operation."""
        self._log(f"cancel called - cancellation not yet implemented")
        # TODO: Implement cancellation of running tasks

    async def extMethod(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Handle extension methods."""
        self._log(f"extMethod called: {method}")
        raise NotImplementedError(f"Extension method not supported: {method}")

    async def extNotification(self, method: str, params: dict[str, Any]) -> None:
        """Handle extension notifications."""
        self._log(f"extNotification called: {method}")


async def main():
    """Entry point for ACP agent."""
    try:
        print("=" * 60, file=sys.stderr, flush=True)
        print("Agent Zero ACP Agent (Native SDK)", file=sys.stderr, flush=True)
        print("=" * 60, file=sys.stderr, flush=True)

        # Create ACP connection over stdio FIRST (before any redirects)
        read_stream, write_stream = await stdio_streams()

        # NOW redirect stdout to stderr to prevent Agent Zero from polluting the JSON-RPC stream
        # The ACP streams above are already connected to the original stdin/stdout
        original_stdout = sys.stdout
        sys.stdout = sys.stderr

        # Create AgentSideConnection (following echo_agent.py example)
        # Parameters: factory function, writer (stdout), reader (stdin)
        # Pass the connection to the agent so it can send sessionUpdate notifications
        AgentSideConnection(
            to_agent=lambda conn: AgentZeroACP(connection=conn),
            input_stream=write_stream,  # Writer for sending responses
            output_stream=read_stream,  # Reader for receiving requests
        )

        print("Agent Zero ready for ACP connections", file=sys.stderr, flush=True)
        print("=" * 60, file=sys.stderr, flush=True)

        # Keep event loop running
        await asyncio.Event().wait()

    except KeyboardInterrupt:
        print("Interrupted by user", file=sys.stderr)
    except Exception as e:
        print(f"Fatal error: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc(file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
