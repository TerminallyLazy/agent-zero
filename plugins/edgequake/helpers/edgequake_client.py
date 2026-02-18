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
    "base_url": "http://host.docker.internal:8080",
    "api_key": "",
    "workspace_id": "",
    "tenant_id": "",
    "timeout": 30,
    # Phase 3: Pipeline settings
    "auto_index": False,
    "index_batch_size": 5,
    "auto_recall": False,
    "recall_timeout": 3,
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


def _make_headers(api_key: str, workspace_id: str = "", tenant_id: str = "") -> dict[str, str]:
    """Build HTTP headers for EdgeQuake API requests."""
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    if workspace_id:
        headers["X-Workspace-Id"] = workspace_id
    if tenant_id:
        headers["X-Tenant-Id"] = tenant_id
    return headers


def api_request(
    method: str,
    path: str,
    body: dict | None = None,
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Make an HTTP request to the EdgeQuake REST API.

    Works without the edgequake SDK — uses raw HTTP via requests.
    Returns the parsed JSON response or a dict with an 'error' key.
    """
    import requests as req

    s = settings or get_edgequake_settings()
    base_url = s.get("base_url", DEFAULTS["base_url"]).rstrip("/")
    api_key = s.get("api_key", "").strip()
    timeout = int(s.get("timeout", DEFAULTS["timeout"]))

    if not api_key:
        return {"error": "EdgeQuake API key is not configured. Open EdgeQuake settings to set one."}

    headers = _make_headers(api_key, s.get("workspace_id", ""), s.get("tenant_id", ""))
    url = f"{base_url}{path}"

    try:
        if method.upper() == "GET":
            resp = req.get(url, headers=headers, timeout=timeout)
        elif method.upper() == "POST":
            resp = req.post(url, json=body, headers=headers, timeout=timeout)
        elif method.upper() == "DELETE":
            resp = req.delete(url, headers=headers, timeout=timeout)
        else:
            resp = req.request(method.upper(), url, json=body, headers=headers, timeout=timeout)

        if resp.status_code == 401:
            return {"error": "Authentication failed (401). Check your API key."}
        if resp.status_code == 403:
            return {"error": "Access forbidden (403). Check your API key."}
        if resp.status_code == 404:
            return {"error": f"Endpoint not found: {path}"}

        # Try to parse JSON; EdgeQuake returns JSON for everything
        try:
            data = resp.json()
        except Exception:
            if resp.status_code >= 400:
                return {"error": f"HTTP {resp.status_code}: {resp.text[:200]}"}
            return {"error": f"Unexpected non-JSON response from {path}"}

        # EdgeQuake error responses have a "code" and "message" field
        if resp.status_code >= 400 and "message" in data:
            return {"error": data["message"]}

        return data
    except req.ConnectionError:
        return {"error": f"Cannot connect to {base_url}. Is the EdgeQuake server running?"}
    except req.Timeout:
        return {"error": f"Request timed out after {timeout}s."}
    except Exception as e:
        return {"error": f"Request failed: {str(e)}"}


def _test_connection_http(settings: dict[str, Any]) -> dict[str, Any]:
    """
    Test connection using raw HTTP (no SDK required).

    Sends GET /health with the API key as a Bearer token.
    """
    import requests as req

    base_url = settings.get("base_url", DEFAULTS["base_url"]).rstrip("/")
    api_key = settings.get("api_key", "").strip()
    timeout = int(settings.get("timeout", DEFAULTS["timeout"]))

    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        resp = req.get(f"{base_url}/health", headers=headers, timeout=timeout)
        if resp.status_code == 401:
            return {"error": "Authentication failed (401). Check your API key."}
        if resp.status_code == 403:
            return {"error": "Access forbidden (403). Check your API key."}
        resp.raise_for_status()
        data = resp.json()
        return {
            "status": data.get("status", "unknown"),
            "version": data.get("version", "unknown"),
            "storage_mode": data.get("storage_mode", "unknown"),
            "llm_provider_name": data.get("llm_provider_name", "unknown"),
        }
    except req.ConnectionError:
        return {"error": f"Cannot connect to {base_url}. Is the server running?"}
    except req.Timeout:
        return {"error": f"Connection timed out after {timeout}s."}
    except Exception as e:
        return {"error": f"Connection failed: {str(e)}"}


def test_connection(settings: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Test connection to EdgeQuake server.

    If settings are provided, creates a temporary client from those values
    (for testing before saving). Otherwise uses the cached client.

    Uses the edgequake SDK if installed, otherwise falls back to raw HTTP.
    Returns a dict with status info or an error message.
    """
    resolved_settings = settings if settings else get_edgequake_settings()
    api_key = resolved_settings.get("api_key", "").strip()
    if not api_key:
        return {"error": "API key is required"}

    # Try the SDK first, fall back to raw HTTP
    try:
        from edgequake import EdgeQuake
    except ImportError:
        return _test_connection_http(resolved_settings)

    if settings is not None:
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
