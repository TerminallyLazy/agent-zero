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


class CEMemoryFind(Tool):

    async def execute(self, query="", limit=5, **kwargs):
        try:
            ContextEngineClient = _load_client()
            config = plugins.get_plugin_config("context-engine", self.agent)
            client = ContextEngineClient(config)

            result = await client.memory_find(query=query, limit=int(limit))

            if "error" in result:
                return Response(
                    message=f"Context Engine is not available. Ensure services are running.\nError: {result['error']}",
                    break_loop=False,
                )

            results = result.get("results", [])
            if not results:
                return Response(
                    message=f"No memories found matching: {query}",
                    break_loop=False,
                )

            lines = [f"Found {len(results)} memory result(s) for '{query}':\n"]
            for i, item in enumerate(results, 1):
                content = item.get("information", item.get("content", ""))
                score = item.get("score", 0)
                meta = item.get("metadata", {})
                tags = meta.get("tags", [])
                tag_str = f" [tags: {', '.join(tags)}]" if tags else ""
                lines.append(f"{i}. (score: {score:.2f}){tag_str}\n{content}\n")

            return Response(message="\n".join(lines), break_loop=False)

        except Exception as e:
            return Response(
                message=f"Context Engine is not available. Ensure services are running. Error: {e}",
                break_loop=False,
            )
