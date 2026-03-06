"""Image provider layer for A0 Design Studio.

Gemini models call the Google AI Studio REST API directly (no LiteLLM) to
avoid Vertex AI credential probing.  OpenAI/DALL-E models still use LiteLLM.
Uses Agent Zero's API key management so keys configured in Settings work.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
from urllib.request import Request, urlopen

log = logging.getLogger("a0_design_studio")

# ---------------------------------------------------------------------------
# Provider / key helpers
# ---------------------------------------------------------------------------

# Map LiteLLM provider prefixes to Agent Zero API_KEY_<NAME> identifiers.
_PROVIDER_TO_KEY_NAME: dict[str, str] = {
    "gemini": "google",
    "google": "google",
    "openai": "openai",
    "dall-e-2": "openai",
    "dall-e-3": "openai",
    "openrouter": "openrouter",
    "azure": "azure",
    "bedrock": "bedrock",
    "fal": "fal",
}

# Available image generation models shown in the UI dropdown.
IMAGE_MODELS: list[dict] = [
    {"id": "gemini/gemini-3.1-flash-image-preview", "name": "Gemini 3.1 Flash Image", "provider": "google", "method": "completion"},
    {"id": "gemini/gemini-3-pro-image-preview", "name": "Gemini 3 Pro Image", "provider": "google", "method": "completion"},
    {"id": "gemini/gemini-2.5-flash-image", "name": "Gemini 2.5 Flash Image", "provider": "google", "method": "completion"},
    {"id": "dall-e-3", "name": "DALL-E 3", "provider": "openai", "method": "image_generation"},
    {"id": "openai/gpt-image-1", "name": "GPT Image 1", "provider": "openai", "method": "image_generation"},
    {"id": "fal/fal-ai/flux/schnell",        "name": "FLUX.1 Schnell (FAL)", "provider": "fal", "method": "image_generation"},
    {"id": "fal/fal-ai/flux/dev",            "name": "FLUX.1 Dev (FAL)",     "provider": "fal", "method": "image_generation"},
    {"id": "fal/fal-ai/flux-pro/v1.1-ultra", "name": "FLUX Pro Ultra (FAL)", "provider": "fal", "method": "image_generation"},
]

_GOOGLE_AI_BASE = "https://generativelanguage.googleapis.com/v1beta"


def _extract_provider(model: str) -> str:
    """Extract the provider name from a model string for key lookup."""
    if "/" in model:
        return model.split("/")[0]
    if model in _PROVIDER_TO_KEY_NAME:
        return model
    for prefix in ("gemini", "gpt", "claude"):
        if model.startswith(prefix):
            return prefix
    return model


def _is_gemini(model: str) -> bool:
    """True if this model should be routed to Google AI Studio directly."""
    return _extract_provider(model) in ("gemini", "google")


def _is_fal(model: str) -> bool:
    """True if this model should be routed to FAL.ai REST API."""
    return _extract_provider(model) == "fal"


def _bare_model(model: str) -> str:
    """Strip the provider prefix: 'gemini/gemini-3.1-flash-image-preview' -> 'gemini-3.1-flash-image-preview'."""
    return model.split("/", 1)[1] if "/" in model else model


def _resolve_api_key(provider: str) -> str | None:
    """Look up the API key for a provider using Agent Zero's key management."""
    key_name = _PROVIDER_TO_KEY_NAME.get(provider, provider)
    try:
        from models import get_api_key
        key = get_api_key(key_name)
        if key and key not in ("None", "NA"):
            return key
    except (ImportError, Exception):
        pass
    # FAL: check plugin config, then native FAL_KEY env var as fallbacks.
    if provider == "fal":
        try:
            cfg = get_plugin_config()
            fal_key = cfg.get("fal_api_key", "")
            if fal_key:
                return fal_key
        except Exception:
            pass
        return os.environ.get("FAL_KEY")
    return None


def check_api_key(provider: str) -> bool:
    """Return True if the API key for the given provider is configured."""
    return _resolve_api_key(provider) is not None


def _get_litellm():
    """Lazy-import litellm (only needed for OpenAI/DALL-E models)."""
    # Inject GEMINI_API_KEY before import to suppress Vertex credential probes.
    key = _resolve_api_key("gemini")
    if key and not os.environ.get("GEMINI_API_KEY"):
        os.environ["GEMINI_API_KEY"] = key
    import litellm
    litellm.drop_params = True
    return litellm


# ---------------------------------------------------------------------------
# Google AI Studio direct REST API
# ---------------------------------------------------------------------------

