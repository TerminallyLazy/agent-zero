from python.helpers.api import ApiHandler, Request, Response
from datetime import datetime, timezone


class AcpPing(ApiHandler):
    """ACP Ping endpoint."""
    
    @classmethod
    def requires_auth(cls) -> bool:
        return False
    
    @classmethod
    def get_methods(cls) -> list[str]:
        return ["GET", "POST"]
    
    async def process(self, input: dict, request: Request) -> dict | Response:
        return {
            "status": "ok",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "protocol": "ACP",
            "version": "0.2.0"
        }