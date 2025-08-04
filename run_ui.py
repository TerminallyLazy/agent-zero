from datetime import timedelta
import os
import secrets
import time
import socket
import struct
from functools import wraps
import threading
from flask import Flask, request, Response, session
from flask_basicauth import BasicAuth
import initialize
from python.helpers import files, git, mcp_server, fasta2a_server
from python.helpers.files import get_abs_path
from python.helpers import runtime, dotenv, process
from python.helpers.extract_tools import load_classes_from_folder
from python.helpers.api import ApiHandler
from python.helpers.print_style import PrintStyle


# Set the new timezone to 'UTC'
os.environ["TZ"] = "UTC"
os.environ["TOKENIZERS_PARALLELISM"] = "false"
# Apply the timezone change
if hasattr(time, 'tzset'):
    time.tzset()

# initialize the internal Flask server
webapp = Flask("app", static_folder=get_abs_path("./webui"), static_url_path="/")
webapp.secret_key = os.getenv("FLASK_SECRET_KEY") or secrets.token_hex(32)
webapp.config.update(
    JSON_SORT_KEYS=False,
    SESSION_COOKIE_NAME="session_" + runtime.get_runtime_id(),  # bind the session cookie name to runtime id to prevent session collision on same host
    SESSION_COOKIE_SAMESITE="Strict",
    SESSION_PERMANENT=True,
    PERMANENT_SESSION_LIFETIME=timedelta(days=1)
)


lock = threading.Lock()

# Set up basic authentication for UI and API but not MCP
basic_auth = BasicAuth(webapp)


def is_loopback_address(address):
    loopback_checker = {
        socket.AF_INET: lambda x: struct.unpack("!I", socket.inet_aton(x))[0]
        >> (32 - 8)
        == 127,
        socket.AF_INET6: lambda x: x == "::1",
    }
    address_type = "hostname"
    try:
        socket.inet_pton(socket.AF_INET6, address)
        address_type = "ipv6"
    except socket.error:
        try:
            socket.inet_pton(socket.AF_INET, address)
            address_type = "ipv4"
        except socket.error:
            address_type = "hostname"

    if address_type == "ipv4":
        return loopback_checker[socket.AF_INET](address)
    elif address_type == "ipv6":
        return loopback_checker[socket.AF_INET6](address)
    else:
        for family in (socket.AF_INET, socket.AF_INET6):
            try:
                r = socket.getaddrinfo(address, None, family, socket.SOCK_STREAM)
            except socket.gaierror:
                return False
            for family, _, _, _, sockaddr in r:
                if not loopback_checker[family](sockaddr[0]):
                    return False
        return True


def requires_api_key(f):
    @wraps(f)
    async def decorated(*args, **kwargs):
        valid_api_key = dotenv.get_dotenv_value("API_KEY")
        if api_key := request.headers.get("X-API-KEY"):
            if api_key != valid_api_key:
                return Response("API key required", 401)
        elif request.json and request.json.get("api_key"):
            api_key = request.json.get("api_key")
            if api_key != valid_api_key:
                return Response("API key required", 401)
        else:
            return Response("API key required", 401)
        return await f(*args, **kwargs)

    return decorated


# allow only loopback addresses
def requires_loopback(f):
    @wraps(f)
    async def decorated(*args, **kwargs):
        if not is_loopback_address(request.remote_addr):
            return Response(
                "Access denied.",
                403,
                {},
            )
        return await f(*args, **kwargs)

    return decorated


# require authentication for handlers
def requires_auth(f):
    @wraps(f)
    async def decorated(*args, **kwargs):
        user = dotenv.get_dotenv_value("AUTH_LOGIN")
        password = dotenv.get_dotenv_value("AUTH_PASSWORD")
        if user and password:
            auth = request.authorization
            if not auth or not (auth.username == user and auth.password == password):
                return Response(
                    "Could not verify your access level for that URL.\n"
                    "You have to login with proper credentials",
                    401,
                    {"WWW-Authenticate": 'Basic realm="Login Required"'},
                )
        return await f(*args, **kwargs)

    return decorated


def csrf_protect(f):
    @wraps(f)
    async def decorated(*args, **kwargs):
        token = session.get("csrf_token")
        header = request.headers.get("X-CSRF-Token")
        cookie = request.cookies.get("csrf_token_" + runtime.get_runtime_id())
        sent = header or cookie
        if not token or not sent or token != sent:
            return Response("CSRF token missing or invalid", 403)
        return await f(*args, **kwargs)

    return decorated


