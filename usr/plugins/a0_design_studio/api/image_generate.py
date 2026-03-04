"""API handler for image generation."""
from __future__ import annotations

import sys
from pathlib import Path

from python.helpers.api import ApiHandler, Input, Request

# Ensure plugin helpers are importable
_plugin_root = Path(__file__).parent.parent
if str(_plugin_root) not in sys.path:
    sys.path.insert(0, str(_plugin_root))

from helpers.image_providers import generate_image, get_plugin_config


class ImageGenerate(ApiHandler):

    @classmethod
    def get_methods(cls) -> list[str]:
        return ["POST"]

    async def process(self, input: Input, request: Request) -> dict:
        prompt = input.get("prompt", "")
        if not prompt:
            return {"error": "prompt is required", "images": []}

        config = get_plugin_config()
        model = input.get("model") or config.get("image_generation_model", "openai/dall-e-3")
        size = input.get("size") or config.get("default_size", "1024x1024")
        n = input.get("n") or config.get("default_count", 1)

        try:
            results = await generate_image(prompt=prompt, model=model, size=size, n=int(n))
            return {"images": results, "model": model}
        except Exception as e:
            return {"error": str(e), "images": []}
