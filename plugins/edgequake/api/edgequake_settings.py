"""
API handler for EdgeQuake plugin settings.

Actions:
- load: Read current settings (API key masked)
- save: Validate and persist settings
- test: Test connection with provided (unsaved) settings
"""

from flask import Request
from python.helpers.api import ApiHandler, Input, Output

ALLOWED_KEYS = {"base_url", "api_key", "workspace_id", "tenant_id", "timeout"}


class EdgequakeSettings(ApiHandler):

    async def process(self, input: Input, request: Request) -> Output:
        action = input.get("action", "load")

        if action == "load":
            return self._load()
        elif action == "save":
            return self._save(input.get("settings", {}))
        elif action == "test":
            return self._test(input.get("settings", {}))
        else:
            return {"error": f"Unknown action: {action}"}

    def _load(self) -> dict:
        from plugins.edgequake.helpers.edgequake_client import get_edgequake_settings

        settings = get_edgequake_settings()
        # Mask API key for display
        api_key = settings.get("api_key", "")
        if api_key and len(api_key) > 4:
            settings["api_key"] = "****" + api_key[-4:]
        elif api_key:
            settings["api_key"] = "****"
        return {"settings": settings}

    def _save(self, settings: dict) -> dict:
        from plugins.edgequake.helpers.edgequake_client import (
            get_edgequake_settings,
            save_edgequake_settings,
        )

        if not settings:
            return {"error": "No settings provided"}

        # Only accept known settings keys
        settings = {k: v for k, v in settings.items() if k in ALLOWED_KEYS}

        # Merge with existing — if API key is masked, keep the original
        current = get_edgequake_settings()
        api_key = settings.get("api_key", "").strip()
        if api_key.startswith("****") or not api_key:
            settings["api_key"] = current.get("api_key", "")

        # Validate base_url
        base_url = settings.get("base_url", "").strip()
        if not base_url:
            settings["base_url"] = "http://localhost:8080"

        # Ensure timeout is an int
        try:
            settings["timeout"] = int(settings.get("timeout", 30))
        except (ValueError, TypeError):
            settings["timeout"] = 30

        save_edgequake_settings(settings)
        return {"success": True}

    def _test(self, settings: dict) -> dict:
        from plugins.edgequake.helpers.edgequake_client import (
            get_edgequake_settings,
            test_connection,
        )

        if not settings:
            return {"error": "No settings provided"}

        # If API key is masked, substitute from saved settings
        api_key = settings.get("api_key", "").strip()
        if api_key.startswith("****") or not api_key:
            current = get_edgequake_settings()
            settings["api_key"] = current.get("api_key", "")

        if not settings.get("api_key", "").strip():
            return {"error": "API key is required to test connection"}

        return test_connection(settings=settings)
