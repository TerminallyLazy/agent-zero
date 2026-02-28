from python.helpers.api import ApiHandler, Request, Response

import sys
from pathlib import Path

_plugin_root = Path(__file__).parent.parent
if str(_plugin_root) not in sys.path:
    sys.path.insert(0, str(_plugin_root))
from helpers.client import ContextEngineClient

from python.helpers import plugins


class IndexHandler(ApiHandler):
    """Trigger codebase indexing from the Context Engine dashboard."""

    async def process(self, input: dict, request: Request) -> dict | Response:
        try:
            root_path = input.get("path", "").strip()
            if not root_path:
                return {"ok": False, "error": "Path is required"}

            collection = input.get("collection") or None

            config = plugins.get_plugin_config("context-engine")
            client = ContextEngineClient(config)

            result = await client.index(path=root_path, collection=collection)

            if isinstance(result, dict) and result.get("ok") is False:
                return {"ok": False, "error": result.get("error", "Indexing failed")}

            return {
                "ok": True,
                "message": f"Indexing started for: {root_path}",
                "result": result,
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}
