"""Context Engine plugin helpers.

Provides get_client() for tools and extensions that need the
ContextEngineClient. Handles the hyphenated directory name import
issue by using importlib with a file path.
"""

from __future__ import annotations

import importlib.util
import os
from typing import TYPE_CHECKING

from python.helpers import plugins

if TYPE_CHECKING:
    from agent import Agent
    from .client import ContextEngineClient


def _load_client_module():
    """Import client.py via file path (bypasses hyphen in dir name)."""
    client_path = os.path.join(os.path.dirname(__file__), "client.py")
    spec = importlib.util.spec_from_file_location(
        "context_engine_client", client_path
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load Context Engine client from {client_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def get_client(agent: Agent) -> ContextEngineClient:
    """Build a ContextEngineClient from the plugin's current config."""
    config = plugins.get_plugin_config("context-engine", agent) or {}
    module = _load_client_module()
    return module.ContextEngineClient(config)
