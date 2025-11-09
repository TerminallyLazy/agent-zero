# noqa: D401 (docstrings) – internal helper
"""
ACP Server implementation for Agent Zero.

Implements Agent Client Protocol (ACP) as an ASGI middleware,
following the same patterns as MCP and A2A servers.
"""

import asyncio
import json
import threading
import uuid
from typing import Any, Dict, List, Optional

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Receive, Scope, Send

from agent import AgentContext, AgentContextType, UserMessage
from initialize import initialize_agent
from python.helpers import settings
from python.helpers.persist_chat import remove_chat
from python.helpers.print_style import PrintStyle

_PRINTER = PrintStyle(italic=True, font_color="cyan", padding=False)


class DynamicACPProxy:
    """
    Singleton ACP server proxy with dynamic reconfiguration.

    Implements ASGI interface to handle ACP JSON-RPC requests over HTTP.
    Follows the same pattern as DynamicMcpProxy and DynamicA2AProxy.
    """

    _instance: Optional["DynamicACPProxy"] = None
    _lock = threading.RLock()

    def __init__(self):
        self.sessions: Dict[str, AgentContext] = {}
        self.token: Optional[str] = None
        self.reconfigure()

    @staticmethod
    def get_instance() -> "DynamicACPProxy":
        """Get or create singleton instance."""
        if DynamicACPProxy._instance is None:
            with DynamicACPProxy._lock:
                if DynamicACPProxy._instance is None:
                    DynamicACPProxy._instance = DynamicACPProxy()
        return DynamicACPProxy._instance

    def reconfigure(self):
        """
        Reconfigure server settings from current settings.
        Allows token updates without restart.
        """
        current_settings = settings.get_settings()
        # Use ACP token if set, otherwise fall back to MCP token
        self.token = current_settings.get("acp_server_token") or current_settings.get(
            "mcp_server_token"
        )
        _PRINTER.print(
            f"[ACP] Server reconfigured (token: {'set' if self.token else 'not set'})"
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        """
        ASGI interface implementation.

        Routes:
        - POST /acp/jsonrpc - JSON-RPC over HTTP
        - GET /acp/sse - Server-Sent Events for streaming (future)
        """
        request = Request(scope, receive)

        # Validate token
        if not self._validate_token(request):
            response = Response("Unauthorized", status_code=401)
            await response(scope, receive, send)
            return

        path = scope.get("path", "")
        method = scope.get("method", "")

        if path.endswith("/jsonrpc") and method == "POST":
            await self._handle_jsonrpc(request, scope, receive, send)
        elif path.endswith("/sse") and method == "GET":
            # SSE endpoint for streaming (future enhancement)
            response = Response("SSE not yet implemented", status_code=501)
            await response(scope, receive, send)
        else:
            response = Response("Not Found", status_code=404)
            await response(scope, receive, send)

    def _validate_token(self, request: Request) -> bool:
        """
        Validate API token from request headers.
        Supports both Authorization: Bearer and X-API-KEY headers.
        """
        if not self.token:
            return True  # No token configured, allow all

        # Check Authorization header
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            return token == self.token

        # Check X-API-KEY header (MCP pattern)
        api_key = request.headers.get("X-API-KEY", "")
        if api_key:
            return api_key == self.token

        return False

    async def _handle_jsonrpc(
        self, request: Request, scope: Scope, receive: Receive, send: Send
    ):
        """Handle JSON-RPC requests."""
        try:
            body = await request.json()
            result = await self._dispatch_method(body)

            response = JSONResponse(content=result)
            await response(scope, receive, send)

        except Exception as e:
            _PRINTER.print(f"[ACP] Error handling JSON-RPC: {e}")
            error_response = {
                "jsonrpc": "2.0",
                "error": {"code": -32603, "message": str(e)},
                "id": body.get("id") if isinstance(body, dict) else None,
            }
            response = JSONResponse(content=error_response, status_code=500)
            await response(scope, receive, send)

    async def _dispatch_method(self, request: dict) -> dict:
        """
        Dispatch JSON-RPC method to handler.

        Maps ACP methods to Agent Zero operations:
        - initialize → protocol handshake
        - session/newSession → create AgentContext
        - session/prompt → context.communicate()
        - session/listTools → generate tool schemas
        - session/executeTool → execute Agent Zero tool
        - session/close → cleanup context
        """
        method = request.get("method")
        params = request.get("params", {})
        request_id = request.get("id")

        _PRINTER.print(f"[ACP] Method: {method}")

        # Method routing
        handlers = {
            "initialize": self.initialize,
            "session/newSession": self.new_session,
            "session/prompt": self.prompt,
            "session/listTools": self.list_tools,
            "session/executeTool": self.execute_tool,
            "session/close": self.close_session,
        }

        handler = handlers.get(method)
        if not handler:
            raise ValueError(f"Unknown method: {method}")

        result = await handler(params)

        return {"jsonrpc": "2.0", "result": result, "id": request_id}

    async def initialize(self, params: dict) -> dict:
        """
        ACP initialize method - protocol handshake.
        Returns server capabilities and protocol version.
        """
        _PRINTER.print("[ACP] Initialize request")
        return {
            "protocolVersion": "0.1.0",
            "serverInfo": {"name": "Agent Zero ACP Server", "version": "1.0.0"},
            "capabilities": {
                "streaming": False,  # Not yet implemented
                "tools": True,
                "attachments": True,
            },
        }

    async def new_session(self, params: dict) -> dict:
        """
        Create new ACP session mapped to AgentContext.

        Pattern: Create AgentContext(type=BACKGROUND) like A2A does.
        """
        session_id = str(uuid.uuid4())
        persistent = params.get("persistent", False)

        _PRINTER.print(f"[ACP] Creating session {session_id} (persistent={persistent})")

        # Initialize Agent Zero context (following A2A pattern)
        config = initialize_agent()
        context = AgentContext(
            config=config,
            type=AgentContextType.BACKGROUND,
            name=f"ACP-{session_id[:8]}",
        )

        # Store mapping
        self.sessions[session_id] = context

        _PRINTER.print(f"[ACP] Session {session_id} created with context {context.id}")

        return {"sessionId": session_id, "contextId": context.id}

    async def prompt(self, params: dict) -> dict:
        """
        Process user prompt through Agent Zero.

        Converts ACP message format to UserMessage and processes via context.communicate().
        """
        session_id = params.get("sessionId")
        message_content = params.get("message", [])

        _PRINTER.print(f"[ACP] Prompt for session {session_id}")

        # Get context
        context = self.sessions.get(session_id)
        if not context:
            raise ValueError(f"Session not found: {session_id}")

        # Convert ACP message to UserMessage
        user_message = self._convert_acp_message(message_content)

        # Log to UI (like A2A does)
        context.log.log(
            type="user",  # type: ignore[arg-type]
            heading="ACP User Message",
            content=user_message.message,
            kvps={"from": "ACP", "session": session_id[:8]},
            temp=False,
        )

        # Process through Agent Zero
        task = context.communicate(user_message)
        result = await task.result()

        _PRINTER.print(f"[ACP] Prompt completed for session {session_id}")

        return {"sessionId": session_id, "response": str(result)}

    def _convert_acp_message(self, acp_content: List[dict]) -> UserMessage:
        """
        Convert ACP content blocks to Agent Zero UserMessage.

        ACP format:
        [
            {"kind": "text", "text": "user message"},
            {"kind": "file", "path": "/path/to/file"}
        ]

        Agent Zero format:
        UserMessage(message="text", attachments=[paths])
        """
        text_parts = []
        attachments = []

        for content in acp_content:
            if content.get("kind") == "text":
                text_parts.append(content["text"])
            elif content.get("kind") == "file":
                attachments.append(content["path"])

        return UserMessage(
            message="\n".join(text_parts) if text_parts else "", attachments=attachments
        )

    async def list_tools(self, params: dict) -> dict:
        """
        List available tools from MCP servers and local Agent Zero tools.

        Returns ACP-compatible tool schemas combining both MCP and local tools.
        """
        session_id = params.get("sessionId")

        _PRINTER.print(f"[ACP] List tools for session {session_id}")

        context = self.sessions.get(session_id)
        if not context:
            raise ValueError(f"Session not found: {session_id}")

        tools = []

        # Get MCP tools (following agent.py:801-807 pattern)
        try:
            import python.helpers.mcp_handler as mcp_helper

            mcp_tools = mcp_helper.MCPConfig.get_instance().get_tools()
            for tool_dict in mcp_tools:
                # Each tool_dict is {"server.tool_name": {tool_info}}
                for full_name, tool_info in tool_dict.items():
                    tools.append(
                        {
                            "name": full_name,
                            "description": tool_info.get("description", ""),
                            "inputSchema": tool_info.get("input_schema", {}),
                        }
                    )

            _PRINTER.print(f"[ACP] Found {len(mcp_tools)} MCP tools")

        except Exception as e:
            _PRINTER.print(f"[ACP] Could not load MCP tools: {e}")

        # TODO: Add local Agent Zero tools discovery
        # For now, MCP tools are the primary tool interface

        return {"tools": tools}

    async def execute_tool(self, params: dict) -> dict:
        """
        Execute tool through Agent Zero's unified system.

        Follows MCP-first priority pattern from agent.py:801-807:
        1. Try MCP tools first
        2. Fallback to local Agent Zero tools
        """
        session_id = params.get("sessionId")
        tool_name = params.get("toolName")
        arguments = params.get("arguments", {})

        _PRINTER.print(f"[ACP] Execute tool {tool_name} for session {session_id}")

        context = self.sessions.get(session_id)
        if not context:
            raise ValueError(f"Session not found: {session_id}")

        agent = context.agent0
        tool = None

        # Try MCP tools first (following agent.py:801-807 pattern)
        try:
            import python.helpers.mcp_handler as mcp_helper

            mcp_tool = mcp_helper.MCPConfig.get_instance().get_tool(agent, tool_name)
            if mcp_tool:
                tool = mcp_tool
                _PRINTER.print(f"[ACP] Using MCP tool: {tool_name}")

        except Exception as e:
            _PRINTER.print(f"[ACP] MCP tool lookup failed: {e}")

        # Fallback to local Agent Zero tools (following agent.py:890-918 pattern)
        if not tool:
            try:
                tool = agent.get_tool(
                    name=tool_name,
                    method=None,
                    args=arguments,
                    message="",
                    loop_data=None,
                )
                _PRINTER.print(f"[ACP] Using local tool: {tool_name}")

            except Exception as e:
                _PRINTER.print(f"[ACP] Local tool lookup failed: {e}")

        if not tool:
            raise ValueError(f"Tool not found: {tool_name}")

        # Execute tool
        try:
            await tool.before_execution(**arguments)
            response = await tool.execute(**arguments)

            _PRINTER.print(f"[ACP] Tool {tool_name} executed successfully")

            return {
                "sessionId": session_id,
                "toolName": tool_name,
                "result": str(response.message)
                if hasattr(response, "message")
                else str(response),
            }

        except Exception as e:
            _PRINTER.print(f"[ACP] Tool execution failed: {e}")
            raise RuntimeError(f"Tool execution failed: {e}") from e

    async def close_session(self, params: dict) -> dict:
        """
        Close session and cleanup context.

        Pattern: Follow A2A cleanup (reset + remove + remove_chat).
        """
        session_id = params.get("sessionId")

        _PRINTER.print(f"[ACP] Closing session {session_id}")

        # Get and remove context
        context = self.sessions.pop(session_id, None)

        if context:
            # Clean up context (A2A pattern at fasta2a_server.py:114-133)
            context.reset()
            AgentContext.remove(context.id)
            remove_chat(context.id)
            _PRINTER.print(f"[ACP] Session {session_id} closed and cleaned up")
        else:
            _PRINTER.print(f"[ACP] Session {session_id} not found (already closed?)")

        return {"sessionId": session_id, "status": "closed"}
