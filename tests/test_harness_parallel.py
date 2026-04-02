from __future__ import annotations
import sys
import time
import threading
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent import AgentContext
from initialize import initialize_agent
from usr.plugins.agent_harness.helpers.models import RunRecord, SubTask, TaskGraph, now_iso, new_id


def _make_run_with_graph() -> RunRecord:
    ts = now_iso()
    run = RunRecord(
        run_id=new_id("run"), context_id="ctx-test", mode="ultra",
        objective="Build feature", phase="implement", status="active",
        risk_level="elevated", created_at=ts, updated_at=ts,
    )
    st1 = SubTask(id="st_1", title="Research", description="Read docs", role="research")
    st2 = SubTask(id="st_2", title="Code", description="Write it", role="code", depends_on=["st_1"])
    run.task_graph = TaskGraph(objective=run.objective, sub_tasks=[st1, st2], created_at=ts)
    return run


def test_registry_starts_empty():
    from usr.plugins.agent_harness.helpers.parallel import poll_status
    status = poll_status("nonexistent-run-id")
    assert status == {}


def test_spawn_parallel_creates_background_tasks():
    from usr.plugins.agent_harness.helpers.parallel import (
        spawn_parallel, poll_status, kill_all,
    )
    from usr.plugins.agent_harness.helpers.settings import load_default_settings

    run = _make_run_with_graph()
    settings = load_default_settings()
    # Mark st_1 as ready (it has no dependencies)
    ready = [run.task_graph.sub_tasks[0]]

    spawned = spawn_parallel(run, ready, settings)
    assert len(spawned) == 1
    assert spawned[0] == "st_1"

    status = poll_status(run.run_id)
    assert "st_1" in status
    assert status["st_1"] in ("running", "completed", "failed")

    # Clean up
    killed = kill_all(run.run_id)
    assert killed >= 1


def test_kill_all_cleans_up():
    from usr.plugins.agent_harness.helpers.parallel import (
        spawn_parallel, poll_status, kill_all,
    )
    from usr.plugins.agent_harness.helpers.settings import load_default_settings

    run = _make_run_with_graph()
    settings = load_default_settings()
    ready = [run.task_graph.sub_tasks[0]]
    spawn_parallel(run, ready, settings)

    killed = kill_all(run.run_id)
    assert killed >= 1

    status = poll_status(run.run_id)
    assert status == {}


def test_collect_completed_harvests_finished_tasks():
    from usr.plugins.agent_harness.helpers.parallel import (
        spawn_parallel, collect_completed, kill_all, poll_status,
    )
    from usr.plugins.agent_harness.helpers.settings import load_default_settings

    run = _make_run_with_graph()
    settings = load_default_settings()
    ready = [run.task_graph.sub_tasks[0]]
    spawn_parallel(run, ready, settings)

    # Wait briefly for the background agent to finish (it will likely error/complete quickly
    # since there's no real LLM, but the task should become "ready")
    time.sleep(2)

    # Collect whatever finished
    results = collect_completed(run)
    # Results is a list of (sub_task_id, summary_or_none, error_or_none) tuples
    # We don't assert specific results since the agent has no LLM configured,
    # but the function should not raise
    assert isinstance(results, list)

    # Clean up any remaining
    kill_all(run.run_id)


def test_spawn_parallel_tolerates_noncopyable_parent_context_data():
    from usr.plugins.agent_harness.helpers.parallel import (
        spawn_parallel, poll_status, kill_all,
    )
    from usr.plugins.agent_harness.helpers.settings import load_default_settings

    run = _make_run_with_graph()
    settings = load_default_settings()
    ready = [run.task_graph.sub_tasks[0]]
    parent_context = AgentContext(config=initialize_agent(), set_current=False)
    parent_context.set_data("chat_model_override", {"provider": "openrouter", "name": "test"})
    parent_context.set_data("uncopyable", threading.Lock())

    spawned = spawn_parallel(run, ready, settings, parent_context=parent_context)
    assert spawned == ["st_1"]

    status = poll_status(run.run_id)
    assert status["st_1"] in ("running", "completed", "failed")

    kill_all(run.run_id)
