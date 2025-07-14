from python.helpers.api import ApiHandler
from flask import Request, Response
from python.helpers.profiles import get_profile_manager
from python.helpers.print_style import PrintStyle


class ProfileUpdate(ApiHandler):
    async def process(self, input: dict, request: Request) -> dict | Response:
        try:
            profile_id = input.get("profile_id")
            profile_data = input.get("profile_data")
            
            if not profile_id:
                return {
                    "success": False,
                    "error": "Profile ID is required"
                }
            
            if not profile_data:
                return {
                    "success": False,
                    "error": "Profile data is required"
                }
            
            profile_manager = get_profile_manager()
            
            # Check if profile exists
            if not profile_manager.profile_exists(profile_id):
                return {
                    "success": False,
                    "error": f"Profile '{profile_id}' not found"
                }
            
            # Validate profile data
            errors = profile_manager.validate_profile(profile_data)
            if errors:
                return {
                    "success": False,
                    "error": "Validation failed",
                    "errors": errors
                }
            
            success = profile_manager.update_profile(profile_id, profile_data)
            
            if success:
                updated_profile = profile_manager.get_profile(profile_id)
                return {
                    "success": True,
                    "profile": updated_profile
                }
            else:
                return {
                    "success": False,
                    "error": "Failed to update profile"
                }
                
        except Exception as e:
            PrintStyle(font_color="red", padding=True).print(f"Error updating profile: {e}")
            return {
                "success": False,
                "error": str(e)
            }