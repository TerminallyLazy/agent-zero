from python.helpers.api import ApiHandler, Request, Response
from agent import AgentContext, UserMessage
from datetime import datetime, timezone
from typing import Dict, List, Any
import json
import uuid
from python.helpers.print_style import PrintStyle


class AcpRuns(ApiHandler):
    """ACP Runs endpoint for creating and managing agent runs."""
    
    @classmethod
    def requires_auth(cls) -> bool:
        return False
    
    @classmethod
    def get_methods(cls) -> list[str]:
        return ["GET", "POST"]
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._active_runs: Dict[str, Dict[str, Any]] = {}
        self._run_events: Dict[str, List[Dict[str, Any]]] = {}
    
    async def process(self, input: dict, request: Request) -> dict | Response:
        method = request.method
        
        if method == "POST":
            return await self._create_run(input, request)
        elif method == "GET":
            run_id = input.get("run_id")
            if run_id:
                return await self._get_run(run_id)
            else:
                return {"error": "run_id required for GET"}, 400
        else:
            return {"error": "Method not allowed"}, 405
    
    async def _create_run(self, input: dict, request: Request) -> dict:
        """Create a new agent run."""
        try:
            agent_name = input.get("agent_name", "agent-zero")
            input_messages = input.get("input", [])
            mode = input.get("mode", "sync")  # sync, async, stream
            context_id = input.get("context_id")
            session_data = input.get("session_data", {})
            routing_info = input.get("routing_info", {})
            
            if agent_name != "agent-zero":
                return {"error": "Agent not found"}, 404
            
            # Create run ID
            run_id = str(uuid.uuid4())
            
            # Extract message content
            message_text = ""
            if input_messages:
                for msg in input_messages:
                    if msg.get("role") == "user":
                        parts = msg.get("parts", [])
                        for part in parts:
                            if part.get("content_type") == "text/plain":
                                message_text += part.get("content", "") + " "
            
            message_text = message_text.strip()
            if not message_text:
                return {"error": "No message content provided"}, 400
            
            # Create run record
            run_data = {
                "id": run_id,
                "agent_name": agent_name,
                "status": "running",
                "mode": mode,
                "input": input_messages,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "context_id": context_id,
                "message": message_text
            }
            
            self._active_runs[run_id] = run_data
            self._run_events[run_id] = []
            
            # Add initial event
            self._add_run_event(run_id, "run_created", {
                "run_id": run_id,
                "agent_name": agent_name,
                "mode": mode
            })
            
            # Process the message
            try:
                # Get or create context - use provided context_id to maintain session continuity
                context = self.get_context(context_id) if context_id else self.get_context("")
                
                # Log routing information if this is from another agent
                if routing_info.get("source_agent"):
                    PrintStyle(
                        background_color="#2E86AB", font_color="white", bold=True, padding=True
                    ).print(f"ACP Run {run_id}: Message from {routing_info.get('source_agent')} via {routing_info.get('protocol')}")
                else:
                    PrintStyle(
                        background_color="#2E86AB", font_color="white", bold=True, padding=True
                    ).print(f"ACP Run {run_id}: Processing message")
                
                PrintStyle(font_color="white", padding=False).print(f"> {message_text}")
                
                # Store session data in context if provided
                if session_data:
                    for key, value in session_data.items():
                        context.set_data(f"session_{key}", value)
                
                # Start agent communication
                task, context = context.communicate(UserMessage(message_text)), context
                result = await task.result()
                
                run_data["status"] = "completed"
                run_data["output"] = str(result)
                run_data["updated_at"] = datetime.now(timezone.utc).isoformat()
                
                self._add_run_event(run_id, "run_completed", {
                    "run_id": run_id,
                    "output": str(result)
                })
                
                return {
                    "id": run_id,
                    "status": "completed",
                    "output": str(result),
                    "created_at": run_data["created_at"],
                    "updated_at": run_data["updated_at"]
                }
                
            except Exception as e:
                run_data["status"] = "failed"
                run_data["error"] = str(e)
                run_data["updated_at"] = datetime.now(timezone.utc).isoformat()
                
                self._add_run_event(run_id, "run_failed", {
                    "run_id": run_id,
                    "error": str(e)
                })
                
                return {
                    "id": run_id,
                    "status": "failed",
                    "error": str(e),
                    "created_at": run_data["created_at"],
                    "updated_at": run_data["updated_at"]
                }
                
        except Exception as e:
            return {"error": str(e)}, 500
    
    async def _get_run(self, run_id: str) -> dict:
        """Get run status."""
        if run_id not in self._active_runs:
            return {"error": "Run not found"}, 404
        
        run_data = self._active_runs[run_id]
        
        return {
            "id": run_id,
            "status": run_data["status"],
            "agent_name": run_data["agent_name"],
            "mode": run_data["mode"],
            "created_at": run_data["created_at"],
            "updated_at": run_data["updated_at"],
            "output": run_data.get("output"),
            "error": run_data.get("error")
        }
    
    def _add_run_event(self, run_id: str, event_type: str, data: Dict[str, Any]):
        """Add an event to a run's event log."""
        if run_id not in self._run_events:
            self._run_events[run_id] = []
        
        event = {
            "id": str(uuid.uuid4()),
            "type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": data
        }
        
        self._run_events[run_id].append(event)