# handle default address, load index
@webapp.route("/", methods=["GET"])
@requires_auth
async def serve_index():
    gitinfo = None
    try:
        gitinfo = git.get_git_info()
    except Exception:
        gitinfo = {
            "version": "unknown",
            "commit_time": "unknown",
        }
    index = files.read_file("webui/index.html")
    index = files.replace_placeholders_text(
        _content=index,
        version_no=gitinfo["version"],
        version_time=gitinfo["commit_time"]
    )
    return index

# A2A Mesh API Endpoints
try:
    from python.helpers.registry_broker import AgentRegistry
    from python.helpers.agent_card import AgentCard
    from flask import jsonify
    import uuid
    from datetime import datetime
    
    # Global registry for A2A mesh
    _a2a_registry = None
    
    def get_a2a_registry():
        global _a2a_registry
        if _a2a_registry is None:
            _a2a_registry = AgentRegistry()
        return _a2a_registry
    
    @webapp.route("/a2a_registry_match", methods=["GET", "POST"])
    @requires_auth
    async def a2a_registry_match():
        try:
            registry = get_a2a_registry()
            
            # Light cleanup only
            registry.prune_stale(ttl=300.0)
            
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
                
                return jsonify({
                    "matches": [{"agent_card": default_card.to_dict()}],
                    "goal": "",
                    "status": "success"
                })
            
            # Return all agents for now
            matches = []
            for agent in all_agents:
                matches.append({"agent_card": agent.signed_card.get("agent_card", {})})
                
            return jsonify({
                "matches": matches,
                "goal": "",
                "status": "success"
            })
            
        except Exception as e:
            return jsonify({"error": str(e), "status": "error"})
    
    @webapp.route("/a2a_tasks_list", methods=["GET", "POST"])
    @requires_auth
    async def a2a_tasks_list():
        try:
            registry = get_a2a_registry()
            all_tasks = {}
            if hasattr(registry, '_tasks'):
                all_tasks = registry._tasks.copy()
            
            return jsonify({
                "tasks": all_tasks,
                "count": len(all_tasks),
                "status": "success"
            })
            
        except Exception as e:
            return jsonify({"error": str(e), "status": "error"})
    
    @webapp.route("/a2a_task_execute", methods=["POST"])
    @requires_auth
    async def a2a_task_execute():
        try:
            from python.helpers.async_task_coordinator import get_coordinator
            
            data = request.get_json() if request.is_json else {}
            goal = data.get("goal", "")
            if not goal:
                return jsonify({"error": "Goal required", "status": "error"})
            
            # Use async coordinator for better concurrency
            coordinator = get_coordinator()
            task_id = await coordinator.submit_task(goal)
            
            # Get initial task status
            task_status = await coordinator.get_task_status(task_id)
            
            # Also store in registry for backward compatibility
            registry = get_a2a_registry()
            if not hasattr(registry, '_tasks'):
                registry._tasks = {}
            
            # Convert to legacy format for UI compatibility
            task_envelope = {
                "task_id": task_id,
                "initiator_id": "ui-user",
                "goal": goal,
                "state": "running",
                "created_at": task_status["created_at"],
                "history": [{
                    "event": "created",
                    "timestamp": task_status["created_at"],
                    "detail": "Task submitted via async coordinator"
                }]
            }
            registry._tasks[task_id] = task_envelope
            
            print(f"[A2A] Submitted task {task_id} to async coordinator: {goal[:50]}...")
            
            return jsonify({
                "task": task_envelope,
                "status": "started",
                "message": f"Task {task_id} submitted for async execution"
            })
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return jsonify({"error": str(e), "status": "error"})
    
    @webapp.route("/a2a_task_execute_batch", methods=["POST"])
    @requires_auth
    async def a2a_task_execute_batch():
        """Execute multiple tasks in parallel."""
        try:
            from python.helpers.async_task_coordinator import get_coordinator
            
            data = request.get_json() if request.is_json else {}
            goals = data.get("goals", [])
            if not goals or not isinstance(goals, list):
                return jsonify({"error": "Goals list required", "status": "error"})
            
            # Use async coordinator for parallel execution
            coordinator = get_coordinator()
            task_ids = await coordinator.submit_batch(goals)
            
            # Store in registry for backward compatibility
            registry = get_a2a_registry()
            if not hasattr(registry, '_tasks'):
                registry._tasks = {}
            
            tasks = []
            for i, task_id in enumerate(task_ids):
                task_status = await coordinator.get_task_status(task_id)
                task_envelope = {
                    "task_id": task_id,
                    "initiator_id": "ui-user",
                    "goal": goals[i],
                    "state": "running",
                    "created_at": task_status["created_at"],
                    "history": [{
                        "event": "created",
                        "timestamp": task_status["created_at"],
                        "detail": "Batch task submitted via async coordinator"
                    }]
                }
                registry._tasks[task_id] = task_envelope
                tasks.append(task_envelope)
            
            print(f"[A2A] Submitted {len(task_ids)} tasks for parallel execution")
            
            return jsonify({
                "tasks": tasks,
                "task_ids": task_ids,
                "status": "started",
                "message": f"{len(task_ids)} tasks submitted for parallel execution"
            })
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return jsonify({"error": str(e), "status": "error"})
    
    @webapp.route("/a2a_task_status", methods=["POST"])
    @requires_auth
    async def a2a_task_status():
        """Get updated status for a task."""
        try:
            from python.helpers.async_task_coordinator import get_coordinator
            
            data = request.get_json() if request.is_json else {}
            task_id = data.get("task_id", "")
            if not task_id:
                return jsonify({"error": "Task ID required", "status": "error"})
            
            # Get status from coordinator
            coordinator = get_coordinator()
            task_status = await coordinator.get_task_status(task_id)
            
            if not task_status:
                # Fallback to registry
                registry = get_a2a_registry()
                if hasattr(registry, '_tasks') and task_id in registry._tasks:
                    task = registry._tasks[task_id]
                    return jsonify({"task": task, "status": "success"})
                else:
                    return jsonify({"error": "Task not found", "status": "error"})
            
            # Convert coordinator status to legacy format
            task_envelope = {
                "task_id": task_id,
                "goal": task_status.get("goal", ""),
                "state": task_status["status"],
                "created_at": task_status["created_at"],
                "started_at": task_status.get("started_at"),
                "completed_at": task_status.get("completed_at"),
                "result": task_status.get("result"),
                "error": task_status.get("error"),
                "progress": task_status.get("progress", []),
                "history": [
                    {
                        "event": "created",
                        "timestamp": task_status["created_at"],
                        "detail": "Task created"
                    }
                ]
            }
            
            # Add progress events to history
            for prog in task_status.get("progress", []):
                task_envelope["history"].append({
                    "event": "progress",
                    "timestamp": prog["timestamp"],
                    "detail": prog["message"]
                })
            
            # Update registry
            registry = get_a2a_registry()
            if hasattr(registry, '_tasks'):
                registry._tasks[task_id] = task_envelope
            
            return jsonify({"task": task_envelope, "status": "success"})
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return jsonify({"error": str(e), "status": "error"})
    
    @webapp.route("/a2a_registry_list", methods=["GET", "POST"])
    @requires_auth
    async def a2a_registry_list():
        """Get all registered agents"""
        try:
            registry = get_a2a_registry()
            
            # Light cleanup
            registry.prune_stale(ttl=300.0)
            
            all_agents = registry.list_agents()
            
            # Convert to UI format
            agents_dict = {}
            for agent in all_agents:
                agent_card = agent.signed_card.get("agent_card", {})
                agents_dict[agent.agent_id] = {
                    "card": agent_card,
                    "lastSeen": datetime.fromtimestamp(agent.last_heartbeat).isoformat(),
                    "score": agent.score_cache
                }
            
            # Always include local agent
            if "agent-zero-local" not in agents_dict:
                agents_dict["agent-zero-local"] = {
                    "card": {
                        "agent_id": "agent-zero-local",
                        "role_description": "Agent Zero - Local AI Assistant",
                        "trust_level": "local",
                        "version": "1.0",
                        "tools": ["code_execution", "web_search", "file_management", "data_analysis"]
                    },
                    "lastSeen": datetime.now().isoformat(),
                    "score": {}
                }
            
            return jsonify({
                "agents": agents_dict,
                "count": len(agents_dict),
                "status": "success"
            })
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return jsonify({"error": str(e), "status": "error"})
    
    @webapp.route("/a2a_registry_clear", methods=["POST"])
    @requires_auth
    async def a2a_registry_clear():
        """Clear all agents from the registry"""
        try:
            registry = get_a2a_registry()
            
            # Clear all agents
            if hasattr(registry, '_agents'):
                count = len(registry._agents)
                registry._agents.clear()
                print(f"[A2A] Cleared {count} agents from registry")
            
            # Clear all tasks
            if hasattr(registry, '_tasks'):
                task_count = len(registry._tasks)
                registry._tasks.clear()
                print(f"[A2A] Cleared {task_count} tasks from registry")
            
            return jsonify({
                "status": "success",
                "message": "Registry cleared successfully",
                "agents_cleared": count if 'count' in locals() else 0,
                "tasks_cleared": task_count if 'task_count' in locals() else 0
            })
            
        except Exception as e:
            return jsonify({"error": str(e), "status": "error"})

    @webapp.route("/a2a_registry_debug", methods=["GET"])
    @requires_auth
    async def a2a_registry_debug():
        """Debug endpoint to see registry state"""
        try:
            registry = get_a2a_registry()
            debug_info = {
                "registry_id": id(registry),
                "agent_count": len(registry.list_agents()),
                "agents": []
            }
            
            for agent in registry.list_agents():
                debug_info["agents"].append({
                    "agent_id": agent.agent_id,
                    "last_heartbeat": agent.last_heartbeat,
                    "age_seconds": time.time() - agent.last_heartbeat
                })
            
            return jsonify(debug_info)
            
        except Exception as e:
            return jsonify({"error": str(e), "status": "error"})

    print("[A2A] API endpoints registered successfully")

