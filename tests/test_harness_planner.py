from __future__ import annotations
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest
from usr.plugins.agent_harness.helpers.models import RunRecord, now_iso, new_id


def _make_run(**overrides) -> RunRecord:
    ts = now_iso()
    defaults = {
        "run_id": new_id("run"), "context_id": "ctx-test", "mode": "pro",
        "objective": "Build feature", "phase": "plan", "status": "active",
        "risk_level": "elevated", "created_at": ts, "updated_at": ts,
    }
    defaults.update(overrides)
    return RunRecord(**defaults)


def test_submit_plan_creates_task_graph():
    from usr.plugins.agent_harness.helpers.planner import submit_plan
    run = _make_run()
    graph = submit_plan(run, [
        {"title": "Research", "description": "Read docs", "role": "research"},
        {"title": "Code", "description": "Implement", "role": "code", "depends_on": [0]},
    ])
    assert len(graph.sub_tasks) == 2
    assert graph.sub_tasks[0].id == "st_1"
    assert graph.sub_tasks[1].depends_on == ["st_1"]
    assert run.task_graph is graph


def test_submit_plan_rejects_cycle():
    from usr.plugins.agent_harness.helpers.planner import submit_plan
    run = _make_run()
    with pytest.raises(ValueError, match="cycle"):
        submit_plan(run, [
            {"title": "A", "description": "A", "role": "code", "depends_on": [1]},
            {"title": "B", "description": "B", "role": "code", "depends_on": [0]},
        ])


def test_submit_plan_rejects_invalid_role():
    from usr.plugins.agent_harness.helpers.planner import submit_plan
    run = _make_run()
    with pytest.raises(ValueError, match="role"):
        submit_plan(run, [
            {"title": "Bad", "description": "Bad", "role": "invalid_role"},
        ])


def test_get_ready_tasks_returns_dispatchable():
    from usr.plugins.agent_harness.helpers.planner import submit_plan, get_ready_tasks
    run = _make_run()
    submit_plan(run, [
        {"title": "A", "description": "first", "role": "research"},
        {"title": "B", "description": "second", "role": "code", "depends_on": [0]},
    ])
    ready = get_ready_tasks(run)
    assert len(ready) == 1
    assert ready[0].title == "A"


def test_mark_sub_task_completed():
    from usr.plugins.agent_harness.helpers.planner import submit_plan, mark_sub_task_completed
    run = _make_run()
    submit_plan(run, [
        {"title": "A", "description": "first", "role": "research"},
        {"title": "B", "description": "second", "role": "code", "depends_on": [0]},
    ])
    task = mark_sub_task_completed(run, "st_1", summary="Done", files=["a.py"])
    assert task.status == "completed"
    assert task.result_summary == "Done"
    assert len(run.task_graph.ready_tasks()) == 1


def test_mark_sub_task_failed():
    from usr.plugins.agent_harness.helpers.planner import submit_plan, mark_sub_task_failed
    run = _make_run()
    submit_plan(run, [{"title": "A", "description": "first", "role": "research"}])
    task = mark_sub_task_failed(run, "st_1", error="API unavailable")
    assert task.status == "failed"


def test_mark_sub_task_failed_cascades_to_dependent_tasks():
    from usr.plugins.agent_harness.helpers.planner import submit_plan, mark_sub_task_failed

    run = _make_run()
    submit_plan(run, [
        {"title": "A", "description": "first", "role": "research"},
        {"title": "B", "description": "second", "role": "code", "depends_on": [0]},
        {"title": "C", "description": "third", "role": "verify", "depends_on": [1]},
    ])

    failed = mark_sub_task_failed(run, "st_1", error="API unavailable")

    assert failed.status == "failed"
    assert run.task_graph.sub_tasks[1].status == "failed"
    assert "Blocked by failed dependency" in run.task_graph.sub_tasks[1].result_summary
    assert run.task_graph.sub_tasks[2].status == "failed"
    assert run.task_graph.is_complete() is True


def test_validate_task_graph_catches_bad_dependency_ref():
    from usr.plugins.agent_harness.helpers.planner import submit_plan
    run = _make_run()
    with pytest.raises(ValueError, match="dependency"):
        submit_plan(run, [
            {"title": "A", "description": "first", "role": "code", "depends_on": [99]},
        ])
