from python.helpers.api import ApiHandler
from flask import Request, Response

from python.helpers import settings

from typing import Any


class SetSettings(ApiHandler):
    async def process(self, input: dict[Any, Any], request: Request) -> dict[Any, Any] | Response:
        # Check if profile is being changed
        if "active_profile" in input:
            try:
                from python.helpers.profiles import get_profile_manager
                profile_manager = get_profile_manager()
                new_profile_id = input["active_profile"]
                
                # Switch to the new profile
                success = profile_manager.set_active_profile(new_profile_id)
                if not success:
                    return {
                        "error": f"Failed to switch to profile '{new_profile_id}'",
                        "success": False
                    }
                
                # Remove active_profile from settings input since it's not a regular setting
                settings_input = {k: v for k, v in input.items() if k != "active_profile"}
            except Exception as e:
                return {
                    "error": f"Error switching profile: {e}",
                    "success": False
                }
        else:
            settings_input = input
        
        # Process regular settings
        set = settings.convert_in(settings_input)
        set = settings.set_settings(set)
        return {"settings": set}
