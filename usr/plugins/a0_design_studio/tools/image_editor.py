"""Agent tool for AI image generation and editing."""
from __future__ import annotations

import base64
import os
import time
import sys
from pathlib import Path

from helpers.tool import Tool, Response

_plugin_root = Path(__file__).parent.parent
if str(_plugin_root) not in sys.path:
    sys.path.insert(0, str(_plugin_root))

from helpers.image_providers import generate_image, edit_image, get_plugin_config


class ImageEditor(Tool):

    async def execute(self, **kwargs) -> Response:
        action = self.args.get("action", "generate")
        config = get_plugin_config()

        if action == "generate":
            return await self._generate(config)
        elif action == "edit":
            return await self._edit(config)
        elif action == "save":
            return await self._save(config)
        else:
            return Response(message=f"Unknown action: {action}", break_loop=False)

    async def _generate(self, config: dict) -> Response:
        prompt = self.args.get("prompt", "")
        if not prompt:
            return Response(message="Error: prompt is required for generation.", break_loop=False)

        model = self.args.get("model") or config.get("image_generation_model", "openai/dall-e-3")
        size = self.args.get("size") or config.get("default_size", "1024x1024")
        gallery_path = config.get("gallery_path", "images")

        results = await generate_image(prompt=prompt, model=model, size=size)

        if not results:
            return Response(message="Image generation returned no results.", break_loop=False)

        # Save first result to gallery
        os.makedirs(gallery_path, exist_ok=True)
        filename = f"generated_{int(time.time())}.png"
        fpath = os.path.join(gallery_path, filename)

        b64_data = results[0].get("b64_json", "")
        if b64_data:
            with open(fpath, "wb") as f:
                f.write(base64.b64decode(b64_data))

        revised = results[0].get("revised_prompt", prompt)
        return Response(
            message=f"Image generated and saved to `{fpath}`.\nPrompt used: {revised}",
            break_loop=False,
        )

    async def _edit(self, config: dict) -> Response:
        image_path = self.args.get("image_path", "")
        prompt = self.args.get("prompt", "")

        if not image_path:
            return Response(message="Error: image_path is required for editing.", break_loop=False)
        if not prompt:
            return Response(message="Error: prompt is required for editing.", break_loop=False)
        if not os.path.isfile(image_path):
            return Response(message=f"Error: Image not found at {image_path}", break_loop=False)

        with open(image_path, "rb") as f:
            image_b64 = base64.b64encode(f.read()).decode()

        model = self.args.get("model") or config.get("image_edit_model", "google/gemini-2.0-flash")
        results = await edit_image(image_b64=image_b64, prompt=prompt, model=model)

        if not results:
            return Response(message="Image editing returned no results.", break_loop=False)

        return Response(
            message=f"Image edit analysis for `{image_path}`:\n{results[0].get('content', '')}",
            break_loop=False,
        )

    async def _save(self, config: dict) -> Response:
        image_path = self.args.get("image_path", "")
        output_path = self.args.get("output_path", "")

        if not image_path or not output_path:
            return Response(message="Error: image_path and output_path are required.", break_loop=False)
        if not os.path.isfile(image_path):
            return Response(message=f"Error: Image not found at {image_path}", break_loop=False)

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        import shutil
        shutil.copy2(image_path, output_path)

        return Response(message=f"Image saved to `{output_path}`.", break_loop=False)
