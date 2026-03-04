"""Image provider layer for A0 Design Studio.

Routes image generation and editing requests through LiteLLM,
which already handles multi-provider routing (OpenAI, Google, etc.).
Uses Agent Zero's API key management so keys configured in Settings work.
"""

from __future__ import annotations

import base64
import logging
import os
from urllib.request import urlopen

log = logging.getLogger("a0_design_studio")


def _get_litellm():
    """Lazy-import litellm to avoid Vertex credential probes at startup."""
    import litellm
    litellm.drop_params = True
    return litellm


# Map LiteLLM provider prefixes to Agent Zero API_KEY_<NAME> identifiers.
# Agent Zero stores keys as API_KEY_GOOGLE, API_KEY_OPENAI, etc.
_PROVIDER_TO_KEY_NAME: dict[str, str] = {
    "gemini": "google",
    "google": "google",
    "openai": "openai",
    "dall-e-2": "openai",
    "dall-e-3": "openai",
    "openrouter": "openrouter",
    "azure": "azure",
    "bedrock": "bedrock",
}

# Available image generation models shown in the UI dropdown.
# "method" indicates whether the model uses the chat completion endpoint
# (with modalities=["image","text"]) or the dedicated image_generation endpoint.
IMAGE_MODELS: list[dict] = [
    {"id": "gemini/gemini-2.0-flash-exp-image-generation", "name": "Gemini Flash Image", "provider": "google", "method": "completion"},
    {"id": "dall-e-3", "name": "DALL-E 3", "provider": "openai", "method": "image_generation"},
    {"id": "dall-e-2", "name": "DALL-E 2", "provider": "openai", "method": "image_generation"},
    {"id": "openai/gpt-image-1", "name": "GPT Image 1", "provider": "openai", "method": "image_generation"},
]

# Models that use acompletion + modalities instead of aimage_generation.
_COMPLETION_IMAGE_MODELS: set[str] = {
    m["id"] for m in IMAGE_MODELS if m.get("method") == "completion"
}


def _extract_provider(model: str) -> str:
    """Extract the provider name from a model string for key lookup.

    Handles: "gemini/model" -> "gemini", "dall-e-3" -> "dall-e-3",
    and bare names like "gemini-2.0-flash" -> "gemini".
    """
    if "/" in model:
        return model.split("/")[0]
    # Check static map first (dall-e-3, etc.)
    if model in _PROVIDER_TO_KEY_NAME:
        return model
    # Bare model names starting with a known prefix
    for prefix in ("gemini", "gpt", "claude"):
        if model.startswith(prefix):
            return prefix
    return model


def _resolve_api_key(provider: str) -> str | None:
    """Look up the API key for a provider using Agent Zero's key management
    (env vars: API_KEY_<PROVIDER>, <PROVIDER>_API_KEY, <PROVIDER>_API_TOKEN)."""
    key_name = _PROVIDER_TO_KEY_NAME.get(provider, provider)
    try:
        from models import get_api_key
        key = get_api_key(key_name)
        if key and key not in ("None", "NA"):
            return key
    except (ImportError, Exception):
        pass
    return None


# LiteLLM checks specific env vars per provider internally, often ignoring
# the api_key kwarg. This maps providers to the env var LiteLLM expects.
_PROVIDER_ENV_VAR: dict[str, str] = {
    "gemini": "GEMINI_API_KEY",
    "google": "GEMINI_API_KEY",
    "openai": "OPENAI_API_KEY",
}


def _inject_env_key(provider: str, api_key: str) -> None:
    """Set the env var that LiteLLM actually reads for this provider.

    LiteLLM's Gemini handler checks GEMINI_API_KEY directly rather than
    using the api_key kwarg. This bridges Agent Zero's API_KEY_GOOGLE
    to what LiteLLM expects."""
    env_var = _PROVIDER_ENV_VAR.get(provider)
    if env_var and not os.environ.get(env_var):
        os.environ[env_var] = api_key


def check_api_key(provider: str) -> bool:
    """Return True if the API key for the given provider is configured."""
    return _resolve_api_key(provider) is not None


async def generate_image(
    prompt: str,
    model: str = "gemini/gemini-2.0-flash-exp-image-generation",
    size: str = "1024x1024",
    n: int = 1,
    **kwargs,
) -> list[dict]:
    """Generate images from a text prompt via LiteLLM.

    Gemini models use acompletion with modalities=["image","text"].
    OpenAI/DALL-E models use aimage_generation.

    Returns:
        List of dicts, each with keys: b64_json, url, revised_prompt.

    Raises:
        ValueError: If the required API key is not configured.
    """
    litellm = _get_litellm()

    provider = _extract_provider(model)
    api_key = _resolve_api_key(provider)
    if not api_key:
        key_name = _PROVIDER_TO_KEY_NAME.get(provider, provider).upper()
        raise ValueError(
            f"API key for {key_name} is not configured. "
            f"Please add your API_KEY_{key_name} in Settings."
        )
    _inject_env_key(provider, api_key)
    kwargs.setdefault("api_key", api_key)

    if model in _COMPLETION_IMAGE_MODELS:
        return await _generate_via_completion(litellm, prompt, model, **kwargs)
    else:
        return await _generate_via_image_api(litellm, prompt, model, size, n, **kwargs)


