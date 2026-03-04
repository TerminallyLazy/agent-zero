"""Tests for a0_design_studio image edit API handler."""

import sys
import types
from abc import abstractmethod
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

PLUGIN_ROOT = str(
    Path(__file__).parent.parent / "usr" / "plugins" / "a0_design_studio"
)


def _build_api_stub() -> types.ModuleType:
    """Create a lightweight stub for ``python.helpers.api``.

    This avoids importing the real module which pulls in flask, agent,
    models, litellm, openai, browser_use and many other heavy deps.
    """
    mod = types.ModuleType("python.helpers.api")

    class ApiHandler:
        def __init__(self, app, thread_lock):
            self.app = app
            self.thread_lock = thread_lock

        @classmethod
        def get_methods(cls) -> list[str]:
            return ["POST"]

        @abstractmethod
        async def process(self, input, request):
            pass

    mod.ApiHandler = ApiHandler
    mod.Input = dict
    mod.Request = object
    return mod


@pytest.fixture(autouse=True)
def _plugin_path():
    """Add plugin root to sys.path and inject lightweight stubs.

    We stub ``python.helpers.api`` (and its parent packages) so that
    ``from python.helpers.api import ApiHandler, Input, Request``
    inside the handler module resolves without importing Flask or the
    full Agent Zero stack.
    """
    project_root = str(Path(__file__).parent.parent)

    paths_added: list[str] = []
    for p in (PLUGIN_ROOT, project_root):
        if p not in sys.path:
            sys.path.insert(0, p)
            paths_added.append(p)

    # Stub the api module and its parent packages
    stubs: dict[str, object] = {}
    api_stub = _build_api_stub()

    for mod_name, mod_obj in (
        ("python", types.ModuleType("python")),
        ("python.helpers", types.ModuleType("python.helpers")),
        ("python.helpers.api", api_stub),
        ("litellm", MagicMock()),
    ):
        if mod_name not in sys.modules:
            sys.modules[mod_name] = mod_obj
            stubs[mod_name] = mod_obj

    yield

    # Tear down: remove added paths and cached modules
    for p in paths_added:
        if p in sys.path:
            sys.path.remove(p)
    for key in list(sys.modules.keys()):
        if key.startswith("helpers") or key.startswith("api."):
            del sys.modules[key]
    for mod_name in stubs:
        if mod_name in sys.modules and sys.modules[mod_name] is stubs[mod_name]:
            del sys.modules[mod_name]


# ---------------------------------------------------------------------------
# Import helper — reimport inside tests so fixture path is active
# ---------------------------------------------------------------------------


def _make_handler():
    """Create an ImageEdit instance without Flask."""
    from api.image_edit import ImageEdit

    handler = ImageEdit.__new__(ImageEdit)
    handler.app = MagicMock()
    handler.thread_lock = MagicMock()
    return handler


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestImageEditHandler:
    """Tests for the ImageEdit API handler."""

    def test_extends_api_handler(self):
        """ImageEdit is a subclass of ApiHandler."""
        from python.helpers.api import ApiHandler
        from api.image_edit import ImageEdit

        assert issubclass(ImageEdit, ApiHandler)

    def test_get_methods_returns_post(self):
        """get_methods() returns ['POST']."""
        from api.image_edit import ImageEdit

        assert ImageEdit.get_methods() == ["POST"]

    @pytest.mark.asyncio
    async def test_process_returns_images_and_model(self):
        """process() returns {"images": [...], "model": "..."} on success."""
        handler = _make_handler()

        fake_results = [
            {
                "content": "edited image description",
                "revised_prompt": "make the sky blue",
            }
        ]

        with patch(
            "api.image_edit.edit_image",
            new_callable=AsyncMock,
            return_value=fake_results,
        ):
            result = await handler.process(
                {"image_b64": "abc123base64data", "prompt": "make the sky blue"},
                MagicMock(),
            )

        assert "images" in result
        assert result["images"] == fake_results
        assert "model" in result

    @pytest.mark.asyncio
    async def test_process_error_when_image_b64_missing(self):
        """process() returns an error dict when image_b64 is empty."""
        handler = _make_handler()

        result = await handler.process(
            {"image_b64": "", "prompt": "make it brighter"}, MagicMock()
        )

        assert "error" in result
        assert result["error"] == "image_b64 is required"
        assert result["images"] == []

    @pytest.mark.asyncio
    async def test_process_error_when_image_b64_key_absent(self):
        """process() returns an error dict when image_b64 key is absent."""
        handler = _make_handler()

        result = await handler.process(
            {"prompt": "make it brighter"}, MagicMock()
        )

        assert "error" in result
        assert result["error"] == "image_b64 is required"
        assert result["images"] == []

    @pytest.mark.asyncio
    async def test_process_error_when_prompt_missing(self):
        """process() returns an error dict when prompt is empty."""
        handler = _make_handler()

        result = await handler.process(
            {"image_b64": "abc123base64data", "prompt": ""}, MagicMock()
        )

        assert "error" in result
        assert result["error"] == "prompt is required"
        assert result["images"] == []

    @pytest.mark.asyncio
    async def test_process_error_when_prompt_key_absent(self):
        """process() returns an error dict when prompt key is absent."""
        handler = _make_handler()

        result = await handler.process(
            {"image_b64": "abc123base64data"}, MagicMock()
        )

        assert "error" in result
        assert result["error"] == "prompt is required"
        assert result["images"] == []

    @pytest.mark.asyncio
    async def test_process_forwards_model_and_mask(self):
        """process() passes model and mask_b64 from input to edit_image."""
        handler = _make_handler()

        with patch(
            "api.image_edit.edit_image",
            new_callable=AsyncMock,
            return_value=[],
        ) as mock_edit:
            await handler.process(
                {
                    "image_b64": "abc123",
                    "prompt": "remove background",
                    "model": "openai/gpt-4o",
                    "mask_b64": "mask_data",
                },
                MagicMock(),
            )

            mock_edit.assert_called_once_with(
                image_b64="abc123",
                prompt="remove background",
                mask_b64="mask_data",
                model="openai/gpt-4o",
            )

    @pytest.mark.asyncio
    async def test_process_returns_error_on_exception(self):
        """process() catches exceptions and returns error dict."""
        handler = _make_handler()

        with patch(
            "api.image_edit.edit_image",
            new_callable=AsyncMock,
            side_effect=RuntimeError("provider unavailable"),
        ):
            result = await handler.process(
                {"image_b64": "abc123", "prompt": "fix colors"}, MagicMock()
            )

        assert "error" in result
        assert "provider unavailable" in result["error"]
        assert result["images"] == []
