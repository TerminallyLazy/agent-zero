"""Tests for usr.plugins.jcode_harness.api.resume_session."""

from __future__ import annotations

import asyncio
import sys
from unittest.mock import MagicMock

import pytest

from usr.plugins.jcode_harness.helpers.daemon import NoCredentialsError


def _make_handler():
    from usr.plugins.jcode_harness.api.resume_session import ResumeSession

    return ResumeSession(app=MagicMock(), thread_lock=MagicMock())


def _patch_api_supervisor(
    monkeypatch,
    socket_path: str | None,
    binary: str | None = "/fake/jcode",
    raises: Exception | None = None,
):
    """Patch supervisor + binary lookup as imported into the api module."""
    import usr.plugins.jcode_harness.api.resume_session as mod
    from usr.plugins.jcode_harness.helpers import daemon as daemon_mod

    async def _ensure(self, working_dir):
        if raises is not None:
            raise raises
        return socket_path

    monkeypatch.setattr(
        daemon_mod.DaemonSupervisor, "ensure_running", _ensure
    )
    monkeypatch.setattr(mod, "locate_jcode_binary", lambda: binary)
    monkeypatch.setattr(mod, "DaemonSupervisor", daemon_mod.DaemonSupervisor)


def test_missing_session_id_returns_error(monkeypatch):
    h = _make_handler()
    out = asyncio.run(h.process({}, MagicMock()))
    assert out == {"ok": False, "error": "session_id required"}
    out2 = asyncio.run(h.process({"session_id": ""}, MagicMock()))
    assert out2["ok"] is False


def test_no_binary_returns_error(monkeypatch):
    _patch_api_supervisor(monkeypatch, None, binary=None)
    h = _make_handler()
    out = asyncio.run(
        h.process({"session_id": "x", "working_dir": "/tmp"}, MagicMock())
    )
    assert out == {"ok": False, "error": "jcode not installed"}


def test_no_creds_returns_error(monkeypatch):
    _patch_api_supervisor(
        monkeypatch, None, raises=NoCredentialsError("no providers configured")
    )
    h = _make_handler()
    out = asyncio.run(
        h.process({"session_id": "x", "working_dir": "/tmp"}, MagicMock())
    )
    assert out["ok"] is False
    assert "no providers configured" in out["error"]


@pytest.mark.asyncio
async def test_returns_history_summary(monkeypatch, fake_daemon, tmp_path):
    """Drive a real JcodeClient against fake_daemon emitting session+history."""
    # Isolate persistence path -> no global ~/.amplihack writes.
    from usr.plugins.jcode_harness.helpers import paths as paths_mod

    monkeypatch.setattr(paths_mod, "jcode_runtime_dir", lambda: tmp_path)
    monkeypatch.setattr(
        paths_mod,
        "client_instance_persist_path",
        lambda ctx_id, instance_id=None: tmp_path / f"cid_{ctx_id}.json",
    )
    # persistence module imported the symbol by name -> patch there too.
    from usr.plugins.jcode_harness.helpers import persistence as p_mod

    monkeypatch.setattr(
        p_mod,
        "client_instance_persist_path",
        lambda ctx_id, instance_id=None: tmp_path / f"cid_{ctx_id}.json",
    )

    async def script(daemon, reader, writer):
        # subscribe request
        await reader.readline()
        writer.write(b'{"type":"session","session_id":"sess-42"}\n')
        await writer.drain()
        # handler then calls _recv_until(history)
        writer.write(
            b'{"type":"history","id":1,"session_id":"sess-42",'
            b'"messages":[{"r":"u"},{"r":"a"},{"r":"u"},{"r":"a"}]}\n'
        )
        await writer.drain()

    daemon = fake_daemon(script)
    sock = await daemon.start()
    _patch_api_supervisor(monkeypatch, sock)

    h = _make_handler()
    out = await h.process(
        {
            "session_id": "sess-42",
            "working_dir": str(tmp_path),
            "a0_ctx_id": "ctx-test",
        },
        MagicMock(),
    )
    assert out["ok"] is True
    assert out["session_id"] == "sess-42"
    assert out["messages"] == 4


@pytest.mark.asyncio
async def test_uses_persistent_client_instance_id(
    monkeypatch, fake_daemon, tmp_path
):
    """The handler must thread the persisted cid through Subscribe."""
    from usr.plugins.jcode_harness.helpers import paths as paths_mod
    from usr.plugins.jcode_harness.helpers import persistence as p_mod

    monkeypatch.setattr(paths_mod, "jcode_runtime_dir", lambda: tmp_path)
    monkeypatch.setattr(
        paths_mod,
        "client_instance_persist_path",
        lambda ctx_id, instance_id=None: tmp_path / f"cid_{ctx_id}.json",
    )
    monkeypatch.setattr(
        p_mod,
        "client_instance_persist_path",
        lambda ctx_id, instance_id=None: tmp_path / f"cid_{ctx_id}.json",
    )

    captured: dict = {}

    async def script(daemon, reader, writer):
        line = await reader.readline()
        captured["subscribe"] = line.decode()
        writer.write(b'{"type":"session","session_id":"s"}\n')
        await writer.drain()
        writer.write(
            b'{"type":"history","id":1,"session_id":"s","messages":[]}\n'
        )
        await writer.drain()

    daemon = fake_daemon(script)
    sock = await daemon.start()
    _patch_api_supervisor(monkeypatch, sock)

    # Pre-seed a known cid for ctx-stable
    import json as _json

    (tmp_path / "cid_ctx-stable.json").write_text(
        _json.dumps({"client_instance_id": "fixed-cid-9999"})
    )

    h = _make_handler()
    out = await h.process(
        {
            "session_id": "s",
            "working_dir": str(tmp_path),
            "a0_ctx_id": "ctx-stable",
        },
        MagicMock(),
    )
    assert out["ok"] is True
    assert "fixed-cid-9999" in captured["subscribe"]
