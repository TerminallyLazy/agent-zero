"""Tests for a0_design_studio image_editor agent tool."""

import base64
import os
import sys
import types
from abc import abstractmethod
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

PLUGIN_ROOT = str(
    Path(__file__).parent.parent / "usr" / "plugins" / "a0_design_studio"
)
PROJECT_ROOT = str(Path(__file__).parent.parent)


def _build_tool_stub() -> types.ModuleType:
    """Create a lightweight stub for ``python.helpers.tool``.

    Avoids importing the real module which pulls in agent, models, litellm
    and other heavy Agent Zero dependencies.
    """
    from dataclasses import dataclass
    from typing import Any

    mod = types.ModuleType("python.helpers.tool")

    @dataclass
    class Response:
        message: str
        break_loop: bool
        additional: dict[str, Any] | None = None

    class Tool:
        def __init__(self, agent, name, method, args, message, loop_data, **kwargs):
            self.agent = agent
            self.name = name
            self.args = args
            self.loop_data = loop_data
            self.message = message

        @abstractmethod
        async def execute(self, **kwargs) -> Response:
            pass

    mod.Response = Response
    mod.Tool = Tool
    return mod


@pytest.fixture(autouse=True)
def _plugin_path():
    """Add plugin root and project root to sys.path and inject stubs.

    Stubs ``python.helpers.tool`` and other heavy deps so the tool module
    can be imported without the full Agent Zero stack.
    """
    paths_added: list[str] = []
    for p in (PLUGIN_ROOT, PROJECT_ROOT):
        if p not in sys.path:
            sys.path.insert(0, p)
            paths_added.append(p)

    stubs: dict[str, object] = {}
    tool_stub = _build_tool_stub()

    for mod_name, mod_obj in (
        ("python", types.ModuleType("python")),
        ("python.helpers", types.ModuleType("python.helpers")),
        ("python.helpers.tool", tool_stub),
        ("python.helpers.print_style", MagicMock()),
        ("python.helpers.errors", MagicMock()),
        ("python.helpers.files", MagicMock()),
        ("python.helpers.cache", MagicMock()),
        ("python.helpers.plugins", MagicMock()),
        ("python.helpers.strings", MagicMock()),
        ("agent", MagicMock()),
        ("litellm", MagicMock()),
    ):
        if mod_name not in sys.modules:
            sys.modules[mod_name] = mod_obj
            stubs[mod_name] = mod_obj

    yield

    # Tear down
    for p in paths_added:
        if p in sys.path:
            sys.path.remove(p)
    for key in list(sys.modules.keys()):
        if key.startswith("helpers") or key.startswith("tools."):
            del sys.modules[key]
    for mod_name in stubs:
        if mod_name in sys.modules and sys.modules[mod_name] is stubs[mod_name]:
            del sys.modules[mod_name]


# ---------------------------------------------------------------------------
# Helper -- build an ImageEditor instance without full agent stack
# ---------------------------------------------------------------------------

def _make_tool(**args_override):
    """Create an ImageEditor instance for testing."""
    from tools.image_editor import ImageEditor

    tool = ImageEditor.__new__(ImageEditor)
    tool.agent = MagicMock()
    tool.name = "image_editor"
    tool.args = args_override
    tool.loop_data = None
    tool.message = ""
    return tool


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestImageEditorTool:
    """Tests for the ImageEditor agent tool."""

    def test_tool_extends_base(self):
        """ImageEditor is a subclass of Tool."""
        from python.helpers.tool import Tool
        from tools.image_editor import ImageEditor

        assert issubclass(ImageEditor, Tool)

    @pytest.mark.asyncio
    async def test_generate_action(self, tmp_path):
        """generate action calls generate_image and saves to disk."""
        fake_b64 = base64.b64encode(b"fake png data").decode()
        fake_results = [
            {
                "b64_json": fake_b64,
                "url": "https://example.com/img.png",
                "revised_prompt": "a glorious sunset",
            }
        ]

        gallery = str(tmp_path / "gallery")
        tool = _make_tool(action="generate", prompt="a sunset")

        with patch(
            "tools.image_editor.generate_image",
            new_callable=AsyncMock,
            return_value=fake_results,
        ), patch(
            "tools.image_editor.get_plugin_config",
            return_value={
                "image_generation_model": "openai/dall-e-3",
                "default_size": "1024x1024",
                "gallery_path": gallery,
            },
        ):
            response = await tool.execute()

        assert not response.break_loop
        assert "generated" in response.message.lower() or "saved" in response.message.lower()
        # Verify the file was actually written
        files = os.listdir(gallery)
        assert len(files) == 1
        assert files[0].startswith("generated_")
        assert files[0].endswith(".png")

    @pytest.mark.asyncio
    async def test_edit_action(self, tmp_path):
        """edit action reads the image, calls edit_image, returns Response."""
        # Create a temp image file
        img_file = tmp_path / "source.png"
        img_file.write_bytes(b"fake image bytes")

        fake_results = [{"content": "The sky has been changed to stormy."}]

        tool = _make_tool(
            action="edit",
            image_path=str(img_file),
            prompt="make the sky stormy",
        )

        with patch(
            "tools.image_editor.edit_image",
            new_callable=AsyncMock,
            return_value=fake_results,
        ), patch(
            "tools.image_editor.get_plugin_config",
            return_value={"image_edit_model": "google/gemini-2.0-flash"},
        ):
            response = await tool.execute()

        assert not response.break_loop
        assert "stormy" in response.message.lower() or "edit" in response.message.lower()

    @pytest.mark.asyncio
    async def test_save_action(self, tmp_path):
        """save action copies an image to the output_path."""
        src = tmp_path / "src.png"
        src.write_bytes(b"image data here")
        dest = tmp_path / "out" / "dest.png"

        tool = _make_tool(
            action="save",
            image_path=str(src),
            output_path=str(dest),
        )

        with patch(
            "tools.image_editor.get_plugin_config",
            return_value={},
        ):
            response = await tool.execute()

        assert not response.break_loop
        assert "saved" in response.message.lower()
        assert dest.exists()
        assert dest.read_bytes() == b"image data here"

    @pytest.mark.asyncio
    async def test_generate_requires_prompt(self):
        """generate action returns error when prompt is missing."""
        tool = _make_tool(action="generate")

        with patch(
            "tools.image_editor.get_plugin_config",
            return_value={},
        ):
            response = await tool.execute()

        assert not response.break_loop
        assert "error" in response.message.lower() or "required" in response.message.lower()

    @pytest.mark.asyncio
    async def test_unknown_action(self):
        """Unknown action returns an error message."""
        tool = _make_tool(action="frobnicate")

        with patch(
            "tools.image_editor.get_plugin_config",
            return_value={},
        ):
            response = await tool.execute()

        assert not response.break_loop
        assert "unknown" in response.message.lower() or "frobnicate" in response.message.lower()
