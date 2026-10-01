"""One explicit, journaled mobile message with an enforced context host target."""
import threading
from agent import UserMessage
from helpers import extension, message_queue, persist_chat
from helpers.api import Request, Response
from helpers.state_monitor_integration import mark_dirty_for_context
import plugins._a0_connector.api.v1.host_status as host_status
from plugins._a0_connector.helpers import host_targets

_submission_lock = threading.RLock()


class HostTask(host_status.HostStatus):
    async def process(self, input: dict, request: Request) -> dict | Response:
        for key, limit in (("context", 128), ("text", 1_048_576), ("message_id", 128),
                           ("target_id", 64), ("generation", 64), ("capability", 32)):
            if not isinstance(input.get(key), str) or not input[key].strip() or len(input[key]) > limit:
                return Response("Invalid host task", status=400)
        if input.get("queued") not in ("true", "false") or input.get("attachments"):
            return Response("Host tasks require text and an explicit queue mode", status=400)
        owner = host_status.session_owner()
        if not owner:
            return Response("Authenticated session bootstrap required", status=403)
        context = host_targets.context_for(input["context"])
        if context is None:
            return Response("Context not found", status=404)
        data = {"message": input["text"], "attachment_paths": []}
        await extension.call_extensions_async("user_message_ui", agent=context.get_agent(), data=data)
        # No await between final route validation, durable binding and submission.
        with _submission_lock:
            previous = context.get_data(host_targets.KEY)
            try:
                host_targets.bind(context, owner, input["target_id"], input["generation"], input["capability"])
            except host_targets.HostTargetError as exc:
                return Response(str(exc), status=409)
            try:
                persist_chat.save_tmp_chat(context)
            except Exception:
                context.set_data(host_targets.KEY, previous)
                return Response("Could not persist the host target; no message sent", status=500)
            text = data.get("message", "")
            attachments = data.get("attachment_paths", [])
            if input["queued"] == "true":
                item = message_queue.add(context, text, attachments, input["message_id"])
                mark_dirty_for_context(context.id, reason="connector_host_task")
                return {"ok": True, "context": context.id, "message_id": item["id"], "queued": True}
            message_queue.log_user_message(context, text, attachments, input["message_id"])
            context.communicate(UserMessage(message=text, attachments=attachments, id=input["message_id"]))
            return {"ok": True, "context": context.id, "message_id": input["message_id"], "queued": False}
