from helpers.api import ApiHandler, Request
from usr.plugins.a0_swarm.helpers.registry import SwarmRegistry


class SwarmClearCompleted(ApiHandler):
    async def process(self, input: dict, request: Request):
        parent = (input or {}).get("parent_context_id") or None
        SwarmRegistry.get().clear_completed(parent_ctx_id=parent)
        return {"ok": True}
