"""
API handler for EdgeQuake query execution.

Actions:
- execute: Run a knowledge graph query with specified mode
"""

from flask import Request
from python.helpers.api import ApiHandler, Input, Output

VALID_MODES = ("naive", "local", "global", "hybrid", "mix", "bypass")


class EdgequakeQuery(ApiHandler):

    async def process(self, input: Input, request: Request) -> Output:
        action = input.get("action", "execute")

        if action == "execute":
            return self._execute(input)
        else:
            return {"error": f"Unknown action: {action}"}

    def _execute(self, input: dict) -> dict:
        from plugins.edgequake.helpers.edgequake_client import api_request

        query = str(input.get("query", "")).strip()
        if not query:
            return {"error": "query is required"}

        mode = str(input.get("mode", "hybrid")).strip().lower()
        if mode not in VALID_MODES:
            mode = "hybrid"

        result = api_request("POST", "/api/v1/query", {"query": query, "mode": mode})
        if "error" in result:
            return result

        return {
            "answer": result.get("response", result.get("answer", "")),
            "mode": mode,
            "sources": [
                {
                    "title": src.get("title", ""),
                    "content": src.get("content", str(src))[:500],
                }
                for src in result.get("sources", [])
            ],
        }
