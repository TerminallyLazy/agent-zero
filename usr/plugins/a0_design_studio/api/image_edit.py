"""API handler for image editing via vision models."""
from __future__ import annotations

import importlib.util
from pathlib import Path

from helpers.api import ApiHandler, Input, Request

# Load plugin helpers by file path to avoid name collision with framework helpers/
_providers_path = Path(__file__).parent.parent / "helpers" / "image_providers.py"
_spec = importlib.util.spec_from_file_location("ds_image_providers", str(_providers_path))
_providers = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_providers)

edit_image = _providers.edit_image
get_plugin_config = _providers.get_plugin_config


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
        # Use the model sent by the frontend (the same dropdown as generation).
        # Gemini uses the same generateContent endpoint for both generate & edit.
        model = input.get("model") or config.get("image_generation_model", "gemini/gemini-3.1-flash-image-preview")
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
