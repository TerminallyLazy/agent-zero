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


@pytest.mark.asyncio
async def test_health_check_handler_returns_structured_result():
    from usr.plugins.headless_mode.api.health_check import HealthCheck

    handler = HealthCheck.__new__(HealthCheck)

    with patch(
        "usr.plugins.headless_mode.api.health_check.run_cli_subprocess",
        new_callable=AsyncMock,
        side_effect=[
            (True, "usage: cli ...", ""),
            (True, '{"response":"pong","context":"c1","log":{}}', ""),
        ],
    ), patch(
        "usr.plugins.headless_mode.api.health_check.plugins"
    ) as mock_plugins:
        mock_plugins.get_plugin_config.return_value = {}
        result = await handler.process({}, MagicMock())

    assert result["ok"] is True
    assert result["cli_help_ok"] is True
    assert result["ephemeral_ok"] is True
    assert "timestamp" in result
    mock_plugins.save_plugin_config.assert_called_once()
    call_args = mock_plugins.save_plugin_config.call_args[0]
    assert call_args[0] == "headless_mode"
    assert call_args[1] == ""
    assert call_args[2] == ""
    assert "last_health_check" in call_args[3]


@pytest.mark.asyncio
async def test_health_check_handler_persists_to_config():
    from usr.plugins.headless_mode.api.health_check import HealthCheck

    handler = HealthCheck.__new__(HealthCheck)
    existing_cfg = {"interactive_prompt": "> ", "exit_commands": ["exit"]}

    with patch(
        "usr.plugins.headless_mode.api.health_check.run_cli_subprocess",
        new_callable=AsyncMock,
        side_effect=[
            (True, "ok", ""),
            (True, '{"response":"ok","context":"c1","log":{}}', ""),
        ],
    ), patch(
        "usr.plugins.headless_mode.api.health_check.plugins"
    ) as mock_plugins:
        mock_plugins.get_plugin_config.return_value = existing_cfg.copy()
        result = await handler.process({}, MagicMock())

    saved = mock_plugins.save_plugin_config.call_args[0][3]
    assert saved["last_health_check"]["ok"] is True
    assert saved["interactive_prompt"] == "> "


@pytest.mark.asyncio
async def test_health_check_handler_timeout():
    from usr.plugins.headless_mode.api.health_check import HealthCheck

    handler = HealthCheck.__new__(HealthCheck)

    with patch(
        "usr.plugins.headless_mode.api.health_check.run_cli_subprocess",
        new_callable=AsyncMock,
        side_effect=[
            (False, "", "Timed out after 60s"),
        ],
    ), patch(
        "usr.plugins.headless_mode.api.health_check.plugins"
    ) as mock_plugins:
        mock_plugins.get_plugin_config.return_value = {}
        result = await handler.process({}, MagicMock())

    assert result["ok"] is False
    assert "Timed out" in result["details"]


@pytest.mark.asyncio
async def test_dependency_status_all_passing():
    from usr.plugins.headless_mode.api.dependency_status import DependencyStatus

    handler = DependencyStatus.__new__(DependencyStatus)

    with patch(
        "usr.plugins.headless_mode.api.dependency_status.plugins"
    ) as mock_plugins, patch(
        "usr.plugins.headless_mode.api.dependency_status._check_framework_imports",
        return_value={"name": "Framework Imports", "ok": True, "detail": "all 3 modules importable"},
    ), patch(
        "usr.plugins.headless_mode.api.dependency_status._check_environment",
        return_value={"name": "Environment", "ok": True, "detail": ".env loaded, 2 keys present"},
    ), patch(
        "usr.plugins.headless_mode.api.dependency_status._check_mcp",
        return_value={"name": "MCP Servers", "ok": True, "detail": "2 servers configured"},
    ):
        mock_plugins.get_plugin_config.return_value = {}
        result = await handler.process({}, MagicMock())

    assert result["ok"] is True
    assert len(result["results"]) == 4
    assert all(r["ok"] for r in result["results"])
    assert "timestamp" in result


@pytest.mark.asyncio
async def test_dependency_status_partial_failure():
    from usr.plugins.headless_mode.api.dependency_status import DependencyStatus

    handler = DependencyStatus.__new__(DependencyStatus)

    with patch(
        "usr.plugins.headless_mode.api.dependency_status.plugins"
    ) as mock_plugins, patch(
        "usr.plugins.headless_mode.api.dependency_status._check_framework_imports",
        return_value={"name": "Framework Imports", "ok": False, "detail": "initialize not importable"},
    ), patch(
        "usr.plugins.headless_mode.api.dependency_status._check_environment",
        return_value={"name": "Environment", "ok": True, "detail": ".env loaded"},
    ), patch(
        "usr.plugins.headless_mode.api.dependency_status._check_mcp",
        return_value={"name": "MCP Servers", "ok": True, "detail": "0 servers"},
    ):
        mock_plugins.get_plugin_config.return_value = {}
        result = await handler.process({}, MagicMock())

    assert result["ok"] is False
    failed = [r for r in result["results"] if not r["ok"]]
    assert len(failed) == 1
    assert failed[0]["name"] == "Framework Imports"


@pytest.mark.asyncio
async def test_run_message_returns_response():
    from usr.plugins.headless_mode.api.run_message import RunMessage

    handler = RunMessage.__new__(RunMessage)
    subprocess_json = json.dumps({"response": "hello back", "context": "ctx-abc", "log": {}})

    with patch(
        "usr.plugins.headless_mode.api.run_message.run_cli_subprocess",
        new_callable=AsyncMock,
        return_value=(True, subprocess_json, ""),
    ):
        result = await handler.process({"message": "hello"}, MagicMock())

    assert result["ok"] is True
    assert result["response"] == "hello back"
    assert result["context_id"] == "ctx-abc"
    assert result["error"] is None


@pytest.mark.asyncio
async def test_run_message_rejects_empty_input():
    from usr.plugins.headless_mode.api.run_message import RunMessage

    handler = RunMessage.__new__(RunMessage)
    result = await handler.process({"message": ""}, MagicMock())

    assert result["ok"] is False
    assert "empty" in result["error"].lower() or "required" in result["error"].lower()


@pytest.mark.asyncio
async def test_run_message_caps_timeout():
    from usr.plugins.headless_mode.api.run_message import RunMessage

    handler = RunMessage.__new__(RunMessage)
    subprocess_json = json.dumps({"response": "ok", "context": "c1", "log": {}})

    with patch(
        "usr.plugins.headless_mode.api.run_message.run_cli_subprocess",
        new_callable=AsyncMock,
        return_value=(True, subprocess_json, ""),
    ) as mock_run:
        await handler.process({"message": "test", "timeout": 9999}, MagicMock())

    # Verify timeout was clamped to 300
    call_kwargs = mock_run.call_args
    assert call_kwargs[1]["timeout"] == 300 or call_kwargs[0][1] == 300
