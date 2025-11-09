from python.helpers.api import ApiHandler, Request, Response
from typing import Any
from python.helpers.acp_server import DynamicACPProxy
from python.helpers import settings


class ACPServerStatus(ApiHandler):
    """API handler to get ACP server status and metrics."""

    async def process(self, input: dict[Any, Any], request: Request) -> dict[Any, Any] | Response:
        """
        Get ACP server status and metrics.

        Returns:
            {
                "success": True,
                "status": {
                    "enabled": True/False,
                    "sessionCount": N,
                    "maxSessions": N,
                    "tokenConfigured": True/False
                }
            }
        """
        try:
            current_settings = settings.get_settings()
            proxy = DynamicACPProxy.get_instance()

            status = {
                "enabled": current_settings.get("acp_server_enabled", False),
                "sessionCount": len(proxy.sessions),
                "maxSessions": current_settings.get("acp_max_sessions", 10),
                "tokenConfigured": bool(proxy.token)
            }

            return {
                "success": True,
                "status": status
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
