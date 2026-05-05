"""Tests for api/provider_status.py — per-provider connection state."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

from usr.plugins.jcode_harness.api import provider_status as ps


def test_unknown_provider_absent_when_nothing_configured(monkeypatch, tmp_path):
    """No auth files, no env vars => every provider reports not connected."""
    # Path.expanduser() reads $HOME directly via os.path.expanduser, NOT
    # Path.home(). Patching the env var is the load-bearing isolation step.
    monkeypatch.setenv("HOME", str(tmp_path))
    for env in (
        "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN",
        "OPENAI_API_KEY",
        "GEMINI_API_KEY",
        "GITHUB_TOKEN", "GITHUB_COPILOT_TOKEN",
    ):
        monkeypatch.delenv(env, raising=False)

    handler = ps.ProviderStatus.__new__(ps.ProviderStatus)
    result = asyncio.run(handler.process({}, None))
    providers = result["providers"]
    for pid in ("claude", "openai", "gemini", "copilot"):
        assert providers[pid]["connected"] is False, pid
        assert providers[pid]["source"] == "", pid


def test_auth_file_marks_provider_connected(monkeypatch, tmp_path):
    """jcode native auth file → connected=True, source=auth_file."""
    # Path.expanduser() reads $HOME directly via os.path.expanduser, NOT
    # Path.home(). Patching the env var is the load-bearing isolation step.
    monkeypatch.setenv("HOME", str(tmp_path))
    for env in (
        "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN",
        "OPENAI_API_KEY",
        "GEMINI_API_KEY",
        "GITHUB_TOKEN", "GITHUB_COPILOT_TOKEN",
    ):
        monkeypatch.delenv(env, raising=False)

    auth = tmp_path / ".jcode" / "auth.json"
    auth.parent.mkdir(parents=True, exist_ok=True)
    auth.write_text("{}")

    handler = ps.ProviderStatus.__new__(ps.ProviderStatus)
    result = asyncio.run(handler.process({}, None))
    assert result["providers"]["claude"]["connected"] is True
    assert result["providers"]["claude"]["source"] == "auth_file"
    # Other providers stay disconnected
    assert result["providers"]["openai"]["connected"] is False


def test_env_var_marks_provider_connected(monkeypatch, tmp_path):
    """API key env var → connected=True, source=env_var."""
    # Path.expanduser() reads $HOME directly via os.path.expanduser, NOT
    # Path.home(). Patching the env var is the load-bearing isolation step.
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_COPILOT_TOKEN", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-real")

    handler = ps.ProviderStatus.__new__(ps.ProviderStatus)
    result = asyncio.run(handler.process({}, None))
    assert result["providers"]["openai"]["connected"] is True
    assert result["providers"]["openai"]["source"] == "env_var"
    assert result["providers"]["claude"]["connected"] is False


def test_get_methods_includes_get_and_post():
    """Probe endpoint must accept GET (page-load fetch from main.html)
    AND POST (consistency with our other read-only handlers)."""
    methods = ps.ProviderStatus.get_methods()
    assert "GET" in methods
    assert "POST" in methods


def test_provider_catalog_covers_four_buttons():
    """Backend dict keys MUST match the four provider IDs the WebUI's main.html
    Login button x-for iteration uses. Adding a button without backing this
    catalog produces 'undefined' status; adding here without a button is dead
    state. Lock the symmetry."""
    catalog = set(ps._PROVIDER_CREDS.keys())
    assert catalog == {"claude", "openai", "gemini", "copilot"}, catalog


def test_unreadable_auth_file_does_not_crash(monkeypatch, tmp_path):
    """A path that exists but raises OSError on stat (e.g. permission
    denied, broken symlink) must not bubble — provider just stays
    disconnected."""
    # Path.expanduser() reads $HOME directly via os.path.expanduser, NOT
    # Path.home(). Patching the env var is the load-bearing isolation step.
    monkeypatch.setenv("HOME", str(tmp_path))

    class _RaisingPath:
        def __init__(self, path):
            self._p = Path(path)

        def expanduser(self):
            return self

        def is_file(self):
            raise OSError("permission denied")

    spec = {"auth_files": ["~/.jcode/auth.json"], "env_vars": []}
    # Patch Path so expanduser/is_file raises
    real_path = ps.Path

    def fake_path(p):
        return _RaisingPath(p)

    monkeypatch.setattr(ps, "Path", fake_path)
    try:
        connected, source = ps._probe_provider(spec)
    finally:
        monkeypatch.setattr(ps, "Path", real_path)
    assert connected is False
    assert source == ""
