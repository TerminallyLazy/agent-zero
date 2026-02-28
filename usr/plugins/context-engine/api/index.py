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
            # "path" is a subdirectory relative to /work inside the container.
            # Empty or "/" means index the full workspace.
            subdir = input.get("path", "").strip().strip("/")
            collection = input.get("collection") or None
            recreate = bool(input.get("recreate", False))

            config = plugins.get_plugin_config("context-engine")
            client = ContextEngineClient(config)

            result = await client.index(
                subdir=subdir,
                collection=collection,
                recreate=recreate,
            )

            if isinstance(result, dict) and result.get("ok") is False:
                return {"ok": False, "error": result.get("error", "Indexing failed")}

            target = subdir or "workspace root"
            return {
                "ok": True,
                "message": f"Indexing started for: {target}",
                "result": result,
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}
