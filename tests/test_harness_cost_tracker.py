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
        "run_id": new_id("run"), "context_id": "ctx-test", "mode": "build",
        "objective": "Test", "phase": "implement", "status": "active",
        "risk_level": "elevated", "created_at": ts, "updated_at": ts,
    }
    defaults.update(overrides)
    return RunRecord(**defaults)


def test_record_usage_creates_cost_record():
    from usr.plugins.agent_harness.helpers.cost_tracker import record_usage
    run = _make_run()
    cost = record_usage(run, prompt_tokens=100, completion_tokens=50)
    assert cost.usage.prompt_tokens == 100
    assert cost.usage.completion_tokens == 50
    assert run.cost is cost


def test_record_usage_accumulates():
    from usr.plugins.agent_harness.helpers.cost_tracker import record_usage
    run = _make_run()
    record_usage(run, prompt_tokens=100, completion_tokens=50)
    record_usage(run, prompt_tokens=200, completion_tokens=100)
    assert run.cost.usage.prompt_tokens == 300
    assert run.cost.usage.completion_tokens == 150
    assert run.cost.usage.total_tokens == 450


def test_record_usage_tracks_per_sub_task():
    from usr.plugins.agent_harness.helpers.cost_tracker import record_usage
    run = _make_run()
    record_usage(run, prompt_tokens=100, completion_tokens=50, sub_task_id="st_1")
    record_usage(run, prompt_tokens=200, completion_tokens=100, sub_task_id="st_1")
    assert run.cost.sub_task_usage["st_1"].prompt_tokens == 300


def test_check_budget_returns_false_when_unlimited():
    from usr.plugins.agent_harness.helpers.cost_tracker import record_usage, check_budget
    run = _make_run()
    record_usage(run, prompt_tokens=999999, completion_tokens=999999)
    assert check_budget(run, {"token_budget": 0}) is False


def test_check_budget_returns_true_when_exhausted():
    from usr.plugins.agent_harness.helpers.cost_tracker import record_usage, check_budget
    run = _make_run()
    record_usage(run, prompt_tokens=5000, completion_tokens=5000)
    assert check_budget(run, {"token_budget": 1000}) is True


def test_render_cost_summary():
    from usr.plugins.agent_harness.helpers.cost_tracker import record_usage, render_cost_summary
    run = _make_run()
    record_usage(run, prompt_tokens=100, completion_tokens=50)
    summary = render_cost_summary(run)
    assert "150" in summary
