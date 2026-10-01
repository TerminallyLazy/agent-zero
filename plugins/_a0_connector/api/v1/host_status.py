"""Read-only native host projection; Launcher retains all host permissions."""
from flask import session
from helpers.api import Request, Response
import plugins._a0_connector.api.v1.base as connector_base
from plugins._a0_connector.helpers import host_targets


def session_owner() -> str:
    return str(session.get("csrf_token") or "")


class HostStatus(connector_base.ProtectedConnectorApiHandler):
    @classmethod
    def requires_csrf(cls) -> bool:
        return True

    async def process(self, input: dict, request: Request) -> dict | Response:
        context_id = input.get("context", "")
        if not isinstance(context_id, str) or len(context_id) > 128:
            return Response("Invalid context", status=400)
        context = host_targets.context_for(context_id)
        if context is None:
            return Response("Context not found", status=404)
        return host_targets.host_status(context, session_owner())
