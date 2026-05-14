from helpers.api import ApiHandler, Request
from usr.plugins.a0_swarm.helpers.registry import SwarmRegistry


class SwarmStatus(ApiHandler):
    async def process(self, input: dict, request: Request) -> dict:
        parent = (input or {}).get("parent_context_id") or None
        return {"agents": SwarmRegistry.get().snapshot(parent_ctx_id=parent)}
