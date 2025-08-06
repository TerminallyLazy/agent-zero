from python.helpers.api import ApiHandler, Request, Response

class NotificationCreate(ApiHandler):
    
    @classmethod
    def requires_auth(cls) -> bool:
        return False
    
    @classmethod 
    def get_methods(cls) -> list[str]:
        return ["POST"]

    async def process(self, input: dict, request: Request) -> dict:
        # Simplified notification system for lite version - just return success
        return {"success": True, "message": "Notification functionality disabled in lite version"}