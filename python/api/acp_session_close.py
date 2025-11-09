from python.helpers.api import ApiHandler, Request, Response
from typing import Any
from python.helpers.acp_server import DynamicACPProxy


class ACPSessionClose(ApiHandler):
    """API handler to close a specific ACP session."""

    async def process(self, input: dict[Any, Any], request: Request) -> dict[Any, Any] | Response:
        """
        Close an ACP session.

        Input:
            {
                "sessionId": "session-id-to-close"
            }

        Returns:
            {
                "success": True/False,
                "message": "..."
            }
        """
        try:
            session_id = input.get("sessionId")

            if not session_id:
                return {
                    "success": False,
                    "error": "sessionId parameter required"
                }

            proxy = DynamicACPProxy.get_instance()

            # Call the close_session method
            result = await proxy.close_session({"sessionId": session_id})

            return {
                "success": True,
                "message": f"Session {session_id} closed",
                "result": result
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
