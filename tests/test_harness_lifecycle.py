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
        "objective": "Test", "phase": "inspect", "status": "active",
        "risk_level": "elevated", "created_at": ts, "updated_at": ts,
    }
    defaults.update(overrides)
    return RunRecord(**defaults)


def test_create_run_record_sets_correct_phase_per_mode():
    from usr.plugins.agent_harness.helpers.lifecycle import create_run_record
    from usr.plugins.agent_harness.helpers.settings import load_default_settings
    settings = load_default_settings()
    build = create_run_record(context_id="ctx", mode="build", objective="test", constraints=[], settings=settings)
    assert build.phase == "inspect"
    assert build.risk_level == "elevated"
    assist = create_run_record(context_id="ctx", mode="assist", objective="test", constraints=[], settings=settings)
    assert assist.phase == "idle"
    assert assist.risk_level == "low"
    surge = create_run_record(context_id="ctx", mode="surge", objective="test", constraints=[], settings=settings)
    assert surge.phase == "inspect"
    assert surge.risk_level == "high"


def test_record_verification_passed_transitions_to_summarize():
    from usr.plugins.agent_harness.helpers.lifecycle import record_verification
    run = _make_run(phase="implement")
    record_verification(run, name="pytest", status="passed", summary="5 passed")
    assert run.phase == "summarize"


def test_record_verification_failed_transitions_to_repair():
    from usr.plugins.agent_harness.helpers.lifecycle import record_verification
    run = _make_run(phase="implement")
    record_verification(run, name="pytest", status="failed", summary="2 failed")
    assert run.phase == "repair"


def test_upsert_task_creates_and_updates():
    from usr.plugins.agent_harness.helpers.lifecycle import upsert_task
    run = _make_run()
    task = upsert_task(run, title="Fix tests", status="active")
    assert len(run.tasks) == 1
    assert task.title == "Fix tests"
    updated = upsert_task(run, title="Fix tests", status="completed")
    assert len(run.tasks) == 1
    assert updated.status == "completed"


def test_record_failure_respects_repair_limit():
    from usr.plugins.agent_harness.helpers.lifecycle import record_failure
    from usr.plugins.agent_harness.helpers.settings import load_default_settings
    settings = load_default_settings()
    run = _make_run()
    record_failure(run, summary="fail 1", settings=settings)
    assert run.phase == "repair"
    record_failure(run, summary="fail 2", settings=settings)
    assert run.phase == "summarize"


def test_complete_run_sets_completed_state():
    from usr.plugins.agent_harness.helpers.lifecycle import complete_run
    run = _make_run(phase="summarize")
    complete_run(run)
    assert run.phase == "complete"
    assert run.status == "completed"
    assert run.completed_at != ""


def test_complete_run_does_not_complete_blocked_run():
    from usr.plugins.agent_harness.helpers.lifecycle import complete_run
    run = _make_run(phase="blocked", status="blocked")
    complete_run(run)
    assert run.status == "blocked"


def test_record_tool_activity_tracks_text_editor_files():
    from usr.plugins.agent_harness.helpers.lifecycle import record_tool_activity
    run = _make_run()
    record_tool_activity(run=run, tool_name="text_editor", tool_args={"path": "/tmp/a.py"})
    assert "/tmp/a.py" in run.touched_files
    assert run.phase == "implement"


def test_record_tool_activity_parses_verification_with_structured_regex():
    from usr.plugins.agent_harness.helpers.lifecycle import record_tool_activity
    run = _make_run()
    record_tool_activity(
        run=run, tool_name="code_execution_tool",
        tool_args={"runtime": "terminal", "code": "pytest tests/"},
        tool_response="collected 10 items\n....\n10 passed, 0 failed in 1.5s",
    )
    assert run.phase == "summarize"
    assert run.verification[-1].status == "passed"

    run2 = _make_run()
    record_tool_activity(
        run=run2, tool_name="code_execution_tool",
        tool_args={"runtime": "terminal", "code": "pytest tests/"},
        tool_response="collected 5 items\n..F.\n4 passed, 1 failed in 0.8s",
    )
    assert run2.phase == "repair"
    assert run2.verification[-1].status == "failed"


def test_set_active_state_respects_task_graph():
    from usr.plugins.agent_harness.helpers.lifecycle import _set_active_state
    from usr.plugins.agent_harness.helpers.planner import submit_plan

    # With task graph and pending tasks -> implement
    run = _make_run(phase="blocked", status="blocked")
    submit_plan(run, [{"title": "A", "description": "a", "role": "code"}])
    _set_active_state(run)
    assert run.phase == "implement"
    assert run.status == "active"

    # In plan phase with no graph -> stay in plan
    run2 = _make_run(phase="plan", status="blocked")
    _set_active_state(run2)
    assert run2.phase == "plan"
    assert run2.status == "active"
