from python.helpers.api import ApiHandler, Request, Response

import sys
from pathlib import Path

_plugin_root = Path(__file__).parent.parent
if str(_plugin_root) not in sys.path:
    sys.path.insert(0, str(_plugin_root))
from helpers.client import ContextEngineClient

from python.helpers import plugins


class SearchHandler(ApiHandler):
    """Code search API handler for the Context Engine WebUI dashboard."""

    async def process(self, input: dict, request: Request) -> dict | Response:
        try:
            query = input.get("query", "").strip()
            if not query:
                return {"ok": False, "error": "Query is required", "results": []}

            limit = input.get("limit", 10)
            language = input.get("language") or None
            path_filter = input.get("path_filter") or None

            config = plugins.get_plugin_config("context-engine")
            client = ContextEngineClient(config)

            result = await client.search(
                query=query,
                limit=limit,
                language=language,
                under=path_filter,
            )

            if isinstance(result, dict) and result.get("ok") is False:
                return {"ok": False, "error": result.get("error", "Search failed"), "results": []}

            results = result.get("results", []) if isinstance(result, dict) else []
            return {
                "ok": True,
                "results": results,
                "total": len(results),
                "query": query,
            }
        except Exception as e:
            return {"ok": False, "error": str(e), "results": []}
