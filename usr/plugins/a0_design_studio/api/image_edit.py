"""API handler for image editing via vision models."""
from __future__ import annotations

import sys
from pathlib import Path

from python.helpers.api import ApiHandler, Input, Request

_plugin_root = Path(__file__).parent.parent
if str(_plugin_root) not in sys.path:
    sys.path.insert(0, str(_plugin_root))

from helpers.image_providers import edit_image, get_plugin_config


class ImageEdit(ApiHandler):

    @classmethod
    def get_methods(cls) -> list[str]:
        return ["POST"]

    async def process(self, input: Input, request: Request) -> dict:
        image_b64 = input.get("image_b64", "")
        prompt = input.get("prompt", "")

        if not image_b64:
            return {"error": "image_b64 is required", "images": []}
        if not prompt:
            return {"error": "prompt is required", "images": []}

        config = get_plugin_config()
        model = input.get("model") or config.get("image_edit_model", "gemini/gemini-2.0-flash")
        mask_b64 = input.get("mask_b64")

        try:
            results = await edit_image(
                image_b64=image_b64,
                prompt=prompt,
                mask_b64=mask_b64,
                model=model,
            )
            return {"images": results, "model": model}
        except Exception as e:
            return {"error": str(e), "images": []}
