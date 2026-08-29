"""Focused Phase 0 runtime-boundary regression tests."""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from usr.plugins.dspy_rlm.api.optimize import Optimize
from usr.plugins.dspy_rlm.helpers import config as config_module
from usr.plugins.dspy_rlm.helpers import optimizer
from usr.plugins.dspy_rlm.helpers import telemetry


def _enabled_config(**optimization: Any) -> dict[str, Any]:
    return {
        "enabled": True,
        "optimization": {"enabled": True, **optimization},
    }


def test_normalization_fallback_is_inert_when_default_file_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config_module, "_load_default", lambda: {})

    cfg = config_module.normalize_config(None)

    assert cfg["enabled"] is False
    assert cfg["instrumentation_enabled"] is False
    assert cfg["optimization"]["enabled"] is False
    assert cfg["optimization"]["auto_optimize"] is False
    assert cfg["prompt"]["inject_guidance"] is False
    assert cfg["prompt"]["fallback_guidance"] == ""
    assert cfg["telemetry"] == {"enabled": False, "trace_to_runtime": False}


def test_nested_telemetry_settings_are_preserved() -> None:
    cfg = config_module.normalize_config(
        {"telemetry": {"enabled": True, "trace_to_runtime": True}}
    )

    assert cfg["telemetry"] == {"enabled": True, "trace_to_runtime": True}


def test_optimizer_force_cannot_bypass_disabled_capability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mark_started = pytest.fail
    monkeypatch.setattr(optimizer.state_module, "mark_optimization_started", mark_started)

    result = optimizer.run_optimization_sync("ctx-1", _enabled_config(enabled=False), force=True)

    assert result["status"] == "skipped"
    assert result["reason"] == "optimization_disabled"


@pytest.mark.asyncio
async def test_optimize_api_force_cannot_bypass_disabled_capability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        config_module,
        "load_config",
        lambda *args, **kwargs: _enabled_config(enabled=False),
    )
    from usr.plugins.dspy_rlm.api import status as status_module
    monkeypatch.setattr(status_module.AgentContext, "get", lambda _context_id: SimpleNamespace(id="ctx-1", agent0=object()))

    handler = object.__new__(Optimize)
    result = await handler.process({"context_id": "ctx-1", "force": True}, None)

    assert result["ok"] is False
    assert result["result"]["reason"] == "optimization_disabled"


def test_telemetry_uses_a_context_data_mapping() -> None:
    context = SimpleNamespace(data={})

    event = telemetry.append_tool_event(context, "shell", args={"command": "echo ok"})

    assert event["tool_name"] == "shell"
    assert telemetry.collect_tool_events(context) == [event]
    assert telemetry.pop_tool_events(context) == [event]
    assert telemetry.collect_tool_events(context) == []
