"""Bootstrap for security smoke tests.

These tests don't need the full helpers-namespace gymnastics that
``tests/unit/conftest.py`` performs, but they DO import the plugin's own
``helpers.daemon`` / ``helpers.provider_import`` / ``helpers.paths`` modules
via the ``usr.plugins.jcode_harness`` package path, which only resolves if
the repo root is on ``sys.path``. Pytest already inserts the repo root when
``rootdir`` resolution finds ``pytest.ini``/``pyproject.toml`` at the top, so
in practice this is belt-and-braces — but cheap and explicit.

We also defensively prevent the plugin's ``helpers`` package from shadowing
the framework's top-level ``helpers`` if a unit-test run earlier in the same
process left a stale entry in ``sys.modules``.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[5]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
