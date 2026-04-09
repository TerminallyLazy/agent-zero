"""Tests for headless_mode plugin UI API handlers and helpers."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.mark.asyncio
async def test_run_cli_subprocess_returns_stdout_on_success():
    from usr.plugins.headless_mode.helpers.subprocess_run import run_cli_subprocess

    mock_proc = AsyncMock()
    mock_proc.communicate = AsyncMock(return_value=(b"hello output", b""))
    mock_proc.returncode = 0

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
        ok, stdout, stderr = await run_cli_subprocess(["--help"], timeout=10)

    assert ok is True
    assert stdout == "hello output"
    assert stderr == ""
    call_args = mock_exec.call_args[0]
    assert call_args[0] == sys.executable


@pytest.mark.asyncio
async def test_run_cli_subprocess_returns_error_on_nonzero_exit():
    from usr.plugins.headless_mode.helpers.subprocess_run import run_cli_subprocess

    mock_proc = AsyncMock()
    mock_proc.communicate = AsyncMock(return_value=(b"", b"some error"))
    mock_proc.returncode = 1

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        ok, stdout, stderr = await run_cli_subprocess(["--message", "x"], timeout=10)

    assert ok is False
    assert stderr == "some error"


@pytest.mark.asyncio
async def test_run_cli_subprocess_handles_timeout():
    from usr.plugins.headless_mode.helpers.subprocess_run import run_cli_subprocess

    mock_proc = AsyncMock()
    mock_proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError())
    mock_proc.kill = MagicMock()
    mock_proc.wait = AsyncMock()

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        ok, stdout, stderr = await run_cli_subprocess(["--message", "x"], timeout=1)

    assert ok is False
    assert "Timed out" in stderr
    mock_proc.kill.assert_called_once()
