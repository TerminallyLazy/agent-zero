"""Authenticated same-origin live viewer. Never log request bodies or pixels."""
from helpers.api import Request, Response
import plugins._a0_connector.api.v1.host_status as host_status
from plugins._a0_connector.helpers import host_control, host_targets


class HostViewer(host_status.HostStatus):
    async def process(self, input: dict, request: Request) -> dict | Response:
        if (getattr(request, "content_length", 0) or 0) > 16384:
            return Response("Viewer input exceeded its size limit", status=413)
        context_id = input.get("context")
        if not isinstance(context_id, str) or len(context_id) > 128:
            return Response("Invalid context", status=400)
        owner = host_status.session_owner()
        if not owner:
            return Response("Authenticated session required", status=403)
        context = host_targets.context_for(context_id)
        if context is None:
            return Response("Context not found", status=404)
        try:
            return await host_control.command(context, owner, input)
        except ValueError as exc:
            return Response(str(exc), status=409)
        except TimeoutError:
            return Response("Host acknowledgement was lost. No command was replayed.", status=504)
