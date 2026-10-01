"""Protected, chat-independent computer setup and continuation."""
from flask import session
from helpers.api import Request, Response
import plugins._a0_connector.api.v1.base as connector_base
from plugins._a0_connector.helpers import host_setup


class HostSetup(connector_base.ProtectedConnectorApiHandler):
    @classmethod
    def requires_csrf(cls) -> bool:
        return True

    async def process(self, input: dict, request: Request) -> dict | Response:
        if (request.content_length or 0) > 4096 or not isinstance(input, dict) or len(str(input)) > 4096:
            return Response("Invalid setup request", status=400)
        action = input.get("action", "status")
        try:
            if action == "status":
                return host_setup.snapshot()
            # Core has one credential owner today. A future multi-user provider
            # must supply its authenticated principal, never a client parameter.
            owner = str(session.get("user_id") or session.get("authentication") or "")
            return host_setup.continuation(owner, action, input)
        except ValueError as error:
            return Response(str(error), status=400)
