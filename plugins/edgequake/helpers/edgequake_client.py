"""
EdgeQuake SDK client factory.

Reads plugin settings from a JSON file, constructs a cached EdgeQuake client,
and provides a connection test helper.
"""

import hashlib
import json
import os
from typing import Any

from python.helpers.files import get_abs_path
from python.helpers.print_style import PrintStyle

# Settings file path (plugin-owned, not in core settings)
SETTINGS_FILE = get_abs_path("plugins/edgequake/settings.json")

# Default settings
DEFAULTS: dict[str, Any] = {
    "base_url": "http://localhost:8080",
    "api_key": "",
    "workspace_id": "",
    "tenant_id": "",
    "timeout": 30,
}

# Cached client state
_cached_client = None
_cached_hash = ""


def _settings_hash(settings: dict) -> str:
    """Compute a hash of settings values for cache invalidation."""
    raw = json.dumps(settings, sort_keys=True)
    return hashlib.md5(raw.encode()).hexdigest()


def get_edgequake_settings() -> dict[str, Any]:
    """Read EdgeQuake settings from the plugin settings file."""
    settings = dict(DEFAULTS)
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f:
                stored = json.load(f)
            settings.update(stored)
        except Exception as e:
            PrintStyle.error(f"EdgeQuake: failed to read settings: {e}")
    return settings


def save_edgequake_settings(settings: dict[str, Any]) -> None:
    """Write EdgeQuake settings to the plugin settings file."""
    global _cached_client, _cached_hash
    os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f, indent=2)
    # Invalidate cache so next get_edgequake_client() rebuilds
    _cached_client = None
    _cached_hash = ""


def get_edgequake_client():
    """
    Get a cached EdgeQuake SDK client.

    Returns None if:
    - api_key is not configured
    - edgequake-sdk is not installed
    """
    global _cached_client, _cached_hash

    try:
        from edgequake import EdgeQuake
    except ImportError:
        return None

    settings = get_edgequake_settings()
    api_key = settings.get("api_key", "").strip()
    if not api_key:
        return None

    current_hash = _settings_hash(settings)
    if _cached_client is not None and current_hash == _cached_hash:
        return _cached_client

    kwargs: dict[str, Any] = {
        "base_url": settings.get("base_url", DEFAULTS["base_url"]),
        "api_key": api_key,
        "timeout": int(settings.get("timeout", DEFAULTS["timeout"])),
    }
    workspace_id = settings.get("workspace_id", "").strip()
    if workspace_id:
        kwargs["workspace_id"] = workspace_id
    tenant_id = settings.get("tenant_id", "").strip()
    if tenant_id:
        kwargs["tenant_id"] = tenant_id

    _cached_client = EdgeQuake(**kwargs)
    _cached_hash = current_hash
    return _cached_client


def test_connection(settings: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Test connection to EdgeQuake server.

    If settings are provided, creates a temporary client from those values
    (for testing before saving). Otherwise uses the cached client.

    Returns a dict with status info or an error message.
    """
    try:
        from edgequake import EdgeQuake
    except ImportError:
        return {"error": "edgequake-sdk is not installed. Run: pip install edgequake-sdk"}

    if settings is not None:
        api_key = settings.get("api_key", "").strip()
        if not api_key:
            return {"error": "API key is required"}
        kwargs: dict[str, Any] = {
            "base_url": settings.get("base_url", DEFAULTS["base_url"]),
            "api_key": api_key,
            "timeout": int(settings.get("timeout", DEFAULTS["timeout"])),
        }
        workspace_id = settings.get("workspace_id", "").strip()
        if workspace_id:
            kwargs["workspace_id"] = workspace_id
        tenant_id = settings.get("tenant_id", "").strip()
        if tenant_id:
            kwargs["tenant_id"] = tenant_id
        client = EdgeQuake(**kwargs)
    else:
        client = get_edgequake_client()
        if client is None:
            return {"error": "EdgeQuake is not configured"}

    try:
        health = client.health()
        return {
            "status": getattr(health, "status", "unknown"),
            "version": getattr(health, "version", "unknown"),
            "storage_mode": getattr(health, "storage_mode", "unknown"),
            "llm_provider_name": getattr(health, "llm_provider_name", "unknown"),
        }
    except Exception as e:
        return {"error": f"Connection failed: {str(e)}"}
