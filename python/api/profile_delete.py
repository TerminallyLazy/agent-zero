from python.helpers.api import ApiHandler
from flask import Request, Response
from python.helpers.profiles import get_profile_manager
from python.helpers.print_style import PrintStyle


class ProfileDelete(ApiHandler):
    async def process(self, input: dict, request: Request) -> dict | Response:
        try:
            profile_id = input.get("profile_id")
            
            if not profile_id:
                return {
                    "success": False,
                    "error": "Profile ID is required"
                }
            
            # Don't allow deleting the default profile
            if profile_id == "default":
                return {
                    "success": False,
                    "error": "Cannot delete the default profile"
                }
            
            profile_manager = get_profile_manager()
            
            # Check if profile exists
            if not profile_manager.profile_exists(profile_id):
                return {
                    "success": False,
                    "error": f"Profile '{profile_id}' not found"
                }
            
            success = profile_manager.delete_profile(profile_id)
            
            return {
                "success": success,
                "error": None if success else "Failed to delete profile"
            }
                
        except Exception as e:
            PrintStyle(font_color="red", padding=True).print(f"Error deleting profile: {e}")
            return {
                "success": False,
                "error": str(e)
            }