from __future__ import annotations
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from usr.plugins.agent_harness.helpers.models import RunRecord, now_iso, new_id


def _make_run(**overrides) -> RunRecord:
    ts = now_iso()
    defaults = {
        "run_id": new_id("run"), "context_id": "ctx-test", "mode": "surge",
        "objective": "Ship it", "phase": "implement", "status": "active",
        "risk_level": "high", "created_at": ts, "updated_at": ts,
    }
    defaults.update(overrides)
    return RunRecord(**defaults)


def _default_settings():
    from usr.plugins.agent_harness.helpers.settings import load_default_settings
    return load_default_settings()


def test_render_system_prompt_surge_mode():
    from usr.plugins.agent_harness.helpers.renderer import render_system_prompt
    run = _make_run()
    prompt = render_system_prompt(
        settings=_default_settings(), run=run,
        accepted_rules=[{"rule_text": "Always verify"}],
    )
    assert "SURGE MODE" in prompt
    assert "Ship it" in prompt
    assert "Always verify" in prompt
    assert "max 4 concurrent subagents" in prompt


def test_render_system_prompt_ambient_assist():
    from usr.plugins.agent_harness.helpers.renderer import render_system_prompt
    prompt = render_system_prompt(
        settings=_default_settings(), run=None, accepted_rules=[],
    )
    assert "AMBIENT ASSIST" in prompt


def test_render_system_prompt_empty_when_ambient_disabled():
    from usr.plugins.agent_harness.helpers.renderer import render_system_prompt
    settings = _default_settings()
    settings["ambient_assist_enabled"] = False
    prompt = render_system_prompt(settings=settings, run=None, accepted_rules=[])
    assert prompt == ""


def test_render_runtime_summary():
    from usr.plugins.agent_harness.helpers.renderer import render_runtime_summary
    run = _make_run()
    summary = render_runtime_summary(run)
    assert "mode: surge" in summary
    assert "objective: Ship it" in summary


def test_render_runtime_summary_returns_empty_for_none():
    from usr.plugins.agent_harness.helpers.renderer import render_runtime_summary
    assert render_runtime_summary(None) == ""
