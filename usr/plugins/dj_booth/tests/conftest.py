import sys
import types
from pathlib import Path

import pytest

pytest_plugins = ["pytest_asyncio"]


# Ensure repo root on sys.path so `helpers.*` resolves to the real top-level package.
# Pytest auto-inserts the rootpkg dir (`usr/plugins/dj_booth`) into sys.path so the
# `tests` package is importable. That dir also contains a regular `helpers/` package
# which would shadow the top-level `helpers` namespace package (where `helpers.tool`,
# `helpers.api`, etc. live). Drop the plugin dir from sys.path and put the repo root
# at position 0 so the top-level `helpers` wins. Plugin code uses the full
# `usr.plugins.dj_booth.helpers...` import path, so this does not break Slice 1.
_REPO_ROOT = str(Path(__file__).resolve().parents[4])
_PLUGIN_DIR = str(Path(__file__).resolve().parents[1])
sys.path[:] = [p for p in sys.path if p != _PLUGIN_DIR]
if _REPO_ROOT in sys.path:
    sys.path.remove(_REPO_ROOT)
sys.path.insert(0, _REPO_ROOT)
# Drop any cached `helpers` import that may have resolved to the wrong path.
for _mod_name in [m for m in list(sys.modules) if m == "helpers" or m.startswith("helpers.")]:
    if _mod_name not in ("helpers.print_style", "helpers.strings", "helpers.extension"):
        sys.modules.pop(_mod_name, None)


# Lightweight stubs so `helpers.tool` (and its transitive imports) load without
# pulling in the full agent runtime / numba / whisper stack.
def _install_stubs():
    if "agent" not in sys.modules:
        m = types.ModuleType("agent")

        class Agent:
            pass

        class LoopData:
            pass

        class AgentContext:
            pass

        m.Agent = Agent
        m.LoopData = LoopData
        m.AgentContext = AgentContext
        sys.modules["agent"] = m

    if "helpers.print_style" not in sys.modules:
        ps = types.ModuleType("helpers.print_style")

        class PrintStyle:
            def __init__(self, *a, **k):
                pass

            def print(self, *a, **k):
                pass

            def stream(self, *a, **k):
                pass

        ps.PrintStyle = PrintStyle
        sys.modules["helpers.print_style"] = ps

    if "helpers.strings" not in sys.modules:
        ss = types.ModuleType("helpers.strings")
        ss.sanitize_string = lambda s: s
        sys.modules["helpers.strings"] = ss

    if "helpers.extension" not in sys.modules:
        ex = types.ModuleType("helpers.extension")

        async def call_extensions_async(*a, **k):
            pass

        class Extension:
            def __init__(self, agent=None, *a, **k):
                self.agent = agent

        def extensible(fn):
            return fn

        ex.call_extensions_async = call_extensions_async
        ex.Extension = Extension
        ex.extensible = extensible
        sys.modules["helpers.extension"] = ex


_install_stubs()

# Force-load `helpers.tool` here so that subsequent test-module imports of
# `usr.plugins.dj_booth.tools.dj_tool` (which does `from helpers.tool import ...`)
# resolve against the top-level `helpers` namespace package while we still control
# sys.path. Without this the first `import helpers` may bind to the plugin's
# regular `helpers/` package instead.
import importlib as _il
_il.invalidate_caches()
import helpers.tool  # noqa: F401
import helpers.api  # noqa: F401
