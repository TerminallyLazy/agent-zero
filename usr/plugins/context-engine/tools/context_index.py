import importlib.util
import os

from python.helpers.tool import Tool, Response
from python.helpers import plugins


def _load_client():
    client_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "helpers", "client.py")
    spec = importlib.util.spec_from_file_location("context_engine_client", client_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.ContextEngineClient


class ContextIndex(Tool):

    async def execute(self, path="", **kwargs):
        if not path:
            return Response(
                message="No path provided. Please specify a directory to index.",
                break_loop=False,
            )

        ContextEngineClient = _load_client()
        config = plugins.get_plugin_config("context-engine", self.agent)
        client = ContextEngineClient(config)
        result = await client.index(path=path)

        if "error" in result:
            return Response(
                message=f"Context Engine is not available. Ensure services are running.\nError: {result['error']}",
                break_loop=False,
            )

        text = result.get("text", "") or result.get("message", "")
        if not text:
            text = f"Indexing started for: {path}"

        return Response(message=text, break_loop=False)
