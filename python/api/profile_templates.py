from python.helpers.api import ApiHandler
from flask import Request, Response
from python.helpers.profiles import get_profile_manager
from python.helpers.print_style import PrintStyle
from python.helpers import files
import os
import json


class ProfileTemplates(ApiHandler):
    async def process(self, input: dict, request: Request) -> dict | Response:
        try:
            profile_manager = get_profile_manager()
            templates = []
            
            templates_dir = files.get_abs_path("profiles", "templates")
            
            if os.path.exists(templates_dir):
                for item in os.listdir(templates_dir):
                    template_path = files.get_abs_path(templates_dir, item)
                    if os.path.isdir(template_path):
                        config_path = files.get_abs_path(template_path, "profile.json")
                        if os.path.exists(config_path):
                            try:
                                with open(config_path, 'r', encoding='utf-8') as f:
                                    template_data = json.load(f)
                                    template_data["is_template"] = True
                                    templates.append(template_data)
                            except Exception as e:
                                PrintStyle(font_color="orange", padding=True).print(
                                    f"Warning: Could not load template '{item}': {e}"
                                )
            
            # Sort templates by name
            templates.sort(key=lambda t: t.get("name", ""))
            
            return {
                "templates": templates,
                "success": True
            }
            
        except Exception as e:
            PrintStyle(font_color="red", padding=True).print(f"Error listing templates: {e}")
            return {
                "templates": [],
                "success": False,
                "error": str(e)
            }