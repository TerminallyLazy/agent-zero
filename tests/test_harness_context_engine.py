from __future__ import annotations
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from usr.plugins.agent_harness.helpers.models import (
    RunRecord, ContextPressure, OffloadRecord, WorkspacePaths, now_iso, new_id,
)


def _make_run(**overrides) -> RunRecord:
    ts = now_iso()
    defaults = {
        "run_id": new_id("run"), "context_id": "ctx-test", "mode": "pro",
        "objective": "Test", "phase": "implement", "status": "active",
        "risk_level": "elevated", "created_at": ts, "updated_at": ts,
    }
    defaults.update(overrides)
    return RunRecord(**defaults)


def test_assess_pressure_normal():
    from usr.plugins.agent_harness.helpers.context_engine import assess_pressure_from_tokens
    pressure = assess_pressure_from_tokens(
        estimated_tokens=50000,
        settings={"context_pressure_threshold": 0.7, "context_model_window": 128000},
    )
    assert pressure.status == "normal"


def test_assess_pressure_elevated():
    from usr.plugins.agent_harness.helpers.context_engine import assess_pressure_from_tokens
    pressure = assess_pressure_from_tokens(
        estimated_tokens=95000,
        settings={"context_pressure_threshold": 0.7, "context_model_window": 128000},
    )
    assert pressure.status == "elevated"


def test_assess_pressure_critical():
    from usr.plugins.agent_harness.helpers.context_engine import assess_pressure_from_tokens
    pressure = assess_pressure_from_tokens(
        estimated_tokens=120000,
        settings={"context_pressure_threshold": 0.7, "context_model_window": 128000},
    )
    assert pressure.status == "critical"


def test_should_offload():
    from usr.plugins.agent_harness.helpers.context_engine import should_offload
    normal = ContextPressure(
        estimated_tokens=50000, threshold_pct=0.7,
        status="normal", last_assessed_at=now_iso(),
    )
    assert should_offload(normal) is False
    elevated = ContextPressure(
        estimated_tokens=95000, threshold_pct=0.7,
        status="elevated", last_assessed_at=now_iso(),
    )
    assert should_offload(elevated) is True


def test_offload_content_creates_record(tmp_path):
    from usr.plugins.agent_harness.helpers.context_engine import offload_content
    from usr.plugins.agent_harness.helpers.workspace import ensure_workspace
    run = _make_run()
    run.workspace = ensure_workspace(str(tmp_path))
    record = offload_content(run, "Long content here", "sub_agent_output", sub_task_id="st_1")
    assert record.content_type == "sub_agent_output"
    assert record.sub_task_id == "st_1"
    assert len(run.offloads) == 1
    assert Path(record.file_path).exists()


def test_render_offload_summaries():
    from usr.plugins.agent_harness.helpers.context_engine import render_offload_summaries
    run = _make_run()
    run.offloads = [
        OffloadRecord(
            id="off_1", content_type="research_result",
            file_path="/tmp/off_1.md", summary="API docs summary",
            created_at=now_iso(),
        ),
        OffloadRecord(
            id="off_2", content_type="sub_agent_output",
            file_path="/tmp/off_2.md", summary="Handler code",
            sub_task_id="st_1", created_at=now_iso(),
        ),
    ]
    result = render_offload_summaries(run)
    assert "API docs summary" in result
    assert "/tmp/off_1.md" in result
    assert "Handler code" in result
    lines = [l for l in result.strip().split("\n") if l.strip().startswith("-")]
    assert len(lines) == 2
