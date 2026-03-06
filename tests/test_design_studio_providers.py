"""Tests for a0_design_studio image provider layer."""

import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import json

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


def _make_gemini_response(b64_data="base64encodeddata", text=None):
    """Build a mock Google AI Studio generateContent JSON response."""
    parts = [{"inlineData": {"mimeType": "image/png", "data": b64_data}}]
    if text:
        parts.insert(0, {"text": text})
    return {
        "candidates": [{"content": {"parts": parts}}],
    }


# ---------------------------------------------------------------------------
# generate_image — Gemini path (direct REST API)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_gemini_returns_image_list():
    """generate_image for Gemini calls REST API and returns b64_json."""
    from helpers.image_providers import generate_image

    gemini_resp = _make_gemini_response("base64encodeddata", "Here is your image")

    with (
        patch("helpers.image_providers._resolve_api_key", return_value=FAKE_API_KEY),
        patch("helpers.image_providers._gemini_generate_content", return_value=gemini_resp),
    ):
        result = await generate_image("a cat sitting on a mat")

    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["b64_json"] == "base64encodeddata"
    assert result[0]["revised_prompt"] == "Here is your image"


@pytest.mark.asyncio
async def test_generate_gemini_calls_correct_endpoint():
    """generate_image for Gemini strips provider prefix and passes API key."""
    from helpers.image_providers import generate_image

    gemini_resp = _make_gemini_response()

    with (
        patch("helpers.image_providers._resolve_api_key", return_value=FAKE_API_KEY),
        patch("helpers.image_providers._gemini_generate_content", return_value=gemini_resp) as mock_call,
    ):
        await generate_image("test", model="gemini/gemini-3.1-flash-image-preview")

    mock_call.assert_called_once()
    args = mock_call.call_args
    assert args[0][0] == "gemini-3.1-flash-image-preview"  # bare model name
    assert args[0][2] == FAKE_API_KEY  # api key


# ---------------------------------------------------------------------------
# generate_image — OpenAI/DALL-E path (LiteLLM)
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

    with patch("helpers.image_providers._resolve_api_key", return_value=None):
        with pytest.raises(ValueError, match="API key for GOOGLE is not configured"):
            await generate_image("test prompt")


# ---------------------------------------------------------------------------
# edit_image — Gemini path (direct REST API)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_edit_gemini_returns_edited_image():
    """edit_image for Gemini returns b64_json from the edited image."""
    from helpers.image_providers import edit_image

    gemini_resp = _make_gemini_response("editedimagedata", "I changed the sky")

    with (
        patch("helpers.image_providers._resolve_api_key", return_value=FAKE_API_KEY),
        patch("helpers.image_providers._gemini_generate_content", return_value=gemini_resp),
    ):
        result = await edit_image(
            image_b64="imagedata", prompt="make the sky blue"
        )

    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["b64_json"] == "editedimagedata"
    assert result[0]["revised_prompt"] == "I changed the sky"


@pytest.mark.asyncio
async def test_edit_gemini_sends_image_and_prompt():
    """edit_image for Gemini sends inlineData + text parts."""
    from helpers.image_providers import edit_image

    gemini_resp = _make_gemini_response()

    with (
        patch("helpers.image_providers._resolve_api_key", return_value=FAKE_API_KEY),
        patch("helpers.image_providers._gemini_generate_content", return_value=gemini_resp) as mock_call,
    ):
        await edit_image(
            image_b64="imagedata",
            prompt="remove the background",
        )

    mock_call.assert_called_once()
    parts = mock_call.call_args[0][1]

    # First part should be the image
    assert "inlineData" in parts[0]
    assert parts[0]["inlineData"]["data"] == "imagedata"

    # Second part should be the text prompt (no mask)
    assert parts[1]["text"] == "remove the background"


@pytest.mark.asyncio
async def test_edit_gemini_with_mask_sends_three_parts():
    """edit_image with mask sends source image + mask image + contextual prompt."""
    from helpers.image_providers import edit_image

    gemini_resp = _make_gemini_response("maskedresult")

    with (
        patch("helpers.image_providers._resolve_api_key", return_value=FAKE_API_KEY),
        patch("helpers.image_providers._gemini_generate_content", return_value=gemini_resp) as mock_call,
    ):
        await edit_image(
            image_b64="sourcedata",
            prompt="replace with grass",
            mask_b64="maskdata",
        )

    mock_call.assert_called_once()
    parts = mock_call.call_args[0][1]

    # 3 parts: source image, mask image, contextual prompt
    assert len(parts) == 3

    # First part: source image
    assert parts[0]["inlineData"]["data"] == "sourcedata"

    # Second part: mask image
    assert parts[1]["inlineData"]["data"] == "maskdata"

    # Third part: prompt wrapping mask instructions
    assert "red-highlighted areas" in parts[2]["text"]
    assert "replace with grass" in parts[2]["text"]


# ---------------------------------------------------------------------------
# generate_image — FAL path (direct REST API)
# ---------------------------------------------------------------------------


def _make_fal_response(urls=None):
    """Build a mock FAL API JSON response."""
    if urls is None:
        urls = ["https://fal.ai/result/img1.png"]
    return {"images": [{"url": u} for u in urls]}


