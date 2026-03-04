"""Tests for a0_design_studio image provider layer."""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

PLUGIN_ROOT = Path(__file__).parent.parent / "usr" / "plugins" / "a0_design_studio"


@pytest.fixture(autouse=True)
def _plugin_path():
    """Add plugin root to sys.path and ensure litellm is mockable.

    If litellm is not installed in the test environment we inject a MagicMock
    into sys.modules so that ``import litellm`` inside image_providers succeeds.
    """
    root = str(PLUGIN_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)

    # Ensure litellm is importable (may not be installed in CI / test env)
    litellm_stub = None
    if "litellm" not in sys.modules:
        litellm_stub = MagicMock()
        sys.modules["litellm"] = litellm_stub

    yield

    # Tear down: remove plugin path and cached helper modules
    if root in sys.path:
        sys.path.remove(root)
    for key in list(sys.modules.keys()):
        if key.startswith("helpers"):
            del sys.modules[key]
    if litellm_stub is not None and sys.modules.get("litellm") is litellm_stub:
        del sys.modules["litellm"]


# ---------------------------------------------------------------------------
# generate_image tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_returns_image_list():
    """generate_image returns a list of dicts with b64_json key."""
    from helpers.image_providers import generate_image

    mock_data_item = MagicMock()
    mock_data_item.b64_json = "base64encodeddata"
    mock_data_item.url = "https://example.com/img.png"
    mock_data_item.revised_prompt = "a revised prompt"

    mock_response = MagicMock()
    mock_response.data = [mock_data_item]

    with patch("helpers.image_providers.litellm") as mock_litellm:
        mock_litellm.aimage_generation = AsyncMock(return_value=mock_response)
        result = await generate_image("a cat sitting on a mat")

    assert isinstance(result, list)
    assert len(result) == 1
    assert "b64_json" in result[0]
    assert result[0]["b64_json"] == "base64encodeddata"
    assert result[0]["url"] == "https://example.com/img.png"
    assert result[0]["revised_prompt"] == "a revised prompt"


@pytest.mark.asyncio
async def test_generate_passes_size_and_n():
    """generate_image forwards size and n to litellm.image_generation."""
    from helpers.image_providers import generate_image

    mock_data_item = MagicMock()
    mock_data_item.b64_json = "data"
    mock_data_item.url = None
    mock_data_item.revised_prompt = None

    mock_response = MagicMock()
    mock_response.data = [mock_data_item]

    with patch("helpers.image_providers.litellm") as mock_litellm:
        mock_litellm.aimage_generation = AsyncMock(return_value=mock_response)
        await generate_image(
            "a dog", model="openai/dall-e-3", size="512x512", n=4
        )

        mock_litellm.aimage_generation.assert_called_once_with(
            model="openai/dall-e-3",
            prompt="a dog",
            size="512x512",
            n=4,
            response_format="b64_json",
            drop_params=True,
        )


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

    with patch("helpers.image_providers.litellm") as mock_litellm:
        mock_litellm.acompletion = AsyncMock(return_value=mock_response)
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

    with patch("helpers.image_providers.litellm") as mock_litellm:
        mock_litellm.acompletion = AsyncMock(return_value=mock_response)
        await edit_image(
            image_b64="imagedata",
            prompt="remove the background",
            mask_b64="maskdata",
        )

        call_args = mock_litellm.acompletion.call_args
        messages = call_args.kwargs.get("messages", call_args[1].get("messages", []))

        # Find the user message
        user_messages = [m for m in messages if m["role"] == "user"]
        assert len(user_messages) == 1

        user_content = user_messages[0]["content"]
        # Count image_url parts
        image_parts = [
            p for p in user_content
            if isinstance(p, dict) and p.get("type") == "image_url"
        ]
        assert len(image_parts) >= 2, (
            f"Expected at least 2 image_url parts when mask provided, got {len(image_parts)}"
        )
