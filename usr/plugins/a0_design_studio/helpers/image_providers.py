"""Image provider layer for A0 Design Studio.

Routes image generation and editing requests through LiteLLM,
which already handles multi-provider routing (OpenAI, Google, etc.).
Uses Agent Zero's API key management so keys configured in Settings work.
"""

from __future__ import annotations


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
IMAGE_MODELS: list[dict] = [
    {"id": "gemini/imagen-4.0-generate-001", "name": "Gemini Imagen 4.0", "provider": "google"},
    {"id": "dall-e-3", "name": "DALL-E 3", "provider": "openai"},
    {"id": "dall-e-2", "name": "DALL-E 2", "provider": "openai"},
    {"id": "openai/gpt-image-1", "name": "GPT Image 1", "provider": "openai"},
]


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


def check_api_key(provider: str) -> bool:
    """Return True if the API key for the given provider is configured."""
    return _resolve_api_key(provider) is not None


async def generate_image(
    prompt: str,
    model: str = "gemini/imagen-4.0-generate-001",
    size: str = "1024x1024",
    n: int = 1,
    **kwargs,
) -> list[dict]:
    """Generate images from a text prompt via LiteLLM.

    Args:
        prompt: Text description of the desired image.
        model: LiteLLM model identifier (e.g. "gemini/imagen-4.0-generate-001").
        size: Image dimensions as "WxH" string.
        n: Number of images to generate.
        **kwargs: Extra arguments forwarded to litellm.aimage_generation.

    Returns:
        List of dicts, each with keys: b64_json, url, revised_prompt.

    Raises:
        ValueError: If the required API key is not configured.
    """
    litellm = _get_litellm()

    # Extract provider prefix for API key lookup (e.g. "gemini" from "gemini/imagen-...")
    provider = model.split("/")[0] if "/" in model else model
    api_key = _resolve_api_key(provider)
    if not api_key:
        key_name = _PROVIDER_TO_KEY_NAME.get(provider, provider).upper()
        raise ValueError(
            f"API key for {key_name} is not configured. "
            f"Please add your API_KEY_{key_name} in Settings."
        )
    kwargs.setdefault("api_key", api_key)

    response = await litellm.aimage_generation(
        model=model,
        prompt=prompt,
        size=size,
        n=n,
        response_format="b64_json",
        drop_params=True,
        **kwargs,
    )

    return [
        {
            "b64_json": getattr(item, "b64_json", None),
            "url": getattr(item, "url", None),
            "revised_prompt": getattr(item, "revised_prompt", None),
        }
        for item in response.data
    ]


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
    provider = model.split("/")[0] if "/" in model else model
    api_key = _resolve_api_key(provider)
    if api_key:
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
        "image_generation_model": "gemini/imagen-4.0-generate-001",
        "image_edit_model": "gemini/gemini-2.0-flash",
        "default_size": "1024x1024",
        "default_count": 1,
        "gallery_path": "images",
    }
