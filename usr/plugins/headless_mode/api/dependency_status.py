"""Dependency status API handler — checks Python, imports, env, MCP."""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from helpers import plugins
from helpers.api import ApiHandler, Request

_PLUGIN = "headless_mode"
_ROOT_DIR = Path(__file__).resolve().parents[4]
_ENV_KEYS = ["API_KEY_OPENAI", "API_KEY_ANTHROPIC", "API_KEY_GOOGLE"]


class DependencyStatus(ApiHandler):
    async def process(self, input: dict, request: Request) -> dict:
        results = [
            _check_python(),
            _check_framework_imports(),
            _check_environment(),
            _check_mcp(),
        ]
        overall_ok = all(r["ok"] for r in results)
        timestamp = datetime.now(timezone.utc).isoformat()

        payload = {"ok": overall_ok, "timestamp": timestamp, "results": results}
        cfg = plugins.get_plugin_config(_PLUGIN) or {}
        cfg["last_dependency_check"] = payload
        plugins.save_plugin_config(_PLUGIN, "", "", cfg)
        return payload


def _check_python() -> dict:
    return {
        "name": "Python",
        "ok": True,
        "detail": f"{sys.executable} {sys.version.split()[0]}",
    }


def _check_framework_imports() -> dict:
    modules = ["initialize", "helpers.persist_chat", "agent"]
    missing = []
    for mod in modules:
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)
    if missing:
        return {
            "name": "Framework Imports",
            "ok": False,
            "detail": f"missing: {', '.join(missing)}",
        }
    return {
        "name": "Framework Imports",
        "ok": True,
        "detail": f"all {len(modules)} modules importable",
    }


def _check_environment() -> dict:
    env_path = _ROOT_DIR / ".env"
    if not env_path.exists():
        env_path = _ROOT_DIR / "usr" / ".env"
    env_exists = env_path.exists()
    present = [k for k in _ENV_KEYS if os.environ.get(k)]
    detail = f".env {'loaded' if env_exists else 'not found'}, {len(present)}/{len(_ENV_KEYS)} keys present"
    return {
        "name": "Environment",
        "ok": env_exists,
        "detail": detail,
    }


def _check_mcp() -> dict:
    try:
        from helpers import settings as settings_helper
        s = settings_helper.get_settings()
        mcp_raw = s.get("mcp_servers", "")
        import json as _json
        servers = _json.loads(mcp_raw) if mcp_raw else {}
        count = len(servers)
        return {
            "name": "MCP Servers",
            "ok": True,
            "detail": f"{count} server{'s' if count != 1 else ''} configured",
        }
    except Exception as e:
        return {
            "name": "MCP Servers",
            "ok": False,
            "detail": f"could not read MCP config: {e}",
        }
