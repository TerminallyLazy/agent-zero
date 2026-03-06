"""API handler for image generation."""
from __future__ import annotations

import importlib.util
from pathlib import Path

from helpers.api import ApiHandler, Input, Request

# Load plugin helpers by file path to avoid name collision with framework helpers/
_providers_path = Path(__file__).parent.parent / "helpers" / "image_providers.py"
_spec = importlib.util.spec_from_file_location("ds_image_providers", str(_providers_path))
_providers = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_providers)

generate_image = _providers.generate_image
get_plugin_config = _providers.get_plugin_config


class ImageGenerate(ApiHandler):

    @classmethod
    def get_methods(cls) -> list[str]:
        return ["POST"]

    async def process(self, input: Input, request: Request) -> dict:
        prompt = input.get("prompt", "")
        if not prompt:
            return {"error": "prompt is required", "images": []}

        config = get_plugin_config()
        model = input.get("model") or config.get("image_generation_model", "gemini/gemini-3.1-flash-image-preview")
        size = input.get("size") or config.get("default_size", "1024x1024")
        n = input.get("n") or config.get("default_count", 1)

        try:
            results = await generate_image(prompt=prompt, model=model, size=size, n=int(n))
            return {"images": results, "model": model}
        except Exception as e:
            return {"error": str(e), "images": []}
