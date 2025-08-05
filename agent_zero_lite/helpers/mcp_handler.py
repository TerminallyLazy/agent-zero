import re
import json
from typing import Dict, Any, Optional, List

from mcp import ClientSession, StdioServerParameters
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamablehttp_client
from mcp.types import CallToolResult, ListToolsResult

from helpers.tool import Tool, Response


def normalize_name(name: str) -> str:
    """
    Normalize a tool name to a consistent format.
    """
    # Lowercase and strip whitespace
    name = name.strip().lower()
    # Replace all non-alphanumeric chars with underscore
    name = re.sub(r"[^\w]", "_", name, flags=re.UNICODE)
    return name


class MCPTool(Tool):
    """
    Tool implementation that delegates to an MCP server.
    """
    def __init__(self, agent: Any, name: str, method: Optional[str], args: Dict[str, Any], 
                 message: str, loop_data: Any, mcp_handler: "MCPHandler", **kwargs):
        super().__init__(agent, name, method, args, message, loop_data, **kwargs)
        self.mcp_handler = mcp_handler

    async def execute(self, **kwargs) -> Response:
        """
        Execute the tool by calling the MCP server.
        """
        try:
            result = await self.mcp_handler.call_tool(self.name, self.args)
            return Response(message=result, break_loop=False)
        except Exception as e:
            return Response(message=f"Error calling MCP tool '{self.name}': {str(e)}", break_loop=False)


class MCPHandler:
    """
    Handler for Model Context Protocol (MCP) integration.
    """
    def __init__(self, agent: Any):
        self.agent = agent
        self.session: Optional[ClientSession] = None
        self.available_tools: List[Dict[str, Any]] = []

    async def connect(self) -> bool:
        """
        Connect to MCP servers specified in the agent config.
        """
        if self.session:
            return True
        
        if not self.agent.config.mcp_servers:
            return False
        
        # Try to connect to each server in the list
        servers = self.agent.config.mcp_servers.split(",")
        for server in servers:
            server = server.strip()
            if not server:
                continue
            
            try:
                if server.startswith("http"):
                    # HTTP server
                    if "sse" in server:
                        self.session = await sse_client(server)
                    else:
                        self.session = await streamablehttp_client(server)
                else:
                    # Stdio server
                    params = StdioServerParameters(command=server)
                    self.session = await ClientSession.create(params)
                
                # If we got here, we successfully connected
                await self._list_tools()
                return True
            except Exception as e:
                print(f"Failed to connect to MCP server {server}: {str(e)}")
        
        return False

    async def _list_tools(self):
        """
        List available tools from the MCP server.
        """
        if not self.session:
            return
        
        try:
            result: ListToolsResult = await self.session.list_tools()
            self.available_tools = result.tools
        except Exception as e:
            print(f"Failed to list MCP tools: {str(e)}")
            self.available_tools = []

    async def find_tool(self, name: str, args: Dict[str, Any], message: str, loop_data: Any) -> Optional[Tool]:
        """
        Find a tool by name in the MCP server.
        """
        if not await self.connect():
            return None
        
        normalized_name = normalize_name(name)
        
        for tool in self.available_tools:
            tool_name = normalize_name(tool.get("name", ""))
            if tool_name == normalized_name:
                return MCPTool(
                    agent=self.agent,
                    name=name,
                    method=None,
                    args=args,
                    message=message,
                    loop_data=loop_data,
                    mcp_handler=self
                )
        
        return None

    async def call_tool(self, name: str, args: Dict[str, Any]) -> str:
        """
        Call a tool on the MCP server.
        """
        if not self.session:
            if not await self.connect():
                return "Failed to connect to MCP server"
        
        try:
            result: CallToolResult = await self.session.call_tool(name, args)
            return result.result
        except Exception as e:
            return f"Error calling tool: {str(e)}"