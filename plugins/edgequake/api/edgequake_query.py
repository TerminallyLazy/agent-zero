"""
API handler for EdgeQuake query execution.

Actions:
- execute: Run a knowledge graph query with specified mode
"""

import asyncio

from flask import Request
from python.helpers.api import ApiHandler, Input, Output

VALID_MODES = ("naive", "local", "global", "hybrid", "mix", "bypass")


class EdgequakeQuery(ApiHandler):

    async def process(self, input: Input, request: Request) -> Output:
        action = input.get("action", "execute")

        if action == "execute":
            return await self._execute(input)
        else:
            return {"error": f"Unknown action: {action}"}

    def _get_client(self):
        from plugins.edgequake.helpers.edgequake_client import get_edgequake_client
        return get_edgequake_client()

    async def _execute(self, input: dict) -> dict:
        client = self._get_client()
        if client is None:
            return {"error": "EdgeQuake is not configured"}

        query = str(input.get("query", "")).strip()
        if not query:
            return {"error": "query is required"}

        mode = str(input.get("mode", "hybrid")).strip().lower()
        if mode not in VALID_MODES:
            mode = "hybrid"

        try:
            result = await asyncio.to_thread(client.query.execute, query=query, mode=mode)
            answer = getattr(result, "answer", str(result))
            sources = getattr(result, "sources", [])

            formatted_sources = []
            for src in (sources or []):
                formatted_sources.append({
                    "title": getattr(src, "title", ""),
                    "content": getattr(src, "content", str(src))[:500],
                })

            return {
                "answer": answer,
                "mode": mode,
                "sources": formatted_sources,
            }
        except Exception as e:
            return {"error": f"Query failed: {str(e)}"}
