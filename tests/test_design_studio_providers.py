"""Tests for a0_design_studio image provider layer."""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

PLUGIN_ROOT = Path(__file__).parent.parent / "usr" / "plugins" / "a0_design_studio"

FAKE_API_KEY = "test-key-12345"


@pytest.fixture(autouse=True)
def _plugin_path():
    """Add plugin root to sys.path and ensure litellm is mockable."""
    root = str(PLUGIN_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)

    litellm_stub = None
    if "litellm" not in sys.modules:
        litellm_stub = MagicMock()
        sys.modules["litellm"] = litellm_stub

    yield

    if root in sys.path:
        sys.path.remove(root)
    for key in list(sys.modules.keys()):
        if key.startswith("helpers"):
            del sys.modules[key]
    if litellm_stub is not None and sys.modules.get("litellm") is litellm_stub:
        del sys.modules["litellm"]


# ---------------------------------------------------------------------------
# generate_image tests — completion path (Gemini default)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_gemini_returns_image_list():
    """generate_image via completion returns b64_json extracted from data URL."""
    from helpers.image_providers import generate_image

    mock_message = MagicMock()
    mock_message.images = [
        {"image_url": {"url": "data:image/png;base64,base64encodeddata"}}
    ]
    mock_message.content = "Here is your image"

    mock_choice = MagicMock()
    mock_choice.message = mock_message

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    mock_litellm = MagicMock()
    mock_litellm.acompletion = AsyncMock(return_value=mock_response)

    with (
        patch("helpers.image_providers._get_litellm", return_value=mock_litellm),
        patch("helpers.image_providers._resolve_api_key", return_value=FAKE_API_KEY),
    ):
        result = await generate_image("a cat sitting on a mat")

    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["b64_json"] == "base64encodeddata"


# ---------------------------------------------------------------------------
# generate_image tests — image_generation path (OpenAI/DALL-E)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_dalle_passes_size_and_n():
    """generate_image via image_generation forwards size and n."""
    from helpers.image_providers import generate_image

    mock_data_item = MagicMock()
    mock_data_item.b64_json = "data"
    mock_data_item.url = None
    mock_data_item.revised_prompt = None

    mock_response = MagicMock()
    mock_response.data = [mock_data_item]

    mock_litellm = MagicMock()
    mock_litellm.aimage_generation = AsyncMock(return_value=mock_response)

    with (
        patch("helpers.image_providers._get_litellm", return_value=mock_litellm),
        patch("helpers.image_providers._resolve_api_key", return_value=FAKE_API_KEY),
    ):
        await generate_image(
            "a dog", model="dall-e-3", size="512x512", n=4
        )

        mock_litellm.aimage_generation.assert_called_once_with(
            model="dall-e-3",
            prompt="a dog",
            size="512x512",
            n=4,
            response_format="b64_json",
            drop_params=True,
            api_key=FAKE_API_KEY,
        )


@pytest.mark.asyncio
async def test_generate_raises_on_missing_key():
    """generate_image raises ValueError when API key is not configured."""
    from helpers.image_providers import generate_image

    with (
        patch("helpers.image_providers._get_litellm", return_value=MagicMock()),
        patch("helpers.image_providers._resolve_api_key", return_value=None),
    ):
        with pytest.raises(ValueError, match="API key for GOOGLE is not configured"):
            await generate_image("test prompt")


# ---------------------------------------------------------------------------
# edit_image tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_edit_returns_image_list():
    """edit_image returns a list of dicts with content key."""
    from helpers.image_providers import edit_image

    mock_choice = MagicMock()
    mock_choice.message.content = "Here is the edited description."

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    mock_litellm = MagicMock()
    mock_litellm.acompletion = AsyncMock(return_value=mock_response)

    with (
        patch("helpers.image_providers._get_litellm", return_value=mock_litellm),
        patch("helpers.image_providers._resolve_api_key", return_value=FAKE_API_KEY),
    ):
        result = await edit_image(
            image_b64="imagedata", prompt="make the sky blue"
        )

    assert isinstance(result, list)
    assert len(result) == 1
    assert "content" in result[0]
    assert result[0]["content"] == "Here is the edited description."
    assert "revised_prompt" in result[0]


@pytest.mark.asyncio
async def test_edit_includes_mask_when_provided():
    """When mask_b64 is provided, user message includes 2+ image_url parts."""
    from helpers.image_providers import edit_image

    mock_choice = MagicMock()
    mock_choice.message.content = "Edited."

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    mock_litellm = MagicMock()
    mock_litellm.acompletion = AsyncMock(return_value=mock_response)

    with (
        patch("helpers.image_providers._get_litellm", return_value=mock_litellm),
        patch("helpers.image_providers._resolve_api_key", return_value=FAKE_API_KEY),
    ):
        await edit_image(
            image_b64="imagedata",
            prompt="remove the background",
            mask_b64="maskdata",
        )

        call_args = mock_litellm.acompletion.call_args
        messages = call_args.kwargs.get("messages", call_args[1].get("messages", []))

        user_messages = [m for m in messages if m["role"] == "user"]
        assert len(user_messages) == 1

        user_content = user_messages[0]["content"]
        image_parts = [
            p for p in user_content
            if isinstance(p, dict) and p.get("type") == "image_url"
        ]
        assert len(image_parts) >= 2, (
            f"Expected at least 2 image_url parts when mask provided, got {len(image_parts)}"
        )
