from __future__ import annotations
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def test_phase3_models_importable():
    from usr.plugins.agent_harness.helpers.models import (
        ContextStatus, ContextPressure, OffloadRecord,
        TokenUsage, CostRecord, WorkspacePaths,
    )
    pressure = ContextPressure(
        estimated_tokens=50000, threshold_pct=0.7,
        status="normal", last_assessed_at="2026-01-01T00:00:00Z",
    )
    assert pressure.status == "normal"

    usage = TokenUsage(prompt_tokens=100, completion_tokens=50)
    assert usage.total_tokens == 0  # manually set, not auto-computed


def test_run_record_has_phase3_fields():
    from usr.plugins.agent_harness.helpers.models import RunRecord, now_iso, new_id
    ts = now_iso()
    run = RunRecord(
        run_id=new_id("run"), context_id="ctx", mode="pro", objective="test",
        phase="implement", status="active", risk_level="elevated",
        created_at=ts, updated_at=ts,
    )
    assert run.offloads == []
    assert run.cost is None
    assert run.workspace is None
