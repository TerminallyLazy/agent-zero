from __future__ import annotations

import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent import AgentContext
from initialize import initialize_agent
from usr.plugins.agent_harness.helpers import runtime as harness_runtime
from usr.plugins.agent_harness.helpers.models import now_iso, new_id
from usr.plugins.agent_harness.helpers.planner import submit_plan, mark_sub_task_failed
from usr.plugins.agent_harness.tools.harness_run import HarnessRun


def _new_context() -> AgentContext:
    return AgentContext(config=initialize_agent(), set_current=False)


def _make_run_with_graph():
    ts = now_iso()
    run = harness_runtime.RunRecord(
        run_id=new_id("run"),
        context_id="ctx-tool",
        mode="ultra",
        objective="Build feature",
        phase="implement",
        status="active",
        risk_level="elevated",
        created_at=ts,
        updated_at=ts,
    )
    submit_plan(run, [
        {"title": "Research API", "description": "Read docs", "role": "research"},
        {"title": "Implement code", "description": "Write code", "role": "code", "depends_on": [0]},
    ])
    return run


def _run(awaitable):
    return asyncio.run(awaitable)


def test_dispatch_failure_keeps_tasks_pending_and_records_failure(monkeypatch):
    context = _new_context()
    run = _make_run_with_graph()
    harness_runtime.save_current_run(context, run)
    tool = HarnessRun(context.agent0, "harness_run", None, {}, "", None)

    def _boom(*args, **kwargs):
        raise RuntimeError("sub-agent API failed")

    monkeypatch.setattr(
        "usr.plugins.agent_harness.helpers.parallel.spawn_parallel",
        _boom,
    )

    response = _run(tool.execute(action="dispatch"))
    assert "Sub-agent dispatch failed" in response.message

    refreshed = harness_runtime.get_current_run(context)
    assert refreshed is not None
    assert refreshed.task_graph is not None
    assert refreshed.task_graph.sub_tasks[0].status == "pending"
    assert refreshed.failures[-1].summary == "Sub-agent dispatch failed: sub-agent API failed"


def test_collect_recovers_orphaned_dispatched_tasks():
    context = _new_context()
    run = _make_run_with_graph()
    run.task_graph.sub_tasks[0].status = "dispatched"
    run.task_graph.sub_tasks[0].dispatched_at = now_iso()
    harness_runtime.save_current_run(context, run)
    tool = HarnessRun(context.agent0, "harness_run", None, {}, "", None)

    response = _run(tool.execute(action="collect"))
    assert "ready to dispatch" in response.message

    refreshed = harness_runtime.get_current_run(context)
    assert refreshed is not None
    assert refreshed.task_graph is not None
    assert refreshed.task_graph.sub_tasks[0].status == "pending"


def test_adopt_action_reconciles_manual_takeover_and_allows_completion():
    context = _new_context()
    run = _make_run_with_graph()
    mark_sub_task_failed(run, "st_1", error="sub-agent API failed")
    harness_runtime.save_current_run(context, run)
    tool = HarnessRun(context.agent0, "harness_run", None, {}, "", None)

    response = _run(
        tool.execute(
            action="adopt",
            sub_task_id="st_2",
            summary="Implemented manually after sub-agent outage.",
            result_files=["usr/plugins/agent_harness/helpers/example.py"],
        )
    )
    assert "adopted into the main agent flow" in response.message

    refreshed = harness_runtime.get_current_run(context)
    assert refreshed is not None
    assert refreshed.task_graph is not None
    assert refreshed.task_graph.sub_tasks[1].status == "completed"
    assert refreshed.task_graph.sub_tasks[1].result_summary == "Implemented manually after sub-agent outage."

    completion = _run(tool.execute(action="complete"))
    assert "Harness run completed" in completion.message
