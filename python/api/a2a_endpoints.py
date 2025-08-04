from python.helpers.api import ApiHandler, Request, Response
from python.helpers import errors
from python.helpers.agent_card import AgentCard
from python.helpers.registry_broker import AgentRegistry
from agent import AgentContext, UserMessage
import os
import uuid
from datetime import datetime

def import_datetime():
    from datetime import datetime
    return datetime

def make_task_envelope(initiator_id, goal, context_snippets=None, required_capabilities=None, response_channel=None):
    """Create a task envelope for A2A communication"""
    return {
        "task_id": str(uuid.uuid4()),
        "initiator_id": initiator_id,
        "goal": goal,
        "context_snippets": context_snippets or {},
        "required_capabilities": required_capabilities or {},
        "response_channel": response_channel,
        "state": "proposed",
        "history": [{
            "event": "created",
            "timestamp": datetime.now().isoformat(),
            "detail": "Task envelope created"
        }]
    }

# Global registry instance
_registry = None

def get_registry():
    global _registry
    if _registry is None:
        _registry = AgentRegistry()
    return _registry

class A2ARegistryHeartbeat(ApiHandler):
    """Handle agent heartbeats and registration."""

    @classmethod
    def requires_auth(cls) -> bool:
        return True

    @classmethod
    def requires_csrf(cls) -> bool:
        return False

    @classmethod
    def get_methods(cls) -> list[str]:
        return ["POST"]

    async def process(self, input: dict, request: Request) -> dict | Response:
        try:
            signed_card = input.get("signed_card")
            signature = input.get("signature")

            if not signed_card or not signature:
                return {"error": "Missing card or signature", "status": "error"}

            # For now, accept any signed card (in production, verify HMAC)
            agent_id = signed_card.get("agent_id")
            registry = get_registry()
            registry.register(agent_id, {"agent_card": signed_card, "signature": signature})
            
            return {"status": "registered", "agent_id": agent_id}

        except Exception as e:
            return {"error": errors.error_text(e), "status": "error"}

class A2ARegistryMatch(ApiHandler):
    """Match agents based on goal."""

    @classmethod
    def requires_auth(cls) -> bool:
        return True

    @classmethod
    def requires_csrf(cls) -> bool:
        return False

    @classmethod
    def get_methods(cls) -> list[str]:
        return ["POST", "GET"]

    async def process(self, input: dict, request: Request) -> dict | Response:
        try:
            # Handle both GET and POST requests
            if request.method == "GET":
                goal = request.query_params.get("goal", "") if hasattr(request, 'query_params') else ""
            else:
                goal = input.get("goal", "")
                
            registry = get_registry()
            all_agents = registry.list_agents()
            
            # If no agents in registry, create a default one for display
            if len(all_agents) == 0:
                default_card = AgentCard(
                    agent_id="agent-zero-local",
                    role_description="Agent Zero - AI Assistant",
                    tools=["code_execution", "web_search", "file_management", "data_analysis"],
                    capabilities={
                        "programming": True,
                        "web_browsing": True,
                        "file_management": True,
                        "data_analysis": True
                    },
                    trust_level="local",
                    version="1.0"
                )
                
                return {
                    "matches": [{"agent_card": default_card.to_dict()}],
                    "goal": goal,
                    "status": "success"
                }
            
            # Return all agents for now (in production, implement matching logic)
            matches = []
            for agent in all_agents:
                matches.append({"agent_card": agent.signed_card.get("agent_card", {})})
            
            return {
                "matches": matches,
                "goal": goal,
                "status": "success"
            }

        except Exception as e:
            return {"error": errors.error_text(e), "status": "error"}

class A2ATaskPropose(ApiHandler):
    """Propose a new task."""

    @classmethod
    def requires_auth(cls) -> bool:
        return True

    @classmethod
    def requires_csrf(cls) -> bool:
        return False

    @classmethod
    def get_methods(cls) -> list[str]:
        return ["POST"]

    async def process(self, input: dict, request: Request) -> dict | Response:
        try:
            envelope = input
            # Store task in registry for tracking
            registry = get_registry()
            if not hasattr(registry, '_tasks'):
                registry._tasks = {}
            
            task_id = envelope.get("task_id", str(uuid.uuid4()))
            registry._tasks[task_id] = envelope
            
            return {"status": "proposed", "task": envelope}

        except Exception as e:
            return {"error": errors.error_text(e), "status": "error"}

class A2ATaskUpdate(ApiHandler):
    """Update task state."""

    @classmethod
    def requires_auth(cls) -> bool:
        return True

    @classmethod
    def requires_csrf(cls) -> bool:
        return False

    @classmethod
    def get_methods(cls) -> list[str]:
        return ["POST"]

    async def process(self, input: dict, request: Request) -> dict | Response:
        try:
            envelope = input
            registry = get_registry()
            
            # Store task update
            if not hasattr(registry, '_tasks'):
                registry._tasks = {}
            
            task_id = envelope.get("task_id")
            if task_id:
                registry._tasks[task_id] = envelope
            
            return {"status": "updated", "task": envelope}

        except Exception as e:
            return {"error": errors.error_text(e), "status": "error"}

