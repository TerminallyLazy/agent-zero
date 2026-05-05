"""Tests for usr.plugins.jcode_harness.helpers.notifications.

The plugin lives under ``usr/plugins/jcode_harness/`` and contains its own
``helpers/`` subpackage. When pytest collects from inside the plugin tree it
puts the plugin dir first on ``sys.path``, which shadows the A0 framework's
top-level ``helpers/`` module. We work around that by preloading the framework
``helpers.notification`` from the repo root before importing the plugin
module under test.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest


def _load_framework_notification():
    """Load A0's ``helpers.notification`` from the repo root, bypassing the
    plugin-local ``helpers/`` package which shadows the framework when pytest
    puts the plugin dir first on ``sys.path``.

    We side-step the package machinery entirely by loading
    ``helpers/notification.py`` from the repo root via importlib's file-based
    spec API and registering it under ``helpers.notification`` so the plugin
    module's ``from helpers.notification import ...`` resolves to the same
    object.
    """
    import importlib.util

    repo_root = Path(__file__).resolve().parents[5]  # .../agent-zero
    framework_file = repo_root / "helpers" / "notification.py"
    if not framework_file.exists():
        return None
    # If the plugin's `helpers` is already cached, install a synthetic parent
    # whose __path__ points at the framework's helpers/ so submodule imports
    # downstream still work.
    fw_helpers_dir = str(framework_file.parent)
    pkg = sys.modules.get("helpers")
    if pkg is None or "usr/plugins/jcode_harness" in (
        getattr(pkg, "__file__", "") or ""
    ):
        # Build a namespace package wrapper with __path__ set to the framework.
        helpers_spec = importlib.util.spec_from_file_location(
            "helpers", repo_root / "helpers" / "__init__.py",
            submodule_search_locations=[fw_helpers_dir],
        )
        if helpers_spec is None:
            # No __init__.py — synthesize a namespace package.
            import types
            helpers_pkg = types.ModuleType("helpers")
            helpers_pkg.__path__ = [fw_helpers_dir]
            sys.modules["helpers"] = helpers_pkg
        else:
            helpers_pkg = importlib.util.module_from_spec(helpers_spec)
            sys.modules["helpers"] = helpers_pkg
            try:
                helpers_spec.loader.exec_module(helpers_pkg)
            except Exception:
                pass
    # Idempotent: if conftest (or another test) already loaded the framework
    # ``helpers.notification`` from this same file, reuse that module instance
    # so any other modules that captured a reference to its classes
    # (e.g. the plugin's ``helpers.notifications``) keep agreeing on identity.
    cached = sys.modules.get("helpers.notification")
    if cached is not None and getattr(cached, "__file__", "") == str(
        framework_file
    ):
        return cached
    spec = importlib.util.spec_from_file_location(
        "helpers.notification", framework_file
    )
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    sys.modules["helpers.notification"] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        return None
    return module


_fw = _load_framework_notification()
if _fw is None:
    pytest.skip(
        "A0 framework helpers.notification not importable",
        allow_module_level=True,
    )

NotificationManager = _fw.NotificationManager
NotificationPriority = _fw.NotificationPriority
NotificationType = _fw.NotificationType

from usr.plugins.jcode_harness.helpers import notifications  # noqa: E402


@pytest.fixture
def recorder(monkeypatch):
    """Capture every NotificationManager.send_notification call."""
    calls: list[dict] = []

    def fake_send(**kwargs):
        calls.append(kwargs)
        return None

    monkeypatch.setattr(
        NotificationManager, "send_notification", staticmethod(fake_send)
    )
    return calls


def test_info_passes_through(recorder):
    notifications.info("hello")
    assert len(recorder) == 1
    c = recorder[0]
    assert c["type"] is NotificationType.INFO
    assert c["priority"] is NotificationPriority.NORMAL
    assert c["message"] == "hello"
    assert c["title"] == "jcode"


def test_success_passes_through(recorder):
    notifications.success("done")
    assert recorder[0]["type"] is NotificationType.SUCCESS
    assert recorder[0]["message"] == "done"
    assert recorder[0]["title"] == "jcode"


def test_warning_passes_through(recorder):
    notifications.warning("careful")
    assert recorder[0]["type"] is NotificationType.WARNING
    assert recorder[0]["message"] == "careful"


def test_error_passes_through(recorder):
    notifications.error("boom")
    assert recorder[0]["type"] is NotificationType.ERROR
    assert recorder[0]["message"] == "boom"
    assert recorder[0]["title"] == "jcode"


def test_custom_title_overrides_default(recorder):
    notifications.info("hi", title="jcode-import")
    assert recorder[0]["title"] == "jcode-import"


def test_default_priority_is_normal(recorder):
    notifications.info("x")
    notifications.warning("y")
    notifications.error("z")
    for call in recorder:
        assert call["priority"] is NotificationPriority.NORMAL
