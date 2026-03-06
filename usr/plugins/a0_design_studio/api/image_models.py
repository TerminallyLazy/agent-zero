"""API handler to list available image generation models and key status."""
from __future__ import annotations

import importlib.util
import logging
from pathlib import Path

from helpers.api import ApiHandler, Input, Request

log = logging.getLogger("a0_design_studio")

# Load plugin helpers by file path to avoid name collision with framework helpers/
_providers_path = Path(__file__).parent.parent / "helpers" / "image_providers.py"
_spec = importlib.util.spec_from_file_location("ds_image_providers", str(_providers_path))
_providers = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_providers)

IMAGE_MODELS = _providers.IMAGE_MODELS
check_api_key = _providers.check_api_key
fetch_fal_models = _providers.fetch_fal_models
_resolve_api_key = _providers._resolve_api_key


class ImageModels(ApiHandler):

    @classmethod
    def get_methods(cls) -> list[str]:
        return ["POST"]

    async def process(self, input: Input, request: Request) -> dict:
        # Start with the static model list (Gemini, OpenAI, hardcoded FAL).
        seen_ids: set[str] = set()
        models = []
        for m in IMAGE_MODELS:
            seen_ids.add(m["id"])
            models.append({
                "id": m["id"],
                "name": m["name"],
                "provider": m["provider"],
                "key_set": check_api_key(m["provider"]),
            })

        # Dynamically fetch FAL models from their API and merge in new ones.
        try:
            fal_key = _resolve_api_key("fal")
            fal_models = fetch_fal_models(api_key=fal_key)
            for m in fal_models:
                if m["id"] not in seen_ids:
                    seen_ids.add(m["id"])
                    models.append({
                        "id": m["id"],
                        "name": m["name"],
                        "provider": m["provider"],
                        "key_set": fal_key is not None,
                    })
        except Exception as e:
            log.warning("Failed to fetch dynamic FAL models: %s", e)

        return {"models": models}
