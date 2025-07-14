import uuid
import shutil
from python.helpers.api import ApiHandler
from flask import Request, Response
from python.helpers.profiles import get_profile_manager
from python.helpers.print_style import PrintStyle
from python.helpers import files


class ProfileCreateFromTemplate(ApiHandler):
    async def process(self, input: dict, request: Request) -> dict | Response:
        try:
            template_id = input.get("template_id")
            profile_name = input.get("profile_name")
            profile_description = input.get("profile_description", "")
            
            if not template_id:
                return {
                    "success": False,
                    "error": "Template ID is required"
                }
            
            if not profile_name:
                return {
                    "success": False,
                    "error": "Profile name is required"
                }
            
            profile_manager = get_profile_manager()
            
            # Check if template exists
            template_path = files.get_abs_path("profiles", "templates", template_id)
            if not files.exists(template_path):
                return {
                    "success": False,
                    "error": f"Template '{template_id}' not found"
                }
            
            # Generate new profile ID
            new_profile_id = str(uuid.uuid4())
            
            # Copy template to new profile
            new_profile_path = profile_manager.get_profile_path(new_profile_id)
            shutil.copytree(template_path, new_profile_path)
            
            # Load and update the profile config
            template_config_path = files.get_abs_path(template_path, "profile.json")
            with open(template_config_path, 'r', encoding='utf-8') as f:
                import json
                profile_data = json.load(f)
            
            # Update profile data for the new instance
            profile_data["id"] = new_profile_id
            profile_data["name"] = profile_name
            profile_data["description"] = profile_description
            profile_data["is_template"] = False
            profile_data["template_source"] = template_id
            profile_data["memory_subdir"] = new_profile_id
            
            # Update prompts_subdir to point to the new profile if it was using template name
            if profile_data.get("prompts_subdir") == template_id:
                profile_data["prompts_subdir"] = new_profile_id
            
            # Save the updated config
            success = profile_manager.update_profile(new_profile_id, profile_data)
            
            if success:
                created_profile = profile_manager.get_profile(new_profile_id)
                return {
                    "success": True,
                    "profile": created_profile,
                    "message": f"Created profile '{profile_name}' from template '{template_id}'"
                }
            else:
                return {
                    "success": False,
                    "error": "Failed to create profile from template"
                }
                
        except Exception as e:
            PrintStyle(font_color="red", padding=True).print(f"Error creating profile from template: {e}")
            return {
                "success": False,
                "error": str(e)
            }