@pytest.mark.asyncio
async def test_generate_fal_returns_image_list():
    """generate_image for FAL calls REST API and downloads images to b64."""
    from helpers.image_providers import generate_image

    fal_resp = _make_fal_response()

    with (
        patch("helpers.image_providers._resolve_api_key", return_value=FAKE_API_KEY),
        patch("helpers.image_providers._fal_request", return_value=fal_resp),
        patch("helpers.image_providers._download_to_b64", return_value="downloadedbase64"),
    ):
        result = await generate_image("a futuristic city", model="fal/fal-ai/flux/schnell")

    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["b64_json"] == "downloadedbase64"
    assert result[0]["url"] == "https://fal.ai/result/img1.png"


@pytest.mark.asyncio
async def test_generate_fal_calls_correct_endpoint():
    """generate_image for FAL strips fal/ prefix and sends correct body."""
    from helpers.image_providers import generate_image

    fal_resp = _make_fal_response()

    with (
        patch("helpers.image_providers._resolve_api_key", return_value=FAKE_API_KEY),
        patch("helpers.image_providers._fal_request", return_value=fal_resp) as mock_req,
        patch("helpers.image_providers._download_to_b64", return_value="b64data"),
    ):
        await generate_image(
            "test", model="fal/fal-ai/flux/dev", size="1792x1024", n=2,
        )

    mock_req.assert_called_once()
    endpoint, body, key = mock_req.call_args[0]
    assert endpoint == "fal-ai/flux/dev"
    assert body["prompt"] == "test"
    assert body["image_size"] == "landscape_16_9"
    assert body["num_images"] == 2
    assert key == FAKE_API_KEY


@pytest.mark.asyncio
async def test_edit_fal_sends_image_and_prompt():
    """edit_image for FAL sends image as data URI with prompt."""
    from helpers.image_providers import edit_image

    fal_resp = _make_fal_response()

    with (
        patch("helpers.image_providers._resolve_api_key", return_value=FAKE_API_KEY),
        patch("helpers.image_providers._fal_request", return_value=fal_resp) as mock_req,
        patch("helpers.image_providers._download_to_b64", return_value="editeddata"),
    ):
        result = await edit_image(
            image_b64="sourcedata",
            prompt="make it darker",
            model="fal/fal-ai/flux/dev",
        )

    mock_req.assert_called_once()
    endpoint, body, key = mock_req.call_args[0]
    assert endpoint == "fal-ai/flux/dev/image-to-image"
    assert body["image_url"] == "data:image/png;base64,sourcedata"
    assert body["prompt"] == "make it darker"
    assert body["strength"] == 0.75
    assert len(result) == 1
    assert result[0]["b64_json"] == "editeddata"


@pytest.mark.asyncio
async def test_fal_key_env_fallback():
    """_resolve_api_key falls back to FAL_KEY env var for fal provider."""
    from helpers.image_providers import _resolve_api_key

    # get_api_key is a lazy import inside _resolve_api_key, so we mock
    # models.get_api_key to simulate it returning nothing for "fal".
    mock_get_key = MagicMock(return_value=None)
    with (
        patch.dict("sys.modules", {"models": MagicMock(get_api_key=mock_get_key)}),
        patch("helpers.image_providers.get_plugin_config", return_value={"fal_api_key": ""}),
        patch.dict(os.environ, {"FAL_KEY": "my-fal-key"}),
    ):
        key = _resolve_api_key("fal")

    assert key == "my-fal-key"


@pytest.mark.asyncio
async def test_fal_key_plugin_config_fallback():
    """_resolve_api_key reads fal_api_key from plugin config."""
    from helpers.image_providers import _resolve_api_key

    mock_get_key = MagicMock(return_value=None)
    with (
        patch.dict("sys.modules", {"models": MagicMock(get_api_key=mock_get_key)}),
        patch("helpers.image_providers.get_plugin_config", return_value={"fal_api_key": "from-plugin-config"}),
    ):
        key = _resolve_api_key("fal")

    assert key == "from-plugin-config"


# ---------------------------------------------------------------------------
# fetch_fal_models — dynamic model discovery
# ---------------------------------------------------------------------------


def test_fetch_fal_models_parses_api_response():
    """fetch_fal_models returns model dicts from FAL API response."""
    from helpers.image_providers import fetch_fal_models

    fal_api_response = json.dumps({
        "models": [
            {
                "endpoint_id": "fal-ai/flux/schnell",
                "metadata": {
                    "display_name": "FLUX.1 Schnell",
                    "status": "active",
                    "category": "text-to-image",
                },
            },
            {
                "endpoint_id": "fal-ai/flux/dev",
                "metadata": {
                    "display_name": "FLUX.1 Dev",
                    "status": "active",
                    "category": "text-to-image",
                },
            },
            {
                "endpoint_id": "fal-ai/old-model",
                "metadata": {
                    "display_name": "Old Model",
                    "status": "deprecated",
                    "category": "text-to-image",
                },
            },
        ],
        "has_more": False,
        "next_cursor": None,
    }).encode("utf-8")

    mock_resp = MagicMock()
    mock_resp.read.return_value = fal_api_response
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("helpers.image_providers.urlopen", return_value=mock_resp):
        models = fetch_fal_models(api_key="test-key")

    # Should include 2 active models, skip the deprecated one
    assert len(models) == 2
    assert models[0]["id"] == "fal/fal-ai/flux/schnell"
    assert models[0]["name"] == "FLUX.1 Schnell (FAL)"
    assert models[0]["provider"] == "fal"
    assert models[1]["id"] == "fal/fal-ai/flux/dev"


def test_fetch_fal_models_handles_api_failure():
    """fetch_fal_models returns empty list on network error."""
    from helpers.image_providers import fetch_fal_models

    with patch("helpers.image_providers.urlopen", side_effect=Exception("Network error")):
        models = fetch_fal_models()

    assert models == []
