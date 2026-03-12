"""
Integration tests for QMDClient.

These tests require:
  - node on PATH
  - @tobilu/qmd installed (bridge/node_modules present)

Run with:
  python3 -m pytest tests/test_qmd_client.py -v
"""

import sys
import os
import asyncio
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest
from usr.plugins.qmd.helpers.qmd_client import QMDClient


# ---------------------------------------------------------------------------
# Shared fixture: a temp db path so each test gets an isolated store
# ---------------------------------------------------------------------------

@pytest.fixture
def db_path(tmp_path):
    """Return a path to a temp SQLite file for the QMD store."""
    return str(tmp_path / "test.sqlite")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ping_roundtrip(db_path):
    """Start client, ping, verify ok=True, stop cleanly."""
    client = QMDClient()
    await client.start(db_path=db_path)
    result = await client.call("ping")
    assert result.get("ok") is True
    await client.stop()
    assert not client.is_running()


@pytest.mark.asyncio
async def test_stop_is_clean(db_path):
    """Start then stop; is_running should be False."""
    client = QMDClient()
    await client.start(db_path=db_path)
    assert client.is_running()
    await client.stop()
    assert not client.is_running()


@pytest.mark.asyncio
async def test_auto_respawn(db_path):
    """Kill the subprocess; next call should auto-respawn."""
    client = QMDClient()
    await client.start(db_path=db_path)
    # Kill proc directly
    client._proc.kill()
    await asyncio.sleep(0.1)
    # Next call should respawn (auto-respawn uses start() with no db_path,
    # so use db_path env to keep the same store)
    os.environ["QMD_DB_PATH"] = db_path
    try:
        result = await client.call("ping")
        assert result.get("ok") is True
    finally:
        del os.environ["QMD_DB_PATH"]
        await client.stop()


@pytest.mark.asyncio
async def test_gating_blocks_management():
    """Gated call with management_enabled=False returns error, no bridge needed."""
    client = QMDClient()
    # No start() — gating check happens before bridge call
    result = await client.call("collection_add", gated=True, management_enabled=False)
    assert "error" in result
    assert "disabled" in result["error"].lower()


@pytest.mark.asyncio
async def test_gating_allows_when_enabled(db_path):
    """Gated call with management_enabled=True should reach the bridge."""
    client = QMDClient()
    await client.start(db_path=db_path)
    # collection_add will fail (no path param) but it should reach the bridge,
    # not be blocked by gating
    result = await client.call(
        "collection_add",
        params={"_management_enabled": True},
        gated=True,
        management_enabled=True,
    )
    # Should get a bridge-level error or result, not a gating error
    if "error" in result:
        assert "disabled" not in result["error"].lower()  # not a gating error
    await client.stop()