def _gemini_generate_content(
    model_name: str,
    parts: list[dict],
    api_key: str,
) -> dict:
    """Call Google AI Studio generateContent REST API directly.

    This bypasses LiteLLM entirely, avoiding all Vertex AI credential
    probing issues.  Uses stdlib urllib so no extra dependencies needed.

    Args:
        model_name: Bare model name (e.g. 'gemini-3.1-flash-image-preview').
        parts: List of content parts (text and/or inline_data).
        api_key: Google AI Studio API key.

    Returns:
        Parsed JSON response dict.
    """
    url = f"{_GOOGLE_AI_BASE}/models/{model_name}:generateContent"
    body = json.dumps({
        "contents": [{"parts": parts}],
        "generationConfig": {
            "responseModalities": ["TEXT", "IMAGE"],
        },
    }).encode("utf-8")

    req = Request(
        url,
        data=body,
        headers={
            "x-goog-api-key": api_key,
            "Content-Type": "application/json",
        },
        method="POST",
    )

    with urlopen(req, timeout=120) as resp:
        return json.loads(resp.read())


def _extract_images_from_gemini_response(response: dict) -> list[dict]:
    """Extract b64_json images from a Gemini generateContent response."""
    results = []
    text_parts = []

    for candidate in response.get("candidates", []):
        for part in candidate.get("content", {}).get("parts", []):
            if "inlineData" in part:
                b64 = part["inlineData"].get("data")
                results.append({
                    "b64_json": b64,
                    "url": None,
                    "revised_prompt": None,
                })
            elif "text" in part:
                text_parts.append(part["text"])

    # Attach any text to the first result as revised_prompt
    if results and text_parts:
        results[0]["revised_prompt"] = " ".join(text_parts)

    return results


def _require_api_key(model: str) -> tuple[str, str]:
    """Resolve API key or raise ValueError.  Returns (provider, api_key)."""
    provider = _extract_provider(model)
    api_key = _resolve_api_key(provider)
    if not api_key:
        key_name = _PROVIDER_TO_KEY_NAME.get(provider, provider).upper()
        raise ValueError(
            f"API key for {key_name} is not configured. "
            f"Please add your API_KEY_{key_name} in Settings."
        )
    return provider, api_key


# ---------------------------------------------------------------------------
# FAL.ai direct REST API
# ---------------------------------------------------------------------------

_FAL_SIZE_MAP: dict[str, str] = {
    "1024x1024": "square_hd",
    "1024x1792": "portrait_16_9",
    "1792x1024": "landscape_16_9",
    "512x512": "square",
}

_FAL_API_BASE = "https://fal.run"
_FAL_MODELS_API = "https://api.fal.ai/v1/models"

# Categories of FAL models relevant for image generation.
_FAL_IMAGE_CATEGORIES = ("text-to-image",)


def fetch_fal_models(api_key: str | None = None) -> list[dict]:
    """Fetch available image generation models from FAL.ai's model discovery API.

    Calls GET https://api.fal.ai/v1/models?category=text-to-image and returns
    them in the same format as IMAGE_MODELS entries.

    Args:
        api_key: Optional FAL API key (gives higher rate limits).

    Returns:
        List of model dicts with keys: id, name, provider, method.
    """
    models: list[dict] = []

    for category in _FAL_IMAGE_CATEGORIES:
        cursor: str | None = None
        while True:
            url = f"{_FAL_MODELS_API}?category={category}&limit=100"
            if cursor:
                url += f"&cursor={cursor}"

            headers: dict[str, str] = {}
            if api_key:
                headers["Authorization"] = f"Key {api_key}"

            req = Request(url, headers=headers, method="GET")
            try:
                with urlopen(req, timeout=30) as resp:
                    data = json.loads(resp.read())
            except Exception as e:
                log.warning("Failed to fetch FAL models: %s", e)
                break

            for m in data.get("models", []):
                endpoint_id = m.get("endpoint_id", "")
                meta = m.get("metadata", {})
                display_name = meta.get("display_name", endpoint_id)
                status = meta.get("status", "active")

                if status != "active" or not endpoint_id:
                    continue

                models.append({
                    "id": f"fal/{endpoint_id}",
                    "name": f"{display_name} (FAL)",
                    "provider": "fal",
                    "method": "image_generation",
                })

            if data.get("has_more") and data.get("next_cursor"):
                cursor = data["next_cursor"]
            else:
                break

    return models


def _fal_model_endpoint(model: str) -> str:
    """Extract the FAL model endpoint from a prefixed model string.

    'fal/fal-ai/flux/dev' -> 'fal-ai/flux/dev'
    """
    return model.split("/", 1)[1] if "/" in model else model


