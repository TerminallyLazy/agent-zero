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
        mode="build",
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
    assert restored.mode == "build"
