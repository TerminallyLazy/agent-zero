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


class SearchTests(Tool):

    async def execute(self, symbol="", **kwargs):
        try:
            ContextEngineClient = _load_client()
            config = plugins.get_plugin_config("context-engine", self.agent)
            client = ContextEngineClient(config)

            result = await client.search_tests(query=symbol)

            if "error" in result:
                return Response(
                    message=f"Context Engine is not available. Ensure services are running.\nError: {result['error']}",
                    break_loop=False,
                )

            results = result.get("results", [])
            if not results:
                return Response(
                    message=f"No tests found for symbol: {symbol}",
                    break_loop=False,
                )

            lines = [f"Found {len(results)} test(s) for '{symbol}':\n"]
            for i, item in enumerate(results, 1):
                path = item.get("path", "unknown")
                snippet = item.get("snippet", "")
                start = item.get("start_line", "")
                loc = f":{start}" if start else ""
                lines.append(f"{i}. {path}{loc}")
                if snippet:
                    lines.append(f"   {snippet[:200]}\n")

            return Response(message="\n".join(lines), break_loop=False)

        except Exception as e:
            return Response(
                message=f"Context Engine is not available. Ensure services are running. Error: {e}",
                break_loop=False,
            )
