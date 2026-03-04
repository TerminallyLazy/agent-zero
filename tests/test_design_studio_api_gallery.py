"""Tests for a0_design_studio image gallery API handler."""

import base64
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

PLUGIN_ROOT = str(
    Path(__file__).parent.parent / "usr" / "plugins" / "a0_design_studio"
)


def _build_api_stub():
    """Create a minimal stub for python.helpers.api.

    This avoids pulling in flask, werkzeug, agent, models, litellm and every
    other heavy dependency that python.helpers.api transitively imports.
    """
    import types
    from abc import abstractmethod

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
    mod.Request = MagicMock
    return mod


@pytest.fixture(autouse=True)
def _plugin_path():
    """Add plugin root and project root to sys.path so imports resolve.

    Stubs out python.helpers.api and litellm to avoid heavy transitive
    dependencies (flask, werkzeug, agent, models, etc.) that are not needed
    for unit-testing the gallery handler.
    """
    project_root = str(Path(__file__).parent.parent)

    paths_added: list[str] = []
    for p in (PLUGIN_ROOT, project_root):
        if p not in sys.path:
            sys.path.insert(0, p)
            paths_added.append(p)

    # Stub out modules with deep dependency chains
    stubs_added: list[str] = []

    # Stub litellm (used by helpers.image_providers)
    if "litellm" not in sys.modules:
        sys.modules["litellm"] = MagicMock()
        stubs_added.append("litellm")

    # Stub python.helpers.api to avoid flask/werkzeug/agent chain
    api_stub = _build_api_stub()
    for mod_name in ("python", "python.helpers", "python.helpers.api"):
        if mod_name not in sys.modules:
            if mod_name == "python.helpers.api":
                sys.modules[mod_name] = api_stub
            else:
                import types
                sys.modules[mod_name] = types.ModuleType(mod_name)
            stubs_added.append(mod_name)

    # Also stub other python.helpers submodules that might be imported
    for sub in ("python.helpers.plugins",):
        if sub not in sys.modules:
            sys.modules[sub] = MagicMock()
            stubs_added.append(sub)

    yield

    # Tear down: remove added paths and cached modules
    for p in paths_added:
        if p in sys.path:
            sys.path.remove(p)
    for key in list(sys.modules.keys()):
        if key.startswith("helpers") or key.startswith("api."):
            del sys.modules[key]
    for mod_name in stubs_added:
        sys.modules.pop(mod_name, None)


# ---------------------------------------------------------------------------
# Import helper -- reimport inside tests so fixture path is active
# ---------------------------------------------------------------------------


def _make_handler():
    """Create an ImageGallery instance without Flask."""
    from api.image_gallery import ImageGallery

    handler = ImageGallery.__new__(ImageGallery)
    handler.app = MagicMock()
    handler.thread_lock = MagicMock()
    return handler


FAKE_IMAGE_DATA = b"fake-png-data"
FAKE_IMAGE_B64 = base64.b64encode(FAKE_IMAGE_DATA).decode()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestImageGalleryHandler:
    """Tests for the ImageGallery API handler."""

    def test_handler_accepts_get_and_post(self):
        """get_methods() includes both GET and POST."""
        from api.image_gallery import ImageGallery

        methods = ImageGallery.get_methods()
        assert "GET" in methods
        assert "POST" in methods

    @pytest.mark.asyncio
    async def test_list_empty_gallery(self, tmp_path):
        """Non-existent gallery returns empty list."""
        handler = _make_handler()
        gallery = str(tmp_path / "nonexistent_gallery")

        result = await handler.process(
            {"action": "list", "gallery_path": gallery}, MagicMock()
        )

        assert result == {"images": []}

    @pytest.mark.asyncio
    async def test_save_and_list(self, tmp_path):
        """Save an image, then list and verify it appears."""
        handler = _make_handler()
        gallery = str(tmp_path / "gallery")

        # Save
        save_result = await handler.process(
            {
                "action": "save",
                "gallery_path": gallery,
                "image_b64": FAKE_IMAGE_B64,
                "filename": "test_image.png",
                "metadata": {"prompt": "a cat", "model": "dall-e-3"},
            },
            MagicMock(),
        )
        assert save_result["success"] is True
        assert save_result["filename"] == "test_image.png"

        # List
        list_result = await handler.process(
            {"action": "list", "gallery_path": gallery}, MagicMock()
        )
        assert len(list_result["images"]) == 1
        img = list_result["images"][0]
        assert img["filename"] == "test_image.png"
        assert img["prompt"] == "a cat"
        assert img["model"] == "dall-e-3"

    @pytest.mark.asyncio
    async def test_delete_image(self, tmp_path):
        """Save, delete, verify gone."""
        handler = _make_handler()
        gallery = str(tmp_path / "gallery")

        # Save
        await handler.process(
            {
                "action": "save",
                "gallery_path": gallery,
                "image_b64": FAKE_IMAGE_B64,
                "filename": "to_delete.png",
                "metadata": {"prompt": "delete me"},
            },
            MagicMock(),
        )

        # Delete
        delete_result = await handler.process(
            {
                "action": "delete",
                "gallery_path": gallery,
                "filename": "to_delete.png",
            },
            MagicMock(),
        )
        assert delete_result["success"] is True

        # Verify gone
        list_result = await handler.process(
            {"action": "list", "gallery_path": gallery}, MagicMock()
        )
        assert list_result["images"] == []

    @pytest.mark.asyncio
    async def test_get_image(self, tmp_path):
        """Save, get, verify b64 content matches."""
        handler = _make_handler()
        gallery = str(tmp_path / "gallery")

        # Save
        await handler.process(
            {
                "action": "save",
                "gallery_path": gallery,
                "image_b64": FAKE_IMAGE_B64,
                "filename": "retrieve_me.png",
                "metadata": {"prompt": "retrieve this", "model": "test-model"},
            },
            MagicMock(),
        )

        # Get
        get_result = await handler.process(
            {
                "action": "get",
                "gallery_path": gallery,
                "filename": "retrieve_me.png",
            },
            MagicMock(),
        )
        assert get_result["image_b64"] == FAKE_IMAGE_B64
        assert get_result["filename"] == "retrieve_me.png"
        assert get_result["metadata"]["prompt"] == "retrieve this"
        assert get_result["metadata"]["model"] == "test-model"
