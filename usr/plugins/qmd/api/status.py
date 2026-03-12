# usr/plugins/qmd/api/status.py
"""GET /api/plugins/qmd/status — bridge state for the config UI."""
from __future__ import annotations

from helpers.api import ApiHandler, Input, Output, Request


class Status(ApiHandler):

    @classmethod
    def get_methods(cls) -> list[str]:
        return ["GET"]

    @classmethod
    def requires_csrf(cls) -> bool:
        return False  # Read-only status endpoint; no state mutation

    async def process(self, input: Input, request: Request) -> Output:
        ctxid = request.args.get("ctxid", "") or input.get("ctxid", "")
        context = self.use_context(ctxid) if ctxid else None
        agent = context.streaming_agent if context else None

        running = False
        pid = None
        collections = []

        if agent:
            client = agent.get_data("qmd_client")
            if client:
                running = client.is_running()
                if running and hasattr(client, "_proc") and client._proc:
                    pid = client._proc.pid
                try:
                    result = await client.call("collection_list")
                    collections = result.get("collections", [])
                except Exception:
                    pass

        return {
            "running": running,
            "pid": pid,
            "collections": [
                {"name": c.get("name", ""), "doc_count": c.get("doc_count", 0)}
                for c in collections
            ],
        }
