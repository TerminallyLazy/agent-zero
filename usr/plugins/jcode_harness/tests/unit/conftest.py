"""Shared fixtures for jcode_harness tool unit tests.

The plugin's own ``helpers/`` package shadows the A0 framework's top-level
``helpers/`` when pytest collects from inside the plugin tree. We install a
namespace-style ``helpers`` package whose ``__path__`` points at the framework
``helpers/`` directory, then load the specific framework modules the tools
need (``helpers.tool``, ``helpers.notification``) by file path so the plugin's
``from helpers.tool import Tool, Response`` and ``from helpers.notification
import ...`` resolve to the framework copy rather than the plugin's.

Fake-daemon fixture spins up an in-process Unix socket NDJSON server so tools
can run end-to-end without spawning the real jcode binary.
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
import tempfile
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest


REPO_ROOT = Path("/Users/lazy/Desktop/agent-zero")
FRAMEWORK_HELPERS_DIR = REPO_ROOT / "helpers"


def _install_framework_helpers_namespace() -> None:
    """Replace any plugin-shadow ``helpers`` module with a namespace package
    whose ``__path__`` is the framework helpers/ directory."""
    pkg = sys.modules.get("helpers")
    plugin_shadowed = pkg is not None and "usr/plugins/jcode_harness" in (
        getattr(pkg, "__file__", "") or ""
    )
    if pkg is None or plugin_shadowed:
        helpers_pkg = types.ModuleType("helpers")
        helpers_pkg.__path__ = [str(FRAMEWORK_HELPERS_DIR)]
        sys.modules["helpers"] = helpers_pkg


def _load_framework_module(name: str, filename: str):
    """Load ``helpers.<name>`` from the framework helpers/ dir by file path."""
    full = f"helpers.{name}"
    if full in sys.modules:
        return sys.modules[full]
    path = FRAMEWORK_HELPERS_DIR / filename
    if not path.exists():
        return None
    spec = importlib.util.spec_from_file_location(full, path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    sys.modules[full] = module
    spec.loader.exec_module(module)
    return module


def _ensure_helpers_tool_loaded() -> None:
    """Make ``from helpers.tool import Tool, Response`` import the A0 module.

    Stub ``agent`` plus the other ``helpers.*`` siblings ``helpers.tool``
    pulls in (print_style, strings, extension) so we can exec the file
    without the rest of the runtime.
    """
    _install_framework_helpers_namespace()

    # Stub `agent` with the symbols A0 helpers.tool / helpers.notification
    # reach for at import or lazy-call time. Add to existing stub if test ran
    # earlier without these.
    agent_stub = sys.modules.get("agent")
    if agent_stub is None:
        agent_stub = types.ModuleType("agent")
        sys.modules["agent"] = agent_stub
    for attr in ("Agent", "LoopData", "AgentContext"):
        if not hasattr(agent_stub, attr):
            setattr(agent_stub, attr, type(attr, (), {}))

    if "helpers.print_style" not in sys.modules:
        ps_mod = types.ModuleType("helpers.print_style")

        class _FakePrintStyle:
            def __init__(self, *a, **kw):
                pass

            def print(self, *a, **kw):
                return None

            def stream(self, *a, **kw):
                return None

        ps_mod.PrintStyle = _FakePrintStyle
        sys.modules["helpers.print_style"] = ps_mod

    if "helpers.strings" not in sys.modules:
        s = types.ModuleType("helpers.strings")
        s.sanitize_string = lambda x: x
        sys.modules["helpers.strings"] = s

    if "helpers.extension" not in sys.modules:
        e = types.ModuleType("helpers.extension")

        async def _noop(*a, **kw):
            return None

        class _Extension:
            """Minimal real-shaped Extension base for plugin extension tests.

            Mirrors helpers.extension.Extension's __init__ signature so the
            plugin's extension classes (which subclass Extension) construct
            cleanly under the tests' stubbed framework.
            """

            def __init__(self, agent=None, **kwargs):
                self.agent = agent
                self.kwargs = kwargs

            async def execute(self, **kwargs):  # pragma: no cover
                return None

        e.call_extensions_async = _noop
        e.Extension = _Extension
        sys.modules["helpers.extension"] = e

    # Preload ``helpers.notification`` so the plugin's ``helpers.notifications``
    # module captures a stable class identity. ``test_notifications.py`` is
    # idempotent under this prepopulated cache.
    _load_framework_module("notification", "notification.py")

    # Now load helpers.tool itself.
    if "helpers.tool" not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            "helpers.tool", FRAMEWORK_HELPERS_DIR / "tool.py"
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules["helpers.tool"] = module
        spec.loader.exec_module(module)


_ensure_helpers_tool_loaded()


# ---------------------------------------------------------------------------
# Tool-test fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_agent():
    """Minimal Agent stub usable by Tool.set_progress / log paths."""
    a = MagicMock()
    a.context.id = "test-ctx"
    a.context.log.log = MagicMock()
    a.hist_add_tool_result = MagicMock()
    a.agent_name = "test"
    return a


def make_tool(cls, agent, **state):
    """Construct a Tool subclass without invoking the real ``__init__``."""
    obj = cls.__new__(cls)
    obj.agent = agent
    obj.progress = ""
    obj.name = state.get("name", cls.__name__)
    obj.method = state.get("method")
    obj.args = state.get("args", {})
    obj.message = state.get("message", "")
    obj.loop_data = state.get("loop_data")
    return obj


class FakeDaemon:
    """In-process Unix-socket NDJSON server for tool tests.

    Each instance accepts one connection and hands the (reader, writer) pair to
    a test-supplied ``script`` async callable, then closes. Tests can record
    NDJSON lines on ``received_lines`` from inside the script.
    """

    def __init__(self, script):
        self._script = script
        self._server = None
        self.received_lines: list[bytes] = []
        self.socket_path: str = ""
        self._tmpdir: str = ""

    async def start(self) -> str:
        self._tmpdir = tempfile.mkdtemp(prefix="jc-tool-")
        self.socket_path = str(Path(self._tmpdir) / "s")

        async def _handle(reader, writer):
            try:
                await self._script(self, reader, writer)
            finally:
                try:
                    writer.close()
                    await writer.wait_closed()
                except Exception:
                    pass

        self._server = await asyncio.start_unix_server(
            _handle, path=self.socket_path
        )
        return self.socket_path

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            try:
                await self._server.wait_closed()
            except Exception:
                pass
        try:
            os.unlink(self.socket_path)
        except OSError:
            pass
        try:
            os.rmdir(self._tmpdir)
        except OSError:
            pass


async def read_line(reader: asyncio.StreamReader) -> bytes:
    return await reader.readline()


@pytest.fixture
def fake_daemon():
    """Factory yielding ``FakeDaemon`` instances; auto-cleans on teardown."""
    daemons: list[FakeDaemon] = []

    def _make(script):
        d = FakeDaemon(script)
        daemons.append(d)
        return d

    yield _make

    # Clean up any servers we spun up. We're inside an async test loop already
    # for the test that used us; teardown runs after the test completes — at
    # that point a fresh asyncio.run is needed.
    async def _shutdown_all():
        for d in daemons:
            await d.stop()

    try:
        asyncio.run(_shutdown_all())
    except RuntimeError:
        # If a loop is somehow still running, do best-effort sync cleanup.
        for d in daemons:
            if d._server is not None:
                d._server.close()


@pytest.fixture
def patch_supervisor(monkeypatch):
    """Patch DaemonSupervisor.ensure_running + locate_jcode_binary.

    Returns a setup function. Pass ``binary=None`` to simulate a missing
    binary, or ``raises=NoCredentialsError(...)`` to simulate missing creds.
    """

    def _setup(
        socket_path: str | None,
        binary: str | None = "/fake/jcode",
        raises: Exception | None = None,
    ):
        from usr.plugins.jcode_harness.helpers import daemon as daemon_mod

        async def _ensure(self, working_dir):
            if raises is not None:
                raise raises
            return socket_path

        monkeypatch.setattr(
            daemon_mod.DaemonSupervisor, "ensure_running", _ensure
        )
        monkeypatch.setattr(daemon_mod, "locate_jcode_binary", lambda: binary)

        # The tool modules do `from .daemon import locate_jcode_binary`, which
        # binds a fresh name. Patch that name in any tool module already
        # imported.
        for tool_modname in (
            "usr.plugins.jcode_harness.tools.jcode_session",
            "usr.plugins.jcode_harness.tools.jcode_grep",
            "usr.plugins.jcode_harness.tools.jcode_memory",
            "usr.plugins.jcode_harness.tools.jcode_skill",
            "usr.plugins.jcode_harness.tools.jcode_resume",
            "usr.plugins.jcode_harness.tools.jcode_swarm_msg",
        ):
            mod = sys.modules.get(tool_modname)
            if mod is not None and hasattr(mod, "locate_jcode_binary"):
                monkeypatch.setattr(mod, "locate_jcode_binary", lambda: binary)

    return _setup
