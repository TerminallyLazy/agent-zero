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


class CodeSearch(Tool):

    async def execute(self, query="", limit=10, language="", under="", **kwargs):
        if not query:
            return Response(
                message="No search query provided. Please specify what to search for.",
                break_loop=False,
            )

        ContextEngineClient = _load_client()
        config = plugins.get_plugin_config("context-engine", self.agent)
        client = ContextEngineClient(config)
        result = await client.search(
            query=query,
            limit=int(limit),
            language=language or None,
            under=under or None,
        )

        if "error" in result:
            return Response(
                message=f"Context Engine is not available. Ensure services are running.\nError: {result['error']}",
                break_loop=False,
            )

        return Response(message=self._format_results(result, query), break_loop=False)

    def _format_results(self, result: dict, query: str) -> str:
        # Client now returns parsed JSON; look for results list or text
        results = result.get("results", [])
        if results:
            lines = []
            for item in results:
                path = item.get("path", "")
                snippet = item.get("snippet", "")
                symbol = item.get("symbol", "")
                start = item.get("start_line", "")
                header = f"**{path}**" + (f":{start}" if start else "") + (f" ({symbol})" if symbol else "")
                lines.append(header)
                if snippet:
                    lines.append(snippet)
                lines.append("")
            return f"Code search results for '{query}':\n\n" + "\n".join(lines)

        # Fallback: plain text response from server
        text = result.get("text", "")
        if text:
            return f"Code search results for '{query}':\n\n{text}"

        return f"No code results found for query: {query}"
