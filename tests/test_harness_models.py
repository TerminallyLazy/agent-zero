from __future__ import annotations
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def test_models_module_exports_all_pydantic_models():
    from usr.plugins.agent_harness.helpers.models import (
        TaskRecord,
        CheckpointRecord,
        VerificationRecord,
        FailureRecord,
        MemoryCandidate,
        RunRecord,
    )
    import re
    from usr.plugins.agent_harness.helpers.models import (
        HarnessMode,
        HarnessPhase,
        RiskLevel,
        RunStatus,
        CheckpointStatus,
        MemoryScope,
        MemoryCandidateStatus,
        VerificationStatus,
        DEPENDENCY_INSTALL_RE,
        DESTRUCTIVE_COMMAND_RE,
        VERIFICATION_COMMAND_RE,
        PLUGIN_NAME,
        RUN_CONTEXT_KEY,
        OUTPUT_CONTEXT_KEY,
        DEFAULT_RUN_OBJECTIVE,
        DEFAULT_DEEP_MODE,
        now_iso,
        new_id,
    )
    assert PLUGIN_NAME == "agent_harness"
    assert isinstance(DEPENDENCY_INSTALL_RE, re.Pattern)
    assert now_iso()
    assert new_id("test").startswith("test_")


def test_run_record_round_trips_through_model_dump():
    from usr.plugins.agent_harness.helpers.models import RunRecord, now_iso, new_id

    ts = now_iso()
    run = RunRecord(
        run_id=new_id("run"),
        context_id="ctx-test",
        mode="pro",
        objective="Test objective",
        phase="inspect",
        status="active",
        risk_level="elevated",
        created_at=ts,
        updated_at=ts,
    )
    data = run.model_dump()
    restored = RunRecord.model_validate(data)
    assert restored.run_id == run.run_id
    assert restored.mode == "pro"


def test_sub_task_and_task_graph_models():
    from usr.plugins.agent_harness.helpers.models import (
        SubTask, TaskGraph, SubTaskRole, SubTaskStatus, now_iso, new_id,
    )
    st1 = SubTask(id="st_1", title="Research API", description="Look up docs", role="research")
    st2 = SubTask(id="st_2", title="Implement", description="Write code", role="code", depends_on=["st_1"])
    graph = TaskGraph(objective="Build feature", sub_tasks=[st1, st2], created_at=now_iso())
    assert graph.ready_tasks() == [st1]
    assert graph.is_complete() is False
    st1.status = "completed"
    assert graph.ready_tasks() == [st2]
    st2.status = "completed"
    assert graph.is_complete() is True


def test_task_graph_has_cycle_detects_circular():
    from usr.plugins.agent_harness.helpers.models import SubTask, TaskGraph, now_iso
    st1 = SubTask(id="st_1", title="A", description="A", role="code", depends_on=["st_2"])
    st2 = SubTask(id="st_2", title="B", description="B", role="code", depends_on=["st_1"])
    graph = TaskGraph(objective="Cycle", sub_tasks=[st1, st2], created_at=now_iso())
    assert graph.has_cycle() is True


def test_task_graph_no_cycle():
    from usr.plugins.agent_harness.helpers.models import SubTask, TaskGraph, now_iso
    st1 = SubTask(id="st_1", title="A", description="A", role="research")
    st2 = SubTask(id="st_2", title="B", description="B", role="code", depends_on=["st_1"])
    graph = TaskGraph(objective="Linear", sub_tasks=[st1, st2], created_at=now_iso())
    assert graph.has_cycle() is False


def test_run_record_has_task_graph_field():
    from usr.plugins.agent_harness.helpers.models import RunRecord, now_iso, new_id
    ts = now_iso()
    run = RunRecord(
        run_id=new_id("run"), context_id="ctx", mode="pro", objective="test",
        phase="plan", status="active", risk_level="elevated",
        created_at=ts, updated_at=ts,
    )
    assert run.task_graph is None


def test_checkpoint_record_has_sub_task_id():
    from usr.plugins.agent_harness.helpers.models import CheckpointRecord, now_iso
    chk = CheckpointRecord(
        id="chk_1", reason="test", proposed_action="test",
        sub_task_id="st_1", created_at=now_iso(),
    )
    assert chk.sub_task_id == "st_1"