except Exception as e:
    print(f"[A2A] Failed to register API endpoints: {e}")
    # Continue without A2A endpoints if there's an error


def run():
    PrintStyle().print("Initializing framework...")

    # Suppress only request logs but keep the startup messages
    from werkzeug.serving import WSGIRequestHandler
    from werkzeug.serving import make_server
    from werkzeug.middleware.dispatcher import DispatcherMiddleware
    from a2wsgi import ASGIMiddleware

    PrintStyle().print("Starting server...")

    class NoRequestLoggingWSGIRequestHandler(WSGIRequestHandler):
        def log_request(self, code="-", size="-"):
            pass  # Override to suppress request logging

    # Get configuration from environment
    port = runtime.get_web_ui_port()
    host = (
        runtime.get_arg("host") or dotenv.get_dotenv_value("WEB_UI_HOST") or "localhost"
    )
    server = None

    def register_api_handler(app, handler: type[ApiHandler]):
        name = handler.__module__.split(".")[-1]
        instance = handler(app, lock)

        async def handler_wrap():
            return await instance.handle_request(request=request)

        if handler.requires_loopback():
            handler_wrap = requires_loopback(handler_wrap)
        if handler.requires_auth():
            handler_wrap = requires_auth(handler_wrap)
        if handler.requires_api_key():
            handler_wrap = requires_api_key(handler_wrap)
        if handler.requires_csrf():
            handler_wrap = csrf_protect(handler_wrap)

        app.add_url_rule(
            f"/{name}",
            f"/{name}",
            handler_wrap,
            methods=handler.get_methods(),
        )

    # initialize and register API handlers
    handlers = load_classes_from_folder("python/api", "*.py", ApiHandler)
    for handler in handlers:
        register_api_handler(webapp, handler)

    # add the webapp, mcp, and a2a to the app
    middleware_routes = {
        # "/mcp": ASGIMiddleware(app=mcp_server.DynamicMcpProxy.get_instance()),  # type: ignore - temporarily disabled due to FastMCP API compatibility
        "/a2a": ASGIMiddleware(app=fasta2a_server.DynamicA2AProxy.get_instance()),  # type: ignore
    }

    app = DispatcherMiddleware(webapp, middleware_routes)  # type: ignore

    PrintStyle().debug(f"Starting server at http://{host}:{port} ...")

    server = make_server(
        host=host,
        port=port,
        app=app,
        request_handler=NoRequestLoggingWSGIRequestHandler,
        threaded=True,
    )
    process.set_server(server)
    server.log_startup()

    # Start init_a0 in a background thread when server starts
    # threading.Thread(target=init_a0, daemon=True).start()
    init_a0()

    # run the server
    server.serve_forever()


def init_a0():
    # initialize contexts and MCP
    init_chats = initialize.initialize_chats()
    # only wait for init chats, otherwise they would seem to disappear for a while on restart
    init_chats.result_sync()

    # initialize.initialize_mcp()  # temporarily disabled due to FastMCP API compatibility
    # start job loop
    initialize.initialize_job_loop()
    # preload
    initialize.initialize_preload()



# run the internal server
if __name__ == "__main__":
    runtime.initialize()
    dotenv.load_dotenv()
    run()
