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


class ContextAnswer(Tool):

    async def execute(self, question="", **kwargs):
        if not question:
            return Response(
                message="No question provided. Please specify your question.",
                break_loop=False,
            )

        ContextEngineClient = _load_client()
        config = plugins.get_plugin_config("context-engine", self.agent)
        client = ContextEngineClient(config)
        result = await client.answer(question=question)

        if "error" in result:
            return Response(
                message=f"Context Engine is not available. Ensure services are running.\nError: {result['error']}",
                break_loop=False,
            )

        # Client returns parsed JSON with answer/text fields
        answer = result.get("answer", "") or result.get("text", "")
        if not answer:
            return Response(
                message=f"No answer found for question: {question}",
                break_loop=False,
            )

        return Response(message=answer, break_loop=False)
