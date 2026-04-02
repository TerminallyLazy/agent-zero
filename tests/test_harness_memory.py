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
        "run_id": new_id("run"), "context_id": "ctx-test", "mode": "pro",
        "objective": "Test", "phase": "inspect", "status": "active",
        "risk_level": "elevated", "created_at": ts, "updated_at": ts,
    }
    defaults.update(overrides)
    return RunRecord(**defaults)


def test_propose_memory_candidate_appends_to_run():
    from usr.plugins.agent_harness.helpers.memory import propose_memory_candidate
    run = _make_run()
    candidate = propose_memory_candidate(
        run=run, rule_text="Always run tests first",
        reason="Prevents regressions", source="test", scope="project",
        confidence=0.9,
    )
    assert len(run.memory_candidates) == 1
    assert candidate.rule_text == "Always run tests first"
    assert candidate.status == "proposed"


def test_find_memory_candidate_raises_on_missing():
    from usr.plugins.agent_harness.helpers.memory import find_memory_candidate
    import pytest
    run = _make_run()
    with pytest.raises(ValueError, match="not found"):
        find_memory_candidate(run, "nonexistent")


def test_reject_memory_candidate_sets_status():
    from usr.plugins.agent_harness.helpers.memory import (
        propose_memory_candidate, reject_memory_candidate,
    )
    run = _make_run()
    candidate = propose_memory_candidate(
        run=run, rule_text="test rule", reason="test",
        source="test", scope="project", confidence=0.5,
    )
    rejected = reject_memory_candidate(run=run, candidate_id=candidate.id)
    assert rejected.status == "rejected"
    assert rejected.decided_at != ""
