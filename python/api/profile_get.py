from python.helpers.api import ApiHandler
from flask import Request, Response
from python.helpers.profiles import get_profile_manager
from python.helpers.print_style import PrintStyle


class ProfileGet(ApiHandler):
    async def process(self, input: dict, request: Request) -> dict | Response:
        try:
            profile_id = input.get("profile_id")
            if not profile_id:
                return {
                    "success": False,
                    "error": "Profile ID is required"
                }
            
            profile_manager = get_profile_manager()
            profile = profile_manager.get_profile(profile_id)
            
            if not profile:
                return {
                    "success": False,
                    "error": f"Profile '{profile_id}' not found"
                }
            
            return {
                "profile": profile,
                "success": True
            }
        except Exception as e:
            PrintStyle(font_color="red", padding=True).print(f"Error getting profile: {e}")
            return {
                "success": False,
                "error": str(e)
            }