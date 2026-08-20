"""Task 7 contract coverage for coordinator-owned guidance promotion."""
from __future__ import annotations

import json

import pytest

from usr.plugins.dspy_rlm.helpers.promotion import PromotionCoordinator
from usr.plugins.dspy_rlm.helpers.state import StateStore


@pytest.fixture
def coordinator(tmp_path) -> PromotionCoordinator:
    return PromotionCoordinator(state_store=StateStore(tmp_path), coordinator_id="test-coordinator")


def test_stage_is_immutable_and_does_not_change_the_active_pointer(coordinator: PromotionCoordinator) -> None:
    version = coordinator.stage("ctx-1", "reasoning", "Use concise steps.", objective_signature="sig-1", metadata={"source": "worker"})

    staged = coordinator.store.get_guidance_version(version)
    assert staged is not None
    assert staged["guidance_text"] == "Use concise steps."
    assert staged["metadata"] == {"source": "worker"}
    assert coordinator.current("ctx-1", "reasoning") is None

    # Re-staging a caller-supplied immutable ID must not replace its artifact.
    assert coordinator.stage("ctx-1", "reasoning", "Replacement", guidance_version=version) == version
    assert coordinator.store.get_guidance_version(version)["guidance_text"] == "Use concise steps."


def test_coordinator_refuses_unevaluated_first_promotion(coordinator: PromotionCoordinator) -> None:
    version = coordinator.stage("ctx-1", "reasoning", "First")

    decision = coordinator.promote("ctx-1", "reasoning", version, expected_revision=0)

    assert not decision.applied
    assert decision.reason == "missing_active_baseline"
    assert coordinator.current("ctx-1", "reasoning") is None

    with coordinator.store._connect() as conn:
        count = conn.execute("SELECT COUNT(*) FROM promotion_audits").fetchone()[0]
    assert count == 0


def test_rollback_is_cas_protected_and_keeps_audit_history(coordinator: PromotionCoordinator) -> None:
    v1 = coordinator.stage("ctx-1", "reasoning", "Known-good")
    v2 = coordinator.stage("ctx-1", "reasoning", "Regression")
    # An existing promoted version is a fixture precondition. New versions must
    # use the evidence-gated promote path and cannot bootstrap themselves.
    applied, revision = coordinator.store.compare_and_swap_active_guidance(
        "ctx-1", "reasoning", v2, expected_revision=0,
        actor_id="fixture", detail={"fixture": True}, action="fixture",
    )
    assert applied and revision == 1

    conflict = coordinator.rollback("ctx-1", "reasoning", v1, expected_revision=0)
    assert not conflict.applied
    assert conflict.reason == "active_revision_conflict"

    restored = coordinator.rollback("ctx-1", "reasoning", v1, expected_revision=1, detail={"why": "regression"})
    assert restored.applied
    assert restored.action == "rollback"
    assert restored.previous_guidance_version == v2
    assert restored.resulting_revision == 2
    active = coordinator.current("ctx-1", "reasoning")
    assert active is not None
    assert active["guidance_version"] == v1
    assert active["revision"] == 2

    with coordinator.store._connect() as conn:
        audit = conn.execute(
            "SELECT action,previous_guidance_version,guidance_version,expected_revision,resulting_revision,actor_id,detail_json "
            "FROM promotion_audits WHERE action='rollback'"
        ).fetchone()
    assert tuple(audit[0:6]) == ("rollback", v2, v1, 1, 2, "coordinator:test-coordinator")
    assert json.loads(audit[6]) == {"authority": "coordinator", "why": "regression"}
