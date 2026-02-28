from python.helpers.api import ApiHandler, Request, Response

import sys
from pathlib import Path

_plugin_root = Path(__file__).parent.parent
if str(_plugin_root) not in sys.path:
    sys.path.insert(0, str(_plugin_root))
from helpers.client import ContextEngineClient

from python.helpers import plugins


class StatusHandler(ApiHandler):
    """Connection and index status handler for Context Engine dashboard."""

    async def process(self, input: dict, request: Request) -> dict | Response:
        try:
            config = plugins.get_plugin_config("context-engine")
            client = ContextEngineClient(config)

            result = await client.status()

            if isinstance(result, dict) and result.get("ok") is False:
                return {
                    "ok": False,
                    "connected": False,
                    "error": result.get("error", "Status check failed"),
                }

            return {
                "ok": True,
                "connected": True,
                "collection": config.get("collection_name", "codebase"),
                "indexer_endpoint": config.get("indexer_endpoint", "http://localhost:8003"),
                "memory_endpoint": config.get("memory_endpoint", "http://localhost:8002"),
                "status": result,
            }
        except Exception as e:
            return {
                "ok": False,
                "connected": False,
                "error": str(e),
            }
