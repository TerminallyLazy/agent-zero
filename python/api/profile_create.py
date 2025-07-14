from python.helpers.api import ApiHandler
from flask import Request, Response
from python.helpers.profiles import get_profile_manager
from python.helpers.print_style import PrintStyle


class ProfileCreate(ApiHandler):
    async def process(self, input: dict, request: Request) -> dict | Response:
        try:
            profile_data = input.get("profile_data")
            if not profile_data:
                return {
                    "success": False,
                    "error": "Profile data is required"
                }
            
            profile_manager = get_profile_manager()
            
            # Validate profile data
            errors = profile_manager.validate_profile(profile_data)
            if errors:
                return {
                    "success": False,
                    "error": "Validation failed",
                    "errors": errors
                }
            
            # Check if profile with same ID already exists
            profile_id = profile_data.get("id")
            if profile_id and profile_manager.profile_exists(profile_id):
                return {
                    "success": False,
                    "error": f"Profile with ID '{profile_id}' already exists"
                }
            
            success = profile_manager.create_profile(profile_data)
            
            if success:
                created_profile = profile_manager.get_profile(profile_data["id"])
                return {
                    "success": True,
                    "profile": created_profile
                }
            else:
                return {
                    "success": False,
                    "error": "Failed to create profile"
                }
                
        except Exception as e:
            PrintStyle(font_color="red", padding=True).print(f"Error creating profile: {e}")
            return {
                "success": False,
                "error": str(e)
            }