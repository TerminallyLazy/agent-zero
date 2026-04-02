from __future__ import annotations
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from usr.plugins.agent_harness.helpers.models import RunRecord, now_iso, new_id
from usr.plugins.agent_harness.helpers.planner import submit_plan


def _make_run_with_graph() -> RunRecord:
    ts = now_iso()
    run = RunRecord(
        run_id=new_id("run"), context_id="ctx", mode="ultra",
        objective="Build feature", phase="implement", status="active",
        risk_level="elevated", created_at=ts, updated_at=ts,
    )
    submit_plan(run, [
        {"title": "Research API", "description": "Read Stripe docs", "role": "research"},
        {"title": "Implement webhook", "description": "Write handler", "role": "code", "depends_on": [0]},
        {"title": "Write tests", "description": "Test handler", "role": "verify", "depends_on": [1]},
    ])
    return run


def test_build_scoped_context_includes_task_description():
    from usr.plugins.agent_harness.helpers.orchestrator import build_scoped_context
    run = _make_run_with_graph()
    context = build_scoped_context(run.task_graph.sub_tasks[0], run)
    assert "Read Stripe docs" in context
    assert "Research API" in context


def test_build_scoped_context_includes_dependency_results():
    from usr.plugins.agent_harness.helpers.orchestrator import build_scoped_context
    from usr.plugins.agent_harness.helpers.planner import mark_sub_task_completed
    run = _make_run_with_graph()
    mark_sub_task_completed(run, "st_1", summary="Stripe uses POST /webhooks")
    context = build_scoped_context(run.task_graph.sub_tasks[1], run)
    assert "Stripe uses POST /webhooks" in context


def test_can_dispatch_respects_subagent_limit():
    from usr.plugins.agent_harness.helpers.orchestrator import can_dispatch
    from usr.plugins.agent_harness.helpers.settings import load_default_settings
    run = _make_run_with_graph()
    settings = load_default_settings()
    assert can_dispatch(run, settings) is True
    run.task_graph.sub_tasks[0].status = "dispatched"
    run.task_graph.sub_tasks[1].status = "dispatched"
    run.task_graph.sub_tasks[2].status = "dispatched"
    assert can_dispatch(run, settings) is False


def test_dispatch_ready_tasks_returns_ready_tasks_without_mutating_status():
    from usr.plugins.agent_harness.helpers.orchestrator import dispatch_ready_tasks
    from usr.plugins.agent_harness.helpers.settings import load_default_settings
    run = _make_run_with_graph()
    settings = load_default_settings()
    dispatched = dispatch_ready_tasks(run, settings)
    assert len(dispatched) == 1
    assert dispatched[0].title == "Research API"
    assert dispatched[0].status == "pending"


def test_record_dispatch_result_updates_graph():
    from usr.plugins.agent_harness.helpers.orchestrator import dispatch_ready_tasks, record_dispatch_result
    from usr.plugins.agent_harness.helpers.settings import load_default_settings
    run = _make_run_with_graph()
    settings = load_default_settings()
    dispatch_ready_tasks(run, settings)
    task = record_dispatch_result(run, "st_1", {
        "summary": "Found the API docs",
        "files": ["docs/stripe.md"],
    })
    assert task.status == "completed"
    assert task.result_summary == "Found the API docs"


def test_synthesize_results_combines_summaries():
    from usr.plugins.agent_harness.helpers.orchestrator import synthesize_results
    from usr.plugins.agent_harness.helpers.planner import mark_sub_task_completed
    run = _make_run_with_graph()
    mark_sub_task_completed(run, "st_1", summary="API uses webhooks")
    mark_sub_task_completed(run, "st_2", summary="Handler implemented")
    mark_sub_task_completed(run, "st_3", summary="Tests passing")
    result = synthesize_results(run)
    assert "API uses webhooks" in result
    assert "Handler implemented" in result
    assert "Tests passing" in result
