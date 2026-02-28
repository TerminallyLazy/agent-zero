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


class CEMemoryStore(Tool):

    async def execute(self, content="", tags="", **kwargs):
        try:
            ContextEngineClient = _load_client()
            config = plugins.get_plugin_config("context-engine", self.agent)
            client = ContextEngineClient(config)

            metadata = {}
            if tags:
                metadata["tags"] = [t.strip() for t in tags.split(",") if t.strip()]

            result = await client.memory_store(information=content, metadata=metadata if metadata else None)

            if "error" in result:
                return Response(
                    message=f"Context Engine is not available. Ensure services are running.\nError: {result['error']}",
                    break_loop=False,
                )

            mem_id = result.get("id", "unknown")
            return Response(
                message=f"Memory stored successfully (id: {mem_id}).",
                break_loop=False,
            )
        except Exception as e:
            return Response(
                message=f"Context Engine is not available. Ensure services are running. Error: {e}",
                break_loop=False,
            )
