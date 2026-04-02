from __future__ import annotations

from helpers.api import ApiHandler, Request, Response

from usr.plugins.agent_harness.helpers.deerflow_client import DeerFlowClient


class DeerflowCore(ApiHandler):
    async def process(self, input: dict, request: Request) -> dict | Response:
        context_id = str(input.get("context_id", "")).strip()
        context = self.use_context(context_id, create_if_not_exists=False)
        skills_limit = int(input.get("skills_limit", 50) or 50)
        client = DeerFlowClient(context)

        return {
            "success": True,
            "context_id": context.id,
            **(await client.core_state(skills_limit=skills_limit)),
        }
