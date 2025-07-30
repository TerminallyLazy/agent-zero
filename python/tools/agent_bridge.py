import asyncio
import json
import aiohttp
import yaml
from typing import Dict, Any, Optional, Tuple, Union
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse
from datetime import datetime, timezone

from python.helpers.tool import Tool, Response
from python.helpers.print_style import PrintStyle
from python.helpers.concurrency_limiter import ConcurrencyLimiter


@dataclass
class AgentCapabilities:
    """Information about a discovered agent."""
    protocol: str  # "ACP" or "A2A"
    endpoint: str
    capabilities: Dict[str, Any]
    version: Optional[str] = None
    agent_id: Optional[str] = None


class AgentBridge(Tool):
    """
    Bridge tool for communicating with remote agents using ACP or A2A protocols.
    
    This tool automatically detects which protocol a remote agent supports and
    provides a unified interface for agent-to-agent communication.
    
    Protocol Detection:
    - ACP: Checks for /.well-known/agent.yml
    - A2A: Attempts JSON-RPC getAgentCard call
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._session_cache: Dict[str, aiohttp.ClientSession] = {}
        self._capabilities_cache: Dict[str, AgentCapabilities] = {}

    async def execute(self, **kwargs) -> Response:
        """
        Execute agent bridge communication.
        
        Args (via self.args):
            endpoint: Target agent endpoint URL
            action: Action to perform (discover, send, call)
            message: Message to send (for send action)
            method: RPC method name (for call action)
            params: Parameters for the action
            timeout: Request timeout in seconds (default: 30)
            
        Returns:
            Response containing the result of the communication
        """
        try:
            endpoint = self.args.get("endpoint", "").strip()
            action = self.args.get("action", "discover").lower()
            timeout = float(self.args.get("timeout", 30))
            
            if not endpoint:
                return Response(
                    message="Error: endpoint parameter is required",
                    break_loop=False
                )
            
            # Normalize endpoint URL
            if not endpoint.startswith(('http://', 'https://')):
                endpoint = f"http://{endpoint}"
            
            PrintStyle(font_color="#2E86AB", bold=True).print(
                f"Agent Bridge: {action} at {endpoint}"
            )
            
            if action == "discover":
                result = await self._discover_agent(endpoint, timeout)
            elif action == "send":
                result = await self._send_message(endpoint, timeout)
            elif action == "call":
                result = await self._call_method(endpoint, timeout)
            else:
                return Response(
                    message=f"Error: Unknown action '{action}'. Use 'discover', 'send', or 'call'",
                    break_loop=False
                )
            
            return Response(message=json.dumps(result, indent=2), break_loop=False)
            
        except Exception as e:
            error_msg = f"Agent bridge error: {str(e)}"
            PrintStyle(font_color="red", bold=True).print(error_msg)
            return Response(message=error_msg, break_loop=False)

    async def _discover_agent(self, endpoint: str, timeout: float) -> Dict[str, Any]:
        """Discover agent capabilities and protocol."""
        if endpoint in self._capabilities_cache:
            capabilities = self._capabilities_cache[endpoint]
            return {
                "protocol": capabilities.protocol,
                "endpoint": capabilities.endpoint,
                "capabilities": capabilities.capabilities,
                "version": capabilities.version,
                "agent_id": capabilities.agent_id,
                "cached": True
            }
        
        # Try ACP first (check for /.well-known/agent.yml)
        acp_result = await self._try_acp_discovery(endpoint, timeout)
        if acp_result:
            return acp_result
            
        # Try A2A (attempt getAgentCard JSON-RPC call)
        a2a_result = await self._try_a2a_discovery(endpoint, timeout)
        if a2a_result:
            return a2a_result
            
        return {
            "protocol": "unknown",
            "endpoint": endpoint,
            "error": "No supported protocol detected",
            "attempted": ["ACP", "A2A"]
        }

    async def _try_acp_discovery(self, endpoint: str, timeout: float) -> Optional[Dict[str, Any]]:
        """Try to discover ACP agent."""
        try:
            well_known_url = urljoin(endpoint, "/.well-known/agent.yml")
            
            async with ConcurrencyLimiter.guard("agent_bridge", 5):
                async with self._get_session() as session:
                    async with session.get(well_known_url, timeout=timeout) as response:
                        if response.status == 200:
                            content = await response.text()
                            agent_info = yaml.safe_load(content)
                            
                            capabilities = AgentCapabilities(
                                protocol="ACP",
                                endpoint=endpoint,
                                capabilities=agent_info,
                                version=agent_info.get("version"),
                                agent_id=agent_info.get("agent_id")
                            )
                            
                            self._capabilities_cache[endpoint] = capabilities
                            
                            PrintStyle(font_color="green").print(
                                f"Discovered ACP agent at {endpoint}"
                            )
                            
                            return {
                                "protocol": "ACP",
                                "endpoint": endpoint,
                                "capabilities": agent_info,
                                "version": agent_info.get("version"),
                                "agent_id": agent_info.get("agent_id"),
                                "discovery_url": well_known_url
                            }
                            
        except Exception as e:
            PrintStyle(font_color="yellow").print(
                f"ACP discovery failed for {endpoint}: {str(e)}"
            )
        
        return None

    async def _try_a2a_discovery(self, endpoint: str, timeout: float) -> Optional[Dict[str, Any]]:
        """Try to discover A2A agent."""
        try:
            # A2A uses JSON-RPC, typically on /rpc or root endpoint
            rpc_endpoints = [
                urljoin(endpoint, "/rpc"),
                urljoin(endpoint, "/"),
                endpoint
            ]
            
            for rpc_url in rpc_endpoints:
                try:
                    rpc_request = {
                        "jsonrpc": "2.0",
                        "method": "getAgentCard",
                        "params": {},
                        "id": 1
                    }
                    
                    async with ConcurrencyLimiter.guard("agent_bridge", 5):
                        async with self._get_session() as session:
                            async with session.post(
                                rpc_url,
                                json=rpc_request,
                                timeout=timeout,
                                headers={"Content-Type": "application/json"}
                            ) as response:
                                if response.status == 200:
                                    result = await response.json()
                                    
                                    if "result" in result:
                                        agent_card = result["result"]
                                        
                                        capabilities = AgentCapabilities(
                                            protocol="A2A",
                                            endpoint=rpc_url,
                                            capabilities=agent_card,
                                            version=agent_card.get("version"),
                                            agent_id=agent_card.get("id") or agent_card.get("agent_id")
                                        )
                                        
                                        self._capabilities_cache[endpoint] = capabilities
                                        
                                        PrintStyle(font_color="green").print(
                                            f"Discovered A2A agent at {rpc_url}"
                                        )
                                        
                                        return {
                                            "protocol": "A2A",
                                            "endpoint": rpc_url,
                                            "capabilities": agent_card,
                                            "version": agent_card.get("version"),
                                            "agent_id": agent_card.get("id") or agent_card.get("agent_id"),
                                            "discovery_method": "getAgentCard",
                                            "agent_card": agent_card,
                                            "skills": agent_card.get("skills", []),
                                            "name": agent_card.get("name", "Unknown Agent"),
                                            "description": agent_card.get("description", "")
                                        }
                                        
                except Exception:
                    continue  # Try next endpoint
                    
        except Exception as e:
            PrintStyle(font_color="yellow").print(
                f"A2A discovery failed for {endpoint}: {str(e)}"
            )
        
        return None

    async def _send_message(self, endpoint: str, timeout: float) -> Dict[str, Any]:
        """Send a message to the remote agent."""
        message = self.args.get("message", "")
        if not message:
            raise ValueError("message parameter is required for send action")
        
        # Discover agent protocol if not cached
        if endpoint not in self._capabilities_cache:
            discovery = await self._discover_agent(endpoint, timeout)
            if discovery.get("protocol") == "unknown":
                raise ValueError(f"Cannot determine protocol for {endpoint}")
        
        capabilities = self._capabilities_cache[endpoint]
        
        if capabilities.protocol == "ACP":
            return await self._send_acp_message(capabilities, message, timeout)
        elif capabilities.protocol == "A2A":
            return await self._send_a2a_message(capabilities, message, timeout)
        else:
            raise ValueError(f"Unsupported protocol: {capabilities.protocol}")

    async def _send_acp_message(self, capabilities: AgentCapabilities, message: str, timeout: float) -> Dict[str, Any]:
        """Send message via ACP protocol."""
        # ACP uses runs endpoint for message execution
        runs_url = urljoin(capabilities.endpoint, "/acp_runs")
        
        payload = {
            "agent_name": "agent-zero",
            "mode": "sync",
            "context_id": self.args.get("context"),
            "input": [
                {
                    "role": "user", 
                    "parts": [
                        {
                            "content": message,
                            "content_type": "text/plain"
                        }
                    ]
                }
            ],
            "session_data": self.args.get("session_data", {}),
            "routing_info": {
                "source_agent": getattr(self.agent, 'agent_name', 'unknown'),
                "protocol": "ACP",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        }
        
        async with ConcurrencyLimiter.guard("agent_bridge", 5):
            async with self._get_session() as session:
                async with session.post(
                    runs_url,
                    json=payload,
                    timeout=timeout,
                    headers={"Content-Type": "application/json"}
                ) as response:
                    result = await response.json()
                    
                    return {
                        "protocol": "ACP",
                        "status": response.status,
                        "response": result,
                        "message_sent": message
                    }

    async def _send_a2a_message(self, capabilities: AgentCapabilities, message: str, timeout: float) -> Dict[str, Any]:
        """Send message via A2A protocol."""
        # A2A uses JSON-RPC
        rpc_request = {
            "jsonrpc": "2.0",
            "method": self.args.get("method", "sendMessage"),
            "params": {
                "message": message,
                "sender": self.agent.agent_name,
                "context": self.args.get("context"),
                "session_data": self.args.get("session_data", {}),
                "routing_info": {
                    "source_agent": getattr(self.agent, 'agent_name', 'unknown'),
                    "protocol": "A2A",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            },
            "id": asyncio.get_event_loop().time()
        }
        
        async with ConcurrencyLimiter.guard("agent_bridge", 5):
            async with self._get_session() as session:
                async with session.post(
                    capabilities.endpoint,
                    json=rpc_request,
                    timeout=timeout,
                    headers={"Content-Type": "application/json"}
                ) as response:
                    result = await response.json()
                    
                    return {
                        "protocol": "A2A",
                        "status": response.status,
                        "response": result,
                        "message_sent": message
                    }

    async def _call_method(self, endpoint: str, timeout: float) -> Dict[str, Any]:
        """Call a specific method on the remote agent."""
        method = self.args.get("method", "")
        if not method:
            raise ValueError("method parameter is required for call action")
        
        params = self.args.get("params", {})
        if isinstance(params, str):
            try:
                params = json.loads(params)
            except json.JSONDecodeError:
                params = {}
        
        # Discover agent protocol if not cached
        if endpoint not in self._capabilities_cache:
            discovery = await self._discover_agent(endpoint, timeout)
            if discovery.get("protocol") == "unknown":
                raise ValueError(f"Cannot determine protocol for {endpoint}")
        
        capabilities = self._capabilities_cache[endpoint]
        
        if capabilities.protocol == "A2A":
            # A2A supports direct method calls via JSON-RPC
            rpc_request = {
                "jsonrpc": "2.0",
                "method": method,
                "params": params,
                "id": asyncio.get_event_loop().time()
            }
            
            async with ConcurrencyLimiter.guard("agent_bridge", 5):
                async with self._get_session() as session:
                    async with session.post(
                        capabilities.endpoint,
                        json=rpc_request,
                        timeout=timeout,
                        headers={"Content-Type": "application/json"}
                    ) as response:
                        result = await response.json()
                        
                        return {
                            "protocol": "A2A",
                            "method": method,
                            "status": response.status,
                            "response": result
                        }
        else:
            # For ACP, convert method call to REST endpoint
            method_url = urljoin(capabilities.endpoint, f"/{method}")
            
            async with ConcurrencyLimiter.guard("agent_bridge", 5):
                async with self._get_session() as session:
                    async with session.post(
                        method_url,
                        json=params,
                        timeout=timeout,
                        headers={"Content-Type": "application/json"}
                    ) as response:
                        result = await response.json()
                        
                        return {
                            "protocol": "ACP",
                            "method": method,
                            "status": response.status,
                            "response": result
                        }

    def _get_session(self) -> aiohttp.ClientSession:
        """Get or create an HTTP session."""
        return aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=60),
            connector=aiohttp.TCPConnector(limit=10, limit_per_host=5)
        )

    async def after_execution(self, response: Response, **kwargs):
        """Clean up resources after execution."""
        await super().after_execution(response, **kwargs)
        
        # Close any open sessions
        for session in self._session_cache.values():
            if not session.closed:
                await session.close()
        self._session_cache.clear()


# Utility functions for agent discovery

async def discover_agent(endpoint: str, timeout: float = 30) -> Optional[AgentCapabilities]:
    """
    Standalone function to discover agent capabilities.
    
    Args:
        endpoint: Agent endpoint URL
        timeout: Discovery timeout in seconds
        
    Returns:
        AgentCapabilities if discovered, None otherwise
    """
    bridge = AgentBridge(
        agent=None,  # type: ignore
        name="agent_bridge",
        method=None,
        args={"endpoint": endpoint, "action": "discover", "timeout": str(timeout)},
        message="",
        loop_data=None
    )
    
    try:
        result = await bridge._discover_agent(endpoint, timeout)
        if result.get("protocol") != "unknown":
            return AgentCapabilities(
                protocol=result["protocol"],
                endpoint=result["endpoint"],
                capabilities=result["capabilities"],
                version=result.get("version"),
                agent_id=result.get("agent_id")
            )
    except Exception:
        pass
    
    return None


def is_valid_agent_url(url: str) -> bool:
    """Check if a URL is a valid agent endpoint."""
    try:
        parsed = urlparse(url)
        return parsed.scheme in ('http', 'https') and bool(parsed.netloc)
    except Exception:
        return False