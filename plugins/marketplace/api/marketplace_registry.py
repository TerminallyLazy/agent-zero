"""Fetch and cache the plugin registry, merged with local state."""

import time
import httpx
from python.helpers.api import ApiHandler, Input, Output, Request
from python.helpers import plugins, files

REGISTRY_URL = "https://raw.githubusercontent.com/TerminallyLazy/a0-marketplace/main/registry.json"
STATS_URL = "https://a0-marketplace-web.vercel.app/api/stats"
CACHE_TTL = 300  # 5 minutes

_cache = {"data": None, "ts": 0, "stats": {}, "stats_ts": 0}


class MarketplaceRegistry(ApiHandler):
    async def process(self, input: Input, request: Request) -> Output:
        now = time.time()

        # Fetch registry (cached)
        if _cache["data"] is None or (now - _cache["ts"]) > CACHE_TTL:
            try:
                async with httpx.AsyncClient(timeout=15) as client:
                    resp = await client.get(REGISTRY_URL)
                    resp.raise_for_status()
                    _cache["data"] = resp.json()
                    _cache["ts"] = now
            except Exception as e:
                if _cache["data"] is None:
                    return {"ok": False, "error": f"Failed to fetch registry: {str(e)}"}
                # Use stale cache on failure

        # Fetch stats (cached, best-effort)
        if STATS_URL and (now - _cache["stats_ts"]) > CACHE_TTL:
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.get(STATS_URL)
                    if resp.status_code == 200:
                        _cache["stats"] = resp.json().get("counts", {})
                        _cache["stats_ts"] = now
            except:
                pass

        registry = _cache["data"]
        stats = _cache["stats"]
        registry_plugins = registry.get("plugins", [])

        # Get local plugin state
        local_plugins = plugins.get_enhanced_plugins_list(custom=True, builtin=True)
        local_by_name = {p.name: p for p in local_plugins}

        # Build merged list
        merged = []
        seen_ids = set()

        for rp in registry_plugins:
            pid = rp["id"]
            seen_ids.add(pid)
            local = local_by_name.get(pid)

            if local:
                disabled_path = files.get_abs_path(
                    files.USER_DIR, files.PLUGINS_DIR, pid, plugins.DISABLED_FILE_NAME
                )
                is_disabled = files.exists(disabled_path)
                status = "inactive" if is_disabled else "active"
            else:
                status = "available"

            merged.append({
                "id": pid,
                "name": rp.get("name", pid),
                "description": rp.get("description", ""),
                "author": rp.get("author", ""),
                "version": rp.get("version", ""),
                "icon": rp.get("icon", "extension"),
                "tags": rp.get("tags", []),
                "featured": rp.get("featured", False),
                "install_count": stats.get(pid, 0),
                "status": status,
                "is_builtin": local.is_custom is False if local else False,
                "has_config": local.has_config_screen if local else False,
                "repo_url": rp.get("repo_url", ""),
                "branch": rp.get("branch", ""),
                "plugin_path": rp.get("plugin_path", "."),
            })

        # Add local-only plugins (sideloaded, not in registry)
        for lp in local_plugins:
            if lp.name not in seen_ids:
                disabled_path = files.get_abs_path(
                    files.USER_DIR, files.PLUGINS_DIR, lp.name, plugins.DISABLED_FILE_NAME
                )
                is_disabled = files.exists(disabled_path)
                merged.append({
                    "id": lp.name,
                    "name": lp.display_name or lp.name,
                    "description": lp.description,
                    "author": "",
                    "version": lp.version,
                    "icon": "extension",
                    "tags": [],
                    "featured": False,
                    "install_count": 0,
                    "status": "inactive" if is_disabled else "active",
                    "is_builtin": not lp.is_custom,
                    "has_config": lp.has_config_screen,
                    "repo_url": "",
                    "plugin_path": "",
                })

        return {"ok": True, "plugins": merged}
