"""
Opik initialization helper for Agent Zero
"""

import os
from typing import Optional
from python.helpers.opik_config import OpikConfig
from python.helpers.opik_client import OpikTracker, initialize_opik, get_opik_tracker
from python.helpers.print_style import PrintStyle

def initialize_opik_integration(config: Optional[OpikConfig] = None) -> Optional[OpikTracker]:
    """
    Initialize Opik integration for Agent Zero with sensible defaults

    Args:
        config: Optional OpikConfig. If None, loads from environment

    Returns:
        OpikTracker instance if successful, None otherwise
    """

    # Check if already initialized
    existing_tracker = get_opik_tracker()
    if existing_tracker and existing_tracker.is_enabled():
        PrintStyle(font_color="green").print("Opik integration already active")
        return existing_tracker

    try:
        # Load configuration from environment or use provided config
        config = config or OpikConfig.from_env()

        # Override with local defaults if not explicitly configured
        if not os.getenv('OPIK_ENDPOINT') and not os.getenv('OPIK_URL_OVERRIDE'):
            config.endpoint = "http://localhost:5173"
            config.use_local = True

        if not os.getenv('OPIK_PROJECT_NAME'):
            config.project_name = "agent-zero-traces"

        # Enable tracing by default
        if not os.getenv('OPIK_ENABLED'):
            config.enabled = True

        if not os.getenv('OPIK_TRACE_TOOLS'):
            config.trace_tools = True

        # Set default tags
        if not config.tags:
            config.tags = ["agent-zero", "local-deployment"]

        # Initialize tracker
        tracker = initialize_opik(config)

        if tracker and tracker.is_enabled():
            PrintStyle(font_color="green", bold=True).print("✓ Opik integration initialized successfully")
            PrintStyle(font_color="cyan").print(f"  Project: {config.project_name}")
            PrintStyle(font_color="cyan").print(f"  Endpoint: {config.endpoint}")
            PrintStyle(font_color="cyan").print(f"  Tools Tracing: {'ON' if config.trace_tools else 'OFF'}")
            PrintStyle(font_color="cyan").print(f"  Dashboard: http://localhost:5173")

            return tracker
        else:
            PrintStyle(font_color="yellow").print("⚠ Opik integration disabled or unavailable")
            return None

    except Exception as e:
        PrintStyle(font_color="red").print(f"✗ Failed to initialize Opik integration: {e}")
        return None

def configure_opik_for_agent_zero():
    """
    Configure Opik with Agent Zero specific settings
    """

    # Set environment variables for optimal Agent Zero integration
    os.environ.setdefault('OPIK_PROJECT_NAME', 'agent-zero-traces')
    os.environ.setdefault('OPIK_ENABLED', 'true')
    os.environ.setdefault('OPIK_USE_LOCAL', 'true')
    os.environ.setdefault('OPIK_ENDPOINT', 'http://localhost:5173')
    os.environ.setdefault('OPIK_TRACE_TOOLS', 'true')
    os.environ.setdefault('OPIK_TRACE_LLM', 'true')

    # Initialize with configured settings
    return initialize_opik_integration()

def get_opik_dashboard_url() -> str:
    """Get the Opik dashboard URL"""
    config = OpikConfig.from_env()
    endpoint = config.endpoint or "http://localhost:5173"
    return endpoint

def print_opik_status():
    """Print current Opik integration status"""
    tracker = get_opik_tracker()

    if tracker and tracker.is_enabled():
        config = tracker.config
        PrintStyle(font_color="green").print(
            f"✅ Opik Status: ACTIVE\n"
            f"   Project: {config.project_name}\n"
            f"   Endpoint: {config.endpoint}\n"
            f"   Tools Tracing: {'ON' if config.trace_tools else 'OFF'}\n"
            f"   Dashboard: {get_opik_dashboard_url()}"
        )
    else:
        PrintStyle(font_color="red").print(
            f"❌ Opik Status: INACTIVE\n"
            f"   To activate: pip install opik && set OPIK_ENABLED=true\n"
            f"   Expected Dashboard: {get_opik_dashboard_url()}"
        )