def _fal_request(endpoint: str, body: dict, api_key: str) -> dict:
    """Call a FAL.ai endpoint synchronously. Returns parsed JSON response."""
    url = f"{_FAL_API_BASE}/{endpoint}"
    data = json.dumps(body).encode("utf-8")

    req = Request(
        url,
        data=data,
        headers={
            "Authorization": f"Key {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    with urlopen(req, timeout=120) as resp:
        return json.loads(resp.read())


def _download_to_b64(url: str) -> str | None:
    """Download a URL and return its content as base64."""
    try:
        with urlopen(url, timeout=60) as resp:
            return base64.b64encode(resp.read()).decode("ascii")
    except Exception as e:
        log.warning("Failed to download FAL image from %s: %s", url, e)
        return None


def _extract_images_from_fal_response(response: dict) -> list[dict]:
    """Extract images from a FAL response, downloading URLs to b64."""
    results = []
    for img in response.get("images", []):
        img_url = img.get("url", "")
        b64 = _download_to_b64(img_url) if img_url else None
        results.append({
            "b64_json": b64,
            "url": img_url,
            "revised_prompt": None,
        })
    return results


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------

async def generate_image(
    prompt: str,
    model: str = "gemini/gemini-3.1-flash-image-preview",
    size: str = "1024x1024",
    n: int = 1,
    **kwargs,
) -> list[dict]:
    """Generate images from a text prompt.

    Gemini models call Google AI Studio REST API directly.
    OpenAI/DALL-E models use LiteLLM's aimage_generation.

    Returns:
        List of dicts with keys: b64_json, url, revised_prompt.
    """
    provider, api_key = _require_api_key(model)

    if _is_gemini(model):
        return await _generate_gemini(prompt, model, api_key)
    elif _is_fal(model):
        return await _generate_fal(prompt, model, size, n, api_key)
    else:
        return await _generate_openai(prompt, model, size, n, api_key, **kwargs)


async def _generate_gemini(prompt: str, model: str, api_key: str) -> list[dict]:
    """Generate image via Google AI Studio REST API."""
    parts = [{"text": f"Generate an image: {prompt}"}]
    response = await asyncio.to_thread(
        _gemini_generate_content, _bare_model(model), parts, api_key,
    )

    log.info("Gemini generate response keys: %s", list(response.keys()))

    results = _extract_images_from_gemini_response(response)
    if not results:
        # Check for error or text-only response
        error = response.get("error", {})
        if error:
            raise RuntimeError(f"Gemini API error: {error.get('message', error)}")
        raise RuntimeError(
            f"Image generation returned no images. Response: {json.dumps(response)[:500]}"
        )
    return results


async def _generate_fal(
    prompt: str, model: str, size: str, n: int, api_key: str,
) -> list[dict]:
    """Generate image via FAL.ai REST API."""
    endpoint = _fal_model_endpoint(model)
    body: dict = {
        "prompt": prompt,
        "image_size": _FAL_SIZE_MAP.get(size, "square_hd"),
        "num_images": n,
    }

    response = await asyncio.to_thread(_fal_request, endpoint, body, api_key)
    log.info("FAL generate response keys: %s", list(response.keys()))

    results = _extract_images_from_fal_response(response)
    if not results:
        raise RuntimeError(
            f"FAL image generation returned no images. Response: {json.dumps(response)[:500]}"
        )
    return results


async def _generate_openai(prompt, model, size, n, api_key, **kwargs):
    """Generate image using LiteLLM aimage_generation (OpenAI/DALL-E)."""
    litellm = _get_litellm()
    response = await litellm.aimage_generation(
        model=model,
        prompt=prompt,
        size=size,
        n=n,
        response_format="b64_json",
        drop_params=True,
        api_key=api_key,
        **kwargs,
    )

    data = getattr(response, "data", None) or []
    if not data:
        raise RuntimeError(f"Image generation returned no results. Raw response: {response}")

    results = []
    for item in data:
        b64 = getattr(item, "b64_json", None)
        url = getattr(item, "url", None)

        if not b64 and url:
            try:
                with urlopen(url) as resp:
                    b64 = base64.b64encode(resp.read()).decode("ascii")
            except Exception as e:
                log.warning("Failed to download image from URL %s: %s", url, e)

        results.append({
            "b64_json": b64,
            "url": url,
            "revised_prompt": getattr(item, "revised_prompt", None),
        })

    return results


# ---------------------------------------------------------------------------
# Editing
# ---------------------------------------------------------------------------

async def edit_image(
    image_b64: str,
    prompt: str,
    mask_b64: str | None = None,
    model: str = "gemini/gemini-3.1-flash-image-preview",
    **kwargs,
) -> list[dict]:
    """Edit an image.

    For Gemini: calls Google AI Studio REST API with the source image +
    edit instructions.  Gemini uses semantic masking (describe what to
    change in words) — no pixel mask needed.

    For non-Gemini: falls back to LiteLLM acompletion with image + mask
    as content parts (text-only response).

    Returns:
        List of dicts with keys: b64_json, url, revised_prompt.
    """
    provider, api_key = _require_api_key(model)

    if _is_gemini(model):
        return await _edit_gemini(image_b64, prompt, model, api_key, mask_b64)
    elif _is_fal(model):
        return await _edit_fal(image_b64, prompt, model, api_key)
    else:
        return await _edit_fallback(image_b64, prompt, mask_b64, model, api_key, **kwargs)


async def _edit_gemini(
    image_b64: str, prompt: str, model: str, api_key: str,
    mask_b64: str | None = None,
) -> list[dict]:
    """Edit image via Google AI Studio REST API.

    If mask_b64 is provided, it is sent as a second image with instructions
    telling Gemini to focus edits on the masked (red-highlighted) areas.
    This leverages Gemini's multimodal understanding of visual masks.
    """
    parts = [
        {
            "inlineData": {
                "mimeType": "image/png",
                "data": image_b64,
            },
        },
    ]

    if mask_b64:
        parts.append({
            "inlineData": {
                "mimeType": "image/png",
                "data": mask_b64,
            },
        })
        parts.append({
            "text": (
                "The first image is the source image. The second image is a mask "
                "where red-highlighted areas indicate the regions to edit. "
                "Only modify the masked areas according to these instructions, "
                "keeping everything else unchanged: " + prompt
            ),
        })
    else:
        parts.append({"text": prompt})

    response = await asyncio.to_thread(
        _gemini_generate_content, _bare_model(model), parts, api_key,
    )

    log.info("Gemini edit response keys: %s", list(response.keys()))

    results = _extract_images_from_gemini_response(response)
    if not results:
        error = response.get("error", {})
        if error:
            raise RuntimeError(f"Gemini API error: {error.get('message', error)}")
        raise RuntimeError(
            f"Image editing returned no images. Response: {json.dumps(response)[:500]}"
        )
    return results


async def _edit_fal(
    image_b64: str, prompt: str, model: str, api_key: str,
) -> list[dict]:
    """Edit image via FAL.ai image-to-image endpoint.

    Uses fal-ai/flux/dev/image-to-image regardless of which FAL model was
    selected, since FLUX image-to-image is the only FAL editing endpoint.
    Mask is not supported (FLUX doesn't do inpainting), so we rely on the
    prompt to describe what to change.
    """
    endpoint = "fal-ai/flux/dev/image-to-image"
    body: dict = {
        "image_url": f"data:image/png;base64,{image_b64}",
        "prompt": prompt,
        "strength": 0.75,
    }

    response = await asyncio.to_thread(_fal_request, endpoint, body, api_key)
    log.info("FAL edit response keys: %s", list(response.keys()))

    results = _extract_images_from_fal_response(response)
    if not results:
        raise RuntimeError(
            f"FAL image editing returned no images. Response: {json.dumps(response)[:500]}"
        )
    return results


async def _edit_fallback(image_b64, prompt, mask_b64, model, api_key, **kwargs):
    """Fallback edit for non-Gemini models (text-only response)."""
    litellm = _get_litellm()
    content_parts: list[dict] = [
        {
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{image_b64}"},
        },
    ]
    if mask_b64:
        content_parts.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{mask_b64}"},
        })
        content_parts.append({
            "type": "text",
            "text": f"The second image is a mask highlighting areas to edit. Instructions: {prompt}",
        })
    else:
        content_parts.append({
            "type": "text",
            "text": f"Edit this image according to these instructions: {prompt}",
        })

    response = await litellm.acompletion(
        model=model,
        messages=[{"role": "user", "content": content_parts}],
        drop_params=True,
        api_key=api_key,
        **kwargs,
    )

    return [
        {
            "b64_json": None,
            "url": None,
            "revised_prompt": choice.message.content,
        }
        for choice in response.choices
    ]


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def get_plugin_config() -> dict:
    """Load the Design Studio plugin configuration."""
    try:
        from helpers import plugins
        config = plugins.get_plugin_config("a0_design_studio")
        if config:
            return config
    except (ImportError, Exception):
        pass

    return {
        "image_generation_model": "gemini/gemini-3.1-flash-image-preview",
        "image_edit_model": "gemini/gemini-3.1-flash-image-preview",
        "default_size": "1024x1024",
        "default_count": 1,
        "gallery_path": "images",
    }
