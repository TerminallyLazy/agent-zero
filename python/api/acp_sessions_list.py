from python.helpers.api import ApiHandler, Request, Response
from typing import Any
from python.helpers.acp_server import DynamicACPProxy


class ACPSessionsList(ApiHandler):
    """API handler to list active ACP sessions."""

    async def process(self, input: dict[Any, Any], request: Request) -> dict[Any, Any] | Response:
        """
        List all active ACP sessions.

        Returns:
            {
                "success": True,
                "sessions": [
                    {
                        "sessionId": "...",
                        "contextId": "...",
                        "contextName": "..."
                    }
                ]
            }
        """
        try:
            proxy = DynamicACPProxy.get_instance()
            sessions = []

            for session_id, context in proxy.sessions.items():
                sessions.append({
                    "sessionId": session_id,
                    "contextId": context.id,
                    "contextName": context.name or "Unnamed"
                })

            return {
                "success": True,
                "sessions": sessions
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
