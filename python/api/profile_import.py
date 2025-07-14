import os
import tempfile
from python.helpers.api import ApiHandler
from flask import Request, Response
from python.helpers.profiles import get_profile_manager
from python.helpers.print_style import PrintStyle


class ProfileImport(ApiHandler):
    async def process(self, input: dict, request: Request) -> dict | Response:
        try:
            # Check if file was uploaded
            if 'file' not in request.files:
                return {
                    "success": False,
                    "error": "No file uploaded"
                }
            
            file = request.files['file']
            if file.filename == '':
                return {
                    "success": False,
                    "error": "No file selected"
                }
            
            # Check file extension
            if not file.filename.lower().endswith('.zip'):
                return {
                    "success": False,
                    "error": "Only ZIP files are supported"
                }
            
            # Save uploaded file to temporary location
            temp_fd, temp_path = tempfile.mkstemp(suffix=".zip")
            os.close(temp_fd)
            
            try:
                file.save(temp_path)
                
                profile_manager = get_profile_manager()
                
                # Import profile
                imported_id = profile_manager.import_profile(temp_path)
                
                if imported_id:
                    imported_profile = profile_manager.get_profile(imported_id)
                    return {
                        "success": True,
                        "profile": imported_profile,
                        "message": f"Successfully imported profile '{imported_profile.get('name', imported_id)}'"
                    }
                else:
                    return {
                        "success": False,
                        "error": "Failed to import profile. Please check the file format."
                    }
                    
            finally:
                # Clean up temporary file
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
                
        except Exception as e:
            PrintStyle(font_color="red", padding=True).print(f"Error importing profile: {e}")
            return {
                "success": False,
                "error": str(e)
            }