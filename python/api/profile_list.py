from python.helpers.api import ApiHandler
from flask import Request, Response
from python.helpers.profiles import get_profile_manager
from python.helpers.print_style import PrintStyle


class ProfileList(ApiHandler):
    async def process(self, input: dict, request: Request) -> dict | Response:
        try:
            profile_manager = get_profile_manager()
            profiles = profile_manager.list_profiles()
            active_profile_id = profile_manager.get_active_profile_id()
            
            return {
                "profiles": profiles,
                "active_profile_id": active_profile_id,
                "success": True
            }
        except Exception as e:
            PrintStyle(font_color="red", padding=True).print(f"Error listing profiles: {e}")
            return {
                "profiles": [],
                "active_profile_id": "default",
                "success": False,
                "error": str(e)
            }