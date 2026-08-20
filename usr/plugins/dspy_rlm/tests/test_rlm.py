"""Adversarial contracts for bounded, redacted RLM evidence analysis."""
from __future__ import annotations

import pytest

from usr.plugins.dspy_rlm.helpers.rlm import (
    EvidenceIndex,
    RlmBudget,
    RlmController,
    RlmQuery,
)


@pytest.fixture
def redacted_events() -> list[dict[str, object]]:
    """Only the narrow, already-redacted event projection reaches the RLM."""
    return [
        {
            "redacted": True,
            "event_type": "tool",
            "objective_bucket": "support",
            "tool": "search",
            "success": False,
            "error_class": "timeout",
        },
        {
            "redacted": True,
            "event_type": "tool",
            "objective_bucket": "support",
            "tool": "search",
            "success": True,
            "error_class": "none",
        },
        {
            "redacted": True,
            "event_type": "tool",
            "objective_bucket": "coding",
            "tool": "editor",
            "success": False,
            "error_class": "validation",
        },
    ]


def test_evidence_index_accepts_only_explicitly_redacted_allowlisted_events(
    redacted_events: list[dict[str, object]],
) -> None:
    index = EvidenceIndex(redacted_events)

    assert index.event_count == len(redacted_events)
    assert all(event["objective_bucket"] in {"support", "coding"} for event in index.events_for())

    without_redaction_marker = dict(redacted_events[0])
    without_redaction_marker.pop("redacted")
    with pytest.raises(ValueError, match="redacted=True"):
        EvidenceIndex([without_redaction_marker])

    raw_payload = {**redacted_events[0], "content": "must-not-enter-evidence-index"}
    with pytest.raises(ValueError, match="prohibited raw field"):
        EvidenceIndex([raw_payload])


def test_recursive_analysis_is_deterministic_and_parent_records_two_children(
    redacted_events: list[dict[str, object]],
) -> None:
    budget = RlmBudget(max_depth=1, max_queries=3, max_evidence_chars=3_000, max_findings=3)
    query = RlmQuery("aggregate_metrics")

    first = RlmController(EvidenceIndex(redacted_events), budget).analyze(query)
    second = RlmController(EvidenceIndex(redacted_events), budget).analyze(query)

    assert first == second
    assert [finding.kind for finding in first] == [
        "aggregate_metrics",
        "tool_reliability",
        "error_cluster",
    ]
    parent, *children = first
    assert parent.status == "ok"
    assert parent.predecessor_ids == tuple(child.finding_id for child in children)
    assert parent.derivation[-1] == "derived_from_children"
    assert all(child.evidence_refs for child in children)
    assert all(child.status == "ok" for child in children)


def test_depth_and_query_budgets_prevent_extra_evidence_queries(
    redacted_events: list[dict[str, object]], monkeypatch: pytest.MonkeyPatch
) -> None:
    index = EvidenceIndex(redacted_events)
    calls: list[tuple[str, int]] = []
    original_query = index.query

    def counted_query(query: RlmQuery, *, max_evidence_chars: int):
        calls.append((query.kind, max_evidence_chars))
        return original_query(query, max_evidence_chars=max_evidence_chars)

    monkeypatch.setattr(index, "query", counted_query)

    depth_limited = RlmController(
        index,
        RlmBudget(max_depth=0, max_queries=8, max_evidence_chars=900, max_findings=8),
    ).analyze(RlmQuery("aggregate_metrics"))
    assert [kind for kind, _ in calls] == ["aggregate_metrics"]
    assert sum(characters for _, characters in calls) <= 900
    assert depth_limited[0].kind == "aggregate_metrics"

    calls.clear()
    query_limited = RlmController(
        index,
        RlmBudget(max_depth=2, max_queries=2, max_evidence_chars=900, max_findings=8),
    ).analyze(RlmQuery("aggregate_metrics"))
    assert [kind for kind, _ in calls] == ["aggregate_metrics", "tool_reliability"]
    assert len(query_limited) == 2


def test_character_budget_bounds_visible_evidence_and_zero_budget_exposes_none(
    redacted_events: list[dict[str, object]],
) -> None:
    index = EvidenceIndex(redacted_events)
    query = RlmQuery("aggregate_metrics")

    tiny = index.query(query, max_evidence_chars=1)
    full = index.query(query, max_evidence_chars=3_000)
    zero_budget = RlmController(
        index,
        RlmBudget(max_depth=1, max_queries=3, max_evidence_chars=0, max_findings=3),
    ).analyze(query)

    assert tiny.metrics["event_count"] == 0
    assert tiny.evidence_refs == ()
    assert full.metrics["event_count"] == len(redacted_events)
    assert all(finding.evidence_refs == () for finding in zero_budget)


def test_recursive_controller_detects_a_query_cycle_without_requerying_evidence(
    redacted_events: list[dict[str, object]], monkeypatch: pytest.MonkeyPatch
) -> None:
    index = EvidenceIndex(redacted_events)
    calls = 0
    original_query = index.query

    def counted_query(query: RlmQuery, *, max_evidence_chars: int):
        nonlocal calls
        calls += 1
        return original_query(query, max_evidence_chars=max_evidence_chars)

    # A planner must not be able to turn a repeated query into unbounded recursion.
    monkeypatch.setattr(index, "query", counted_query)
    monkeypatch.setattr(
        RlmController,
        "_child_queries",
        staticmethod(lambda query, finding: (RlmQuery(query.kind, dict(query.parameters)),)),
    )

    findings = RlmController(index, RlmBudget(max_depth=5, max_queries=5)).analyze(
        RlmQuery("aggregate_metrics")
    )

    assert calls == 1
    assert len(findings) == 2
    assert findings[1].status == "review_only"
    assert findings[1].review_only is True
    assert findings[1].derivation == ("cycle_detected",)


def test_query_handler_failure_degrades_to_review_only_without_children(
    redacted_events: list[dict[str, object]], monkeypatch: pytest.MonkeyPatch
) -> None:
    import usr.plugins.dspy_rlm.helpers.rlm_queries as rlm_queries

    def broken_handler(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("simulated local analysis failure")

    monkeypatch.setattr(rlm_queries, "execute_query", broken_handler)

    findings = RlmController(EvidenceIndex(redacted_events)).analyze(
        RlmQuery("aggregate_metrics")
    )

    assert len(findings) == 1
    finding = findings[0]
    assert finding.status == "review_only"
    assert finding.review_only is True
    assert finding.derivation == ("handler_failure",)
    assert finding.evidence_refs == ()
