from python.helpers.api import ApiHandler
from flask import Request, Response
from python.helpers.profiles import get_profile_manager
from python.helpers.print_style import PrintStyle


class ProfileSwitch(ApiHandler):
    async def process(self, input: dict, request: Request) -> dict | Response:
        try:
            profile_id = input.get("profile_id")
            
            if not profile_id:
                return {
                    "success": False,
                    "error": "Profile ID is required"
                }
            
            profile_manager = get_profile_manager()
            
            # Check if profile exists
            if not profile_manager.profile_exists(profile_id):
                return {
                    "success": False,
                    "error": f"Profile '{profile_id}' not found"
                }
            
            success = profile_manager.set_active_profile(profile_id)
            
            if success:
                active_profile = profile_manager.get_active_profile()
                return {
                    "success": True,
                    "active_profile": active_profile,
                    "message": f"Switched to profile '{active_profile.get('name', profile_id)}'"
                }
            else:
                return {
                    "success": False,
                    "error": "Failed to switch profile"
                }
                
        except Exception as e:
            PrintStyle(font_color="red", padding=True).print(f"Error switching profile: {e}")
            return {
                "success": False,
                "error": str(e)
            }