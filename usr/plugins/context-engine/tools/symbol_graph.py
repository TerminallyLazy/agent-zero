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


class SymbolGraph(Tool):

    async def execute(self, symbol="", query_type="callers", **kwargs):
        if not symbol:
            return Response(
                message="No symbol provided. Please specify a function, class, or variable name.",
                break_loop=False,
            )

        ContextEngineClient = _load_client()
        config = plugins.get_plugin_config("context-engine", self.agent)
        client = ContextEngineClient(config)
        result = await client.symbol_graph(symbol=symbol, query_type=query_type)

        if "error" in result:
            return Response(
                message=f"Context Engine is not available. Ensure services are running.\nError: {result['error']}",
                break_loop=False,
            )

        return Response(message=self._format_graph(result, symbol), break_loop=False)

    def _format_graph(self, result: dict, symbol: str) -> str:
        # Client returns parsed JSON; look for results list or text
        results = result.get("results", [])
        if results:
            lines = []
            for item in results:
                path = item.get("path", "")
                sym = item.get("symbol", "")
                start = item.get("start_line", "")
                snippet = item.get("snippet", "")
                header = f"**{path}**" + (f":{start}" if start else "") + (f" ({sym})" if sym else "")
                lines.append(header)
                if snippet:
                    lines.append(snippet)
                lines.append("")
            return f"Symbol graph for '{symbol}':\n\n" + "\n".join(lines)

        text = result.get("text", "")
        if text:
            return f"Symbol graph for '{symbol}':\n\n{text}"

        return f"No symbol graph data found for: {symbol}"
