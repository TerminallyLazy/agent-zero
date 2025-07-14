import os
import tempfile
from python.helpers.api import ApiHandler
from flask import Request, Response, send_file
from python.helpers.profiles import get_profile_manager
from python.helpers.print_style import PrintStyle


class ProfileExport(ApiHandler):
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
            
            # Get profile info for filename
            profile = profile_manager.get_profile(profile_id)
            profile_name = profile.get("name", profile_id) if profile else profile_id
            
            # Create temporary file for export
            temp_fd, temp_path = tempfile.mkstemp(suffix=".zip")
            os.close(temp_fd)
            
            success = profile_manager.export_profile(profile_id, temp_path)
            
            if success:
                # Return the file for download
                filename = f"{profile_name.replace(' ', '_')}_profile.zip"
                return send_file(
                    temp_path,
                    as_attachment=True,
                    download_name=filename,
                    mimetype="application/zip"
                )
            else:
                # Clean up temp file on error
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
                return {
                    "success": False,
                    "error": "Failed to export profile"
                }
                
        except Exception as e:
            PrintStyle(font_color="red", padding=True).print(f"Error exporting profile: {e}")
            return {
                "success": False,
                "error": str(e)
            }