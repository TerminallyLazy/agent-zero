"""API handler to list available image generation models and key status."""
from __future__ import annotations

import sys
from pathlib import Path

from python.helpers.api import ApiHandler, Input, Request

_plugin_root = Path(__file__).parent.parent
if str(_plugin_root) not in sys.path:
    sys.path.insert(0, str(_plugin_root))

from helpers.image_providers import IMAGE_MODELS, check_api_key


class ImageModels(ApiHandler):

    @classmethod
    def get_methods(cls) -> list[str]:
        return ["POST"]

    async def process(self, input: Input, request: Request) -> dict:
        models = []
        for m in IMAGE_MODELS:
            models.append({
                "id": m["id"],
                "name": m["name"],
                "provider": m["provider"],
                "key_set": check_api_key(m["provider"]),
            })
        return {"models": models}