async def _generate_via_completion(litellm, prompt, model, **kwargs):
    """Generate image using acompletion + modalities (Gemini models)."""
    response = await litellm.acompletion(
        model=model,
        messages=[{"role": "user", "content": f"Generate an image: {prompt}"}],
        modalities=["image", "text"],
        drop_params=True,
        **kwargs,
    )

    log.info("completion image response: %s", response)

    results = []
    for choice in response.choices:
        images = getattr(choice.message, "images", None) or []
        for img in images:
            # images are like {"image_url": {"url": "data:image/png;base64,..."}}
            data_url = img.get("image_url", {}).get("url", "")
            b64 = None
            if data_url.startswith("data:"):
                # Strip the data:image/png;base64, prefix
                b64 = data_url.split(",", 1)[1] if "," in data_url else None
            results.append({
                "b64_json": b64,
                "url": data_url if not b64 else None,
                "revised_prompt": getattr(choice.message, "content", None),
            })

    if not results:
        # Check if there's text content that might explain the refusal
        text = getattr(response.choices[0].message, "content", "") if response.choices else ""
        raise RuntimeError(
            f"Image generation returned no images. "
            f"Model response: {text or response}"
        )

    return results


async def _generate_via_image_api(litellm, prompt, model, size, n, **kwargs):
    """Generate image using aimage_generation (OpenAI/DALL-E models)."""
    response = await litellm.aimage_generation(
        model=model,
        prompt=prompt,
        size=size,
        n=n,
        response_format="b64_json",
        drop_params=True,
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


async def edit_image(
    image_b64: str,
    prompt: str,
    mask_b64: str | None = None,
    model: str = "gemini/gemini-2.0-flash",
    **kwargs,
) -> list[dict]:
    """Edit an image using a vision-capable chat model.

    Sends the source image (and optional mask) alongside editing instructions
    to a vision model via litellm.acompletion().

    Args:
        image_b64: Base64-encoded source image (PNG).
        prompt: Editing instructions in natural language.
        mask_b64: Optional base64-encoded mask image highlighting edit regions.
        model: LiteLLM model identifier for a vision-capable model.
        **kwargs: Extra arguments forwarded to litellm.acompletion.

    Returns:
        List of dicts, each with keys: content, revised_prompt.
    """
    litellm = _get_litellm()
    provider = _extract_provider(model)
    api_key = _resolve_api_key(provider)
    if not api_key:
        key_name = _PROVIDER_TO_KEY_NAME.get(provider, provider).upper()
        raise ValueError(
            f"API key for {key_name} is not configured. "
            f"Please add your API_KEY_{key_name} in Settings."
        )
    _inject_env_key(provider, api_key)
    kwargs.setdefault("api_key", api_key)

    content_parts: list[dict] = [
        {
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{image_b64}"},
        },
    ]

    if mask_b64:
        content_parts.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{mask_b64}"},
            }
        )

    content_parts.append(
        {
            "type": "text",
            "text": f"Edit this image according to these instructions: {prompt}",
        }
    )

    if mask_b64:
        content_parts.append(
            {
                "type": "text",
                "text": "The second image is a mask where highlighted regions indicate areas to edit.",
            }
        )

    messages = [
        {
            "role": "system",
            "content": "You are an image editing assistant. Follow the user's editing instructions precisely.",
        },
        {
            "role": "user",
            "content": content_parts,
        },
    ]

    response = await litellm.acompletion(
        model=model,
        messages=messages,
        **kwargs,
    )

    return [
        {
            "content": choice.message.content,
            "revised_prompt": prompt,
        }
        for choice in response.choices
    ]


def get_plugin_config() -> dict:
    """Load the Design Studio plugin configuration.

    Attempts to use the Agent Zero plugin system. Falls back to a default
    configuration dict if the plugin system is unavailable.

    Returns:
        Configuration dict with keys like image_generation_model,
        image_edit_model, default_size, default_count, gallery_path.
    """
    try:
        from python.helpers import plugins

        config = plugins.get_plugin_config("a0_design_studio")
        if config:
            return config
    except (ImportError, Exception):
        pass

    return {
        "image_generation_model": "gemini/gemini-2.0-flash-exp-image-generation",
        "image_edit_model": "gemini/gemini-2.0-flash",
        "default_size": "1024x1024",
        "default_count": 1,
        "gallery_path": "images",
    }
