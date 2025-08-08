from datetime import timedelta
import asyncio
import os
import secrets
import time
import socket
import struct
from functools import wraps
import threading
from flask import Flask, request, Response, session
from flask_basicauth import BasicAuth
import importlib
from python.helpers import files, mcp_server
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

# Set up basic authentication for UI and API (simplified)
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
            return Response("Forbidden", 403)
        return await f(*args, **kwargs)

    return decorated


# Load API handlers from python/api folder
api_classes = load_classes_from_folder(get_abs_path("python/api"), "*", ApiHandler)
api_handlers: dict[str, ApiHandler] = {}

for api_class in api_classes:
    route_name = api_class.__module__.split(".")[-1]
    api_handler = api_class(webapp, lock)
    api_handlers[route_name] = api_handler

    # Create route
    route_path = f"/api/{route_name}"
    
    endpoint_func = lambda handler=api_handler: asyncio.run(handler.handle_request(request))
    endpoint_func.__name__ = f"api_{route_name}"
    
    # Apply decorators based on handler requirements
    if api_handler.requires_api_key():
        endpoint_func = requires_api_key(endpoint_func)
    
    if api_handler.requires_loopback():
        endpoint_func = requires_loopback(endpoint_func)
    
    if api_handler.requires_auth():
        endpoint_func = basic_auth.required(endpoint_func)
    
    webapp.add_url_rule(
        route_path,
        endpoint_func.__name__,
        endpoint_func,
        methods=api_handler.get_methods()
    )


# Serve the main page
@webapp.route("/")
def index():
    return webapp.send_static_file("index.html")


def main():
    PrintStyle(font_color="green", bold=True).print("Starting Agent Zero Lite...")
    
    # Initialize the agent
    try:
        # Import lazily to avoid module resolution edge cases in certain installers
        init_mod = importlib.import_module("initialize")
        agent_config = init_mod.initialize_agent()  # type: ignore[attr-defined]
        PrintStyle(font_color="green").print("Agent Zero Lite initialized successfully")
    except Exception as e:
        PrintStyle(font_color="red").print(f"Failed to initialize Agent Zero Lite: {e}")
        return
    
    # Start the web server
    host = "127.0.0.1"
    port = int(os.getenv("PORT", 50001))
    
    PrintStyle(font_color="cyan", bold=True).print(f"Web UI available at: http://{host}:{port}")
    PrintStyle(font_color="yellow").print("Press Ctrl+C to stop")
    
    try:
        webapp.run(
            host=host,
            port=port,
            debug=False,
            threaded=True,
            use_reloader=False
        )
    except KeyboardInterrupt:
        PrintStyle(font_color="yellow").print("\nShutting down Agent Zero Lite...")
    except Exception as e:
        PrintStyle(font_color="red").print(f"Server error: {e}")


if __name__ == "__main__":
    main()