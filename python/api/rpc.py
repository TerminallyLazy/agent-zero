from python.helpers.api import ApiHandler, Request, Response
from agent import AgentContext, UserMessage
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional
import json
import uuid
from python.helpers.print_style import PrintStyle


class Rpc(ApiHandler):
    """
    Agent-to-Agent Protocol (A2A) server implementation via JSON-RPC 2.0.
    
    Provides JSON-RPC 2.0 endpoints for A2A-compliant agent communication.
    """
    
    @classmethod
    def requires_auth(cls) -> bool:
        return False
    
    @classmethod
    def get_methods(cls) -> list[str]:
        return ["GET", "POST"]
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._active_tasks: Dict[str, Dict[str, Any]] = {}
    
    async def process(self, input: dict, request: Request) -> dict | Response:
        """Handle JSON-RPC 2.0 requests."""
        try:
            if not input or "jsonrpc" not in input or input["jsonrpc"] != "2.0":
                return self._create_error_response(None, -32600, "Invalid Request")
            
            method = input.get("method")
            params = input.get("params", {})
            request_id = input.get("id")
            
            if not method:
                return self._create_error_response(request_id, -32600, "Invalid Request")
            
            # Route to appropriate method handler
            if method == "getAgentCard":
                result = await self._get_agent_card(params)
            elif method == "sendMessage":
                result = await self._send_message(params)
            elif method == "executeTask":
                result = await self._execute_task(params)
            elif method == "getStatus":
                result = await self._get_status(params)
            elif method == "listCapabilities":
                result = await self._list_capabilities(params)
            else:
                return self._create_error_response(request_id, -32601, "Method not found")
            
            return self._create_success_response(request_id, result)
            
        except json.JSONDecodeError:
            return self._create_error_response(None, -32700, "Parse error")
        except Exception as e:
            return self._create_error_response(request_id, -32603, f"Internal error: {str(e)}")
    
    async def _get_agent_card(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Get agent card with capabilities and information."""
        return {
            "id": "agent-zero",
            "name": "Agent Zero",
            "description": "Personal, organic agentic AI framework designed to grow and learn with users",
            "version": "1.0.0",
            "protocol": "A2A",
            "capabilities": [
                {
                    "name": "reasoning",
                    "description": "Advanced reasoning and problem-solving capabilities",
                    "parameters": {}
                },
                {
                    "name": "tool_execution",
                    "description": "Execute various tools including code, web search, file operations",
                    "parameters": {
                        "supported_languages": ["python", "javascript", "bash"],
                        "file_operations": ["read", "write", "search"],
                        "web_capabilities": ["search", "browse", "scrape"]
                    }
                },
                {
                    "name": "memory_management",
                    "description": "Persistent memory system for learning and adaptation",
                    "parameters": {
                        "storage_types": ["fragments", "solutions", "user_data"],
                        "search_capabilities": ["semantic", "keyword"]
                    }
                },
                {
                    "name": "planning",
                    "description": "Multi-step task planning and execution",
                    "parameters": {}
                },
                {
                    "name": "sub_agent_creation",
                    "description": "Create and manage subordinate agents",
                    "parameters": {
                        "max_subordinates": 10,
                        "communication_protocols": ["ACP", "A2A"]
                    }
                }
            ],
            "supported_content_types": [
                "text/plain",
                "application/json", 
                "image/png",
                "image/jpeg",
                "application/pdf"
            ],
            "endpoints": {
                "rpc": "/rpc",
                "alternative_rpc": "/rpc"
            },
            "authentication": {
                "required": False,
                "methods": []
            },
            "rate_limits": {
                "requests_per_minute": 60,
                "concurrent_tasks": 5
            },
            "metadata": {
                "framework": "Agent Zero",
                "language": "Python",
                "async_support": True,
                "streaming": False,
                "multimodal": True,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "status": "active"
            }
        }
    
    async def _send_message(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Send a message to the agent."""
        message = params.get("message", "")
        sender = params.get("sender", "unknown")
        context_id = params.get("context")
        session_data = params.get("session_data", {})
        routing_info = params.get("routing_info", {})
        
        if not message:
            raise ValueError("Message parameter is required")
        
        try:
            # Get or create context - use provided context_id to maintain session continuity
            context = self.get_context(context_id) if context_id else self.get_context("")
            
            # Log routing information
            if routing_info.get("source_agent"):
                PrintStyle(
                    background_color="#8E44AD", font_color="white", bold=True, padding=True
                ).print(f"A2A Message from {routing_info.get('source_agent')} via {routing_info.get('protocol')}")
            else:
                PrintStyle(
                    background_color="#8E44AD", font_color="white", bold=True, padding=True
                ).print(f"A2A Message from {sender}")
            
            PrintStyle(font_color="white", padding=False).print(f"> {message}")
            
            # Store session data in context if provided
            if session_data:
                for key, value in session_data.items():
                    context.set_data(f"session_{key}", value)
            
            # Start agent communication
            task, context = context.communicate(UserMessage(message)), context
            result = await task.result()
            
            response_id = str(uuid.uuid4())
            
            return {
                "response_id": response_id,
                "message": str(result),
                "sender": "agent-zero",
                "recipient": sender,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "context_id": context.id,
                "status": "completed"
            }
            
        except Exception as e:
            PrintStyle(font_color="red", bold=True).print(f"A2A message error: {str(e)}")
            raise e
    
    async def _execute_task(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a specific task."""
        task_description = params.get("task", "")
        task_id = params.get("task_id", str(uuid.uuid4()))
        context_id = params.get("context")
        priority = params.get("priority", "normal")
        session_data = params.get("session_data", {})
        routing_info = params.get("routing_info", {})
        
        if not task_description:
            raise ValueError("Task description is required")
        
        try:
            # Create task record
            task_data = {
                "id": task_id,
                "description": task_description,
                "status": "running",
                "priority": priority,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "context_id": context_id
            }
            
            self._active_tasks[task_id] = task_data
            
            # Get or create context - use provided context_id to maintain session continuity
            context = self.get_context(context_id) if context_id else self.get_context("")
            
            # Log routing information
            if routing_info.get("source_agent"):
                PrintStyle(
                    background_color="#8E44AD", font_color="white", bold=True, padding=True
                ).print(f"A2A Task from {routing_info.get('source_agent')} via {routing_info.get('protocol')}: {task_id}")
            else:
                PrintStyle(
                    background_color="#8E44AD", font_color="white", bold=True, padding=True
                ).print(f"A2A Task Execution: {task_id}")
            
            PrintStyle(font_color="white", padding=False).print(f"> {task_description}")
            
            # Store session data in context if provided
            if session_data:
                for key, value in session_data.items():
                    context.set_data(f"session_{key}", value)
            
            # Execute the task
            task, context = context.communicate(UserMessage(task_description)), context
            result = await task.result()
            
            # Update task record
            task_data["status"] = "completed"
            task_data["result"] = str(result)
            task_data["updated_at"] = datetime.now(timezone.utc).isoformat()
            
            return {
                "task_id": task_id,
                "status": "completed",
                "result": str(result),
                "created_at": task_data["created_at"],
                "completed_at": task_data["updated_at"],
                "context_id": context.id
            }
            
        except Exception as e:
            # Update task record with error
            if task_id in self._active_tasks:
                self._active_tasks[task_id]["status"] = "failed"
                self._active_tasks[task_id]["error"] = str(e)
                self._active_tasks[task_id]["updated_at"] = datetime.now(timezone.utc).isoformat()
            
            PrintStyle(font_color="red", bold=True).print(f"A2A task execution error: {str(e)}")
            raise e
    
    async def _get_status(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Get agent or task status."""
        task_id = params.get("task_id")
        
        if task_id:
            # Return specific task status
            if task_id not in self._active_tasks:
                raise ValueError(f"Task {task_id} not found")
            
            task_data = self._active_tasks[task_id]
            return {
                "task_id": task_id,
                "status": task_data["status"],
                "created_at": task_data["created_at"],
                "updated_at": task_data["updated_at"],
                "result": task_data.get("result"),
                "error": task_data.get("error")
            }
        else:
            # Return agent status
            return {
                "agent_id": "agent-zero",
                "status": "active",
                "active_tasks": len([t for t in self._active_tasks.values() if t["status"] == "running"]),
                "total_tasks": len(self._active_tasks),
                "uptime": "active",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
    
    async def _list_capabilities(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List agent capabilities."""
        capability_filter = params.get("filter")
        
        agent_card = await self._get_agent_card({})
        capabilities = agent_card["capabilities"]
        
        if capability_filter:
            # Filter capabilities based on name or description
            filtered_capabilities = []
            for cap in capabilities:
                if (capability_filter.lower() in cap["name"].lower() or 
                    capability_filter.lower() in cap["description"].lower()):
                    filtered_capabilities.append(cap)
            capabilities = filtered_capabilities
        
        return {
            "capabilities": capabilities,
            "total_count": len(capabilities),
            "filtered": bool(capability_filter)
        }
    
    def _create_success_response(self, request_id: Any, result: Any) -> Dict[str, Any]:
        """Create successful JSON-RPC 2.0 response."""
        return {
            "jsonrpc": "2.0",
            "result": result,
            "id": request_id
        }
    
    def _create_error_response(self, request_id: Any, code: int, message: str) -> Dict[str, Any]:
        """Create error JSON-RPC 2.0 response."""
        return {
            "jsonrpc": "2.0",
            "error": {
                "code": code,
                "message": message
            },
            "id": request_id
        }