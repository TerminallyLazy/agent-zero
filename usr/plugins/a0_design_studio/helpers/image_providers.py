"""Image provider layer for A0 Design Studio.

Routes image generation and editing requests through LiteLLM,
which already handles multi-provider routing (OpenAI, Google, etc.).
"""

from __future__ import annotations

import litellm

litellm.drop_params = True

async def generate_image(
    prompt: str,
    model: str = "openai/dall-e-3",
    size: str = "1024x1024",
    n: int = 1,
    **kwargs,
) -> list[dict]:
    """Generate images from a text prompt via LiteLLM.

    Calls litellm.image_generation and returns a normalised list of dicts.

    Args:
        prompt: Text description of the desired image.
        model: LiteLLM model identifier (e.g. "openai/dall-e-3").
        size: Image dimensions as "WxH" string.
        n: Number of images to generate.
        **kwargs: Extra arguments forwarded to litellm.image_generation.

    Returns:
        List of dicts, each with keys: b64_json, url, revised_prompt.
    """
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
    model: str = "google/gemini-2.0-flash",
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
        "image_generation_model": "openai/dall-e-3",
        "image_edit_model": "google/gemini-2.0-flash",
        "default_size": "1024x1024",
        "default_count": 1,
        "gallery_path": "images",
    }
