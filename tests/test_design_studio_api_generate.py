"""Tests for a0_design_studio image generation API handler."""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

PLUGIN_ROOT = str(
    Path(__file__).parent.parent / "usr" / "plugins" / "a0_design_studio"
)
PROJECT_ROOT = str(Path(__file__).parent.parent)


@pytest.fixture(autouse=True)
def _plugin_path():
    """Add plugin root and project root to sys.path so imports resolve.

    Stubs out litellm, flask, werkzeug and other heavy Agent Zero modules
    that are not needed for unit-testing the API handler.
    """
    paths_added: list[str] = []
    for p in (PLUGIN_ROOT, PROJECT_ROOT):
        if p not in sys.path:
            sys.path.insert(0, p)
            paths_added.append(p)

    # Track all stubs we inject so we can clean them up
    stubs_injected: dict[str, MagicMock] = {}

    # Stub modules that may not be installed in the test environment
    stub_modules = [
        "litellm",
        "flask",
        "werkzeug",
        "werkzeug.wrappers",
        "werkzeug.wrappers.response",
        "agent",
        "initialize",
        "python.helpers.print_style",
        "python.helpers.errors",
        "python.helpers.files",
        "python.helpers.cache",
        "python.helpers.plugins",
    ]
    for mod_name in stub_modules:
        if mod_name not in sys.modules:
            stub = MagicMock()
            sys.modules[mod_name] = stub
            stubs_injected[mod_name] = stub

    # Make flask stub provide necessary names for api.py imports
    flask_mod = sys.modules["flask"]
    if not hasattr(flask_mod, "Request") or isinstance(flask_mod.Request, MagicMock):
        flask_mod.Request = MagicMock
        flask_mod.Response = MagicMock
        flask_mod.Flask = MagicMock

    yield

    # Tear down: remove added paths and cached modules
    for p in paths_added:
        if p in sys.path:
            sys.path.remove(p)
    # Remove modules we may have imported during tests
    for key in list(sys.modules.keys()):
        if (
            key.startswith("helpers")
            or key.startswith("api.")
            or key.startswith("python.helpers.api")
        ):
            del sys.modules[key]
    for mod_name, stub in stubs_injected.items():
        if sys.modules.get(mod_name) is stub:
            del sys.modules[mod_name]


# ---------------------------------------------------------------------------
# Import helper -- reimport inside tests so fixture path is active
# ---------------------------------------------------------------------------


def _make_handler():
    """Create an ImageGenerate instance without Flask."""
    from api.image_generate import ImageGenerate

    handler = ImageGenerate.__new__(ImageGenerate)
    handler.app = MagicMock()
    handler.thread_lock = MagicMock()
    return handler


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestImageGenerateHandler:
    """Tests for the ImageGenerate API handler."""

    def test_extends_api_handler(self):
        """ImageGenerate is a subclass of ApiHandler."""
        from python.helpers.api import ApiHandler
        from api.image_generate import ImageGenerate

        assert issubclass(ImageGenerate, ApiHandler)

    def test_get_methods_returns_post(self):
        """get_methods() returns ['POST']."""
        from api.image_generate import ImageGenerate

        assert ImageGenerate.get_methods() == ["POST"]

    @pytest.mark.asyncio
    async def test_process_returns_images_and_model(self):
        """process() returns {"images": [...], "model": "..."} on success."""
        handler = _make_handler()

        fake_results = [
            {
                "b64_json": "base64data",
                "url": "https://example.com/img.png",
                "revised_prompt": "a revised prompt",
            }
        ]

        with patch(
            "api.image_generate.generate_image",
            new_callable=AsyncMock,
            return_value=fake_results,
        ):
            result = await handler.process(
                {"prompt": "a cat sitting on a mat"}, MagicMock()
            )

        assert "images" in result
        assert result["images"] == fake_results
        assert "model" in result

    @pytest.mark.asyncio
    async def test_process_error_when_prompt_empty(self):
        """process() returns an error dict when prompt is empty."""
        handler = _make_handler()

        result = await handler.process({"prompt": ""}, MagicMock())

        assert "error" in result
        assert result["error"] == "prompt is required"
        assert result["images"] == []

    @pytest.mark.asyncio
    async def test_process_error_when_prompt_missing(self):
        """process() returns an error dict when prompt key is absent."""
        handler = _make_handler()

        result = await handler.process({}, MagicMock())

        assert "error" in result
        assert result["error"] == "prompt is required"
        assert result["images"] == []

    @pytest.mark.asyncio
    async def test_process_forwards_model_and_size(self):
        """process() passes model, size, and n from input to generate_image."""
        handler = _make_handler()

        with patch(
            "api.image_generate.generate_image",
            new_callable=AsyncMock,
            return_value=[],
        ) as mock_gen:
            await handler.process(
                {
                    "prompt": "a dog",
                    "model": "openai/dall-e-2",
                    "size": "512x512",
                    "n": 3,
                },
                MagicMock(),
            )

            mock_gen.assert_called_once_with(
                prompt="a dog",
                model="openai/dall-e-2",
                size="512x512",
                n=3,
            )

    @pytest.mark.asyncio
    async def test_process_returns_error_on_exception(self):
        """process() catches exceptions and returns error dict."""
        handler = _make_handler()

        with patch(
            "api.image_generate.generate_image",
            new_callable=AsyncMock,
            side_effect=RuntimeError("provider unavailable"),
        ):
            result = await handler.process(
                {"prompt": "a landscape"}, MagicMock()
            )

        assert "error" in result
        assert "provider unavailable" in result["error"]
        assert result["images"] == []
