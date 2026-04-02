from __future__ import annotations

from helpers.api import ApiHandler, Request, Response

from usr.plugins.agent_harness.helpers.deerflow_client import DeerFlowClient


class ThreadData(ApiHandler):
    async def process(self, input: dict, request: Request) -> dict | Response:
        action = str(input.get("action", "status")).strip().lower()
        context_id = str(input.get("context_id", "")).strip()
        context = self.use_context(context_id, create_if_not_exists=False)
        client = DeerFlowClient(context)

        if action == "cleanup":
            return {
                "success": True,
                "context_id": context.id,
                "thread": client.cleanup_thread(),
            }

        return {
            "success": True,
            "context_id": context.id,
            "thread": client.thread_status(),
        }
