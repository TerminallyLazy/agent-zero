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
        context = None
        if ctxid:
            try:
                context = self.use_context(ctxid, create_if_not_exists=False)
            except Exception:
                context = None
        # Use agent0 (the persistent root agent) — streaming_agent is only set
        # while a message is actively processing, so it's None most of the time.
        agent = context.agent0 if context else None

        running = False
        pid = None
        collections = []

        from usr.plugins.qmd.helpers.client_access import get_global_client
        # Prefer the per-agent client; fall back to the global singleton so
        # the config UI (which has no ctxid) can still reflect bridge state.
        client = None
        if agent:
            client = agent.get_data("qmd_client")
        if client is None:
            client = get_global_client()

        if client:
            running = client.is_running()
            if running and hasattr(client, "_proc") and client._proc:
                pid = client._proc.pid
            if running:  # only fetch collections if bridge is already up
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
