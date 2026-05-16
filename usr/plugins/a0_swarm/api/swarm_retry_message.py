from helpers.api import ApiHandler, Request
from usr.plugins.a0_swarm.helpers.registry import SwarmRegistry
from usr.plugins.a0_swarm.helpers import delivery


class SwarmRetryMessage(ApiHandler):
    async def process(self, input: dict, request: Request):
        message_id = (input or {}).get("message_id", "")
        if not message_id:
            return {"ok": False, "error": "message_id is required"}

        reg = SwarmRegistry.get()
        msg = reg.get_message(message_id)
        if not msg:
            return {"ok": False, "error": f"Message {message_id} not found"}
        if msg.delivery_state == "delivered":
            return {"ok": True, "message_id": message_id, "delivery_state": "delivered", "error": ""}

        reg.mark_message_queued(message_id)
        result = await delivery.deliver_message(message_id)
        return {
            "ok": result.ok,
            "message_id": message_id,
            "delivery_state": result.state,
            "error": result.reason,
        }