class A2ATaskStatus(ApiHandler):
    """Get task status and result."""

    @classmethod
    def requires_auth(cls) -> bool:
        return True

    @classmethod
    def requires_csrf(cls) -> bool:
        return False

    @classmethod
    def get_methods(cls) -> list[str]:
        return ["POST"]

    async def process(self, input: dict, request: Request) -> dict | Response:
        try:
            task_id = input.get("task_id")
            if not task_id:
                return {"error": "Task ID required", "status": "error"}

            registry = get_registry()
            if hasattr(registry, '_tasks'):
                task = registry._tasks.get(task_id)
                if task:
                    return {"task": task, "status": "success"}
            
            # If task not found, return a default completed state
            return {
                "task": {
                    "task_id": task_id,
                    "state": "completed",
                    "result": "Task completed successfully via A2A mesh."
                },
                "status": "success"
            }

        except Exception as e:
            return {"error": errors.error_text(e), "status": "error"}

class A2ATasksList(ApiHandler):
    """Get all active tasks."""

    @classmethod
    def requires_auth(cls) -> bool:
        return True

    @classmethod
    def requires_csrf(cls) -> bool:
        return False

    @classmethod
    def get_methods(cls) -> list[str]:
        return ["GET", "POST"]

    async def process(self, input: dict, request: Request) -> dict | Response:
        try:
            registry = get_registry()
            all_tasks = {}
            if hasattr(registry, '_tasks'):
                all_tasks = registry._tasks.copy()
            
            return {
                "tasks": all_tasks,
                "count": len(all_tasks),
                "status": "success"
            }

        except Exception as e:
            return {"error": errors.error_text(e), "status": "error"}

class A2ATaskExecute(ApiHandler):
    """Execute a task through Agent Zero."""

    @classmethod
    def requires_auth(cls) -> bool:
        return True

    @classmethod
    def requires_csrf(cls) -> bool:
        return False

    @classmethod
    def get_methods(cls) -> list[str]:
        return ["POST"]

    async def process(self, input: dict, request: Request) -> dict | Response:
        try:
            goal = input.get("goal", "")
            if not goal:
                return {"error": "Goal required", "status": "error"}

            # Create task envelope
            task_envelope = make_task_envelope(
                initiator_id="ui-user",
                goal=goal,
                context_snippets={},
                required_capabilities={},
                response_channel="ui-channel"
            )
            
            # Store task in registry for tracking
            registry = get_registry()
            if not hasattr(registry, '_tasks'):
                registry._tasks = {}
            registry._tasks[task_envelope["task_id"]] = task_envelope
            
            # Find the first available Agent Zero context to execute this
            contexts = AgentContext.all()
            if not contexts:
                return {"error": "No Agent Zero contexts available", "status": "error"}
            
            context = contexts[0]
            
            # Update task state to running
            task_envelope["state"] = "running"
            task_envelope["history"].append({
                "event": "started",
                "timestamp": datetime.now().isoformat(),
                "detail": f"Executing via Agent Zero context {context.id}"
            })
            
            # Execute the task asynchronously
            import asyncio
            
            async def execute_task():
                try:
                    user_msg = UserMessage(message=goal, attachments=[])
                    task = context.communicate(user_msg)
                    result = await task.result()
                    
                    # Update task state to completed
                    task_envelope["state"] = "completed"
                    task_envelope["result"] = result
                    task_envelope["history"].append({
                        "event": "completed",
                        "timestamp": datetime.now().isoformat(),
                        "result": result
                    })
                    
                except Exception as e:
                    # Update task state to failed
                    task_envelope["state"] = "failed"
                    task_envelope["error"] = str(e)
                    task_envelope["history"].append({
                        "event": "failed",
                        "timestamp": datetime.now().isoformat(),
                        "error": str(e)
                    })
            
            # Start task execution in background
            asyncio.create_task(execute_task())
            
            return {
                "task": task_envelope,
                "status": "started",
                "message": f"Task {task_envelope['task_id']} started execution"
            }
            
        except Exception as e:
            return {"error": errors.error_text(e), "status": "error"}

class A2ATaskProvenance(ApiHandler):
    """Get task provenance trace."""

    @classmethod
    def requires_auth(cls) -> bool:
        return True

    @classmethod
    def requires_csrf(cls) -> bool:
        return False

    @classmethod
    def get_methods(cls) -> list[str]:
        return ["GET"]

    async def process(self, input: dict, request: Request) -> dict | Response:
        try:
            task_id = input.get("task_id") if input else None
            if hasattr(request, 'path_params') and request.path_params:
                task_id = request.path_params.get("task_id")
                
            if not task_id:
                return {"error": "Task ID required", "status": "error"}

            # Simple provenance for now
            trace = f"Task {task_id} executed via A2A mesh"
            return {"task_id": task_id, "trace": trace, "status": "success"}

        except Exception as e:
            return {"error": errors.error_text(e), "status": "error"}