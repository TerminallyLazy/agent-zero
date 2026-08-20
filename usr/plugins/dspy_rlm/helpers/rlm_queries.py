"""Deterministic handlers for bounded :mod:`.rlm` evidence queries.

This module has no storage or model dependency.  It operates only on the
allowlisted projections exposed by ``EvidenceIndex.events_for``.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import replace
from typing import TYPE_CHECKING, Mapping

if TYPE_CHECKING:
    from .rlm import EvidenceIndex, RlmFinding, RlmQuery


def _cap_records(
    records: tuple[Mapping[str, object], ...], max_evidence_chars: int
) -> tuple[Mapping[str, object], ...]:
    """Take a deterministic record prefix bounded by its projected representation."""
    if max_evidence_chars <= 0:
        return ()
    selected: list[Mapping[str, object]] = []
    used = 0
    for record in records:
        # Fields in EvidenceIndex projections are short labels/booleans only.
        size = sum(len(str(key)) + len(str(value)) + 4 for key, value in record.items())
        if selected and used + size > max_evidence_chars:
            break
        if size > max_evidence_chars:
            break
        selected.append(record)
        used += size
    return tuple(selected)


def _events(index: "EvidenceIndex", query: "RlmQuery", maximum: int) -> tuple[Mapping[str, object], ...]:
    bucket = query.parameters.get("objective_bucket")
    events = index.events_for(objective_bucket=str(bucket)) if bucket else index.events_for()
    return _cap_records(events, maximum)


def _finding(query: "RlmQuery", *, status: str, summary: str, metrics: Mapping[str, object], refs: tuple[str, ...], derivation: tuple[str, ...] = ()) -> "RlmFinding":
    # Imported lazily so the pair of modules remains import-safe in either order.
    from .rlm import RlmFinding, _digest

    return RlmFinding(
        finding_id=_digest("finding", {"query": query.digest, "metrics": dict(metrics), "status": status}),
        kind=query.kind,
        status=status,
        summary=summary,
        metrics=metrics,
        evidence_refs=refs,
        derivation=derivation,
        review_only=status == "review_only",
    )


def _references(events: tuple[Mapping[str, object], ...]) -> tuple[str, ...]:
    """Use hashes of projected records, rather than raw-event IDs or content."""
    from .rlm import _digest

    return tuple(_digest("evidence", dict(event)) for event in events)


def aggregate_metrics(index: "EvidenceIndex", query: "RlmQuery", max_evidence_chars: int) -> "RlmFinding":
    events = _events(index, query, max_evidence_chars)
    total = len(events)
    successful = sum(bool(event["success"]) for event in events)
    buckets = Counter(str(event["objective_bucket"]) for event in events)
    metrics = {
        "event_count": total,
        "success_count": successful,
        "failure_count": total - successful,
        "success_rate": round(successful / total, 6) if total else 0.0,
        "bucket_count": len(buckets),
    }
    return _finding(query, status="ok" if total else "empty", summary="Aggregate metrics computed from bounded redacted evidence.", metrics=metrics, refs=_references(events), derivation=("aggregate_metrics",))


def objective_bucket(index: "EvidenceIndex", query: "RlmQuery", max_evidence_chars: int) -> "RlmFinding":
    bucket = query.parameters.get("objective_bucket")
    if not isinstance(bucket, str) or not bucket:
        return _finding(query, status="review_only", summary="Objective bucket label is required.", metrics={}, refs=(), derivation=("invalid_bucket",))
    events = _events(index, query, max_evidence_chars)
    total = len(events)
    successful = sum(bool(event["success"]) for event in events)
    return _finding(query, status="ok" if total else "empty", summary="Objective bucket metrics computed from bounded redacted evidence.", metrics={"objective_bucket": bucket, "event_count": total, "success_count": successful, "failure_count": total - successful, "success_rate": round(successful / total, 6) if total else 0.0}, refs=_references(events), derivation=("objective_bucket",))


def error_cluster(index: "EvidenceIndex", query: "RlmQuery", max_evidence_chars: int) -> "RlmFinding":
    events = _events(index, query, max_evidence_chars)
    errors = Counter(str(event["error_class"]) for event in events if not bool(event["success"]))
    # Fixed count representation avoids reflecting arbitrary free-form error content.
    metrics = {"event_count": len(events), "failure_count": sum(errors.values()), "error_cluster_count": len(errors), "largest_cluster_count": max(errors.values(), default=0)}
    return _finding(query, status="ok" if events else "empty", summary="Failure clusters counted from bounded redacted labels.", metrics=metrics, refs=_references(events), derivation=("error_cluster",))


def tool_reliability(index: "EvidenceIndex", query: "RlmQuery", max_evidence_chars: int) -> "RlmFinding":
    events = _events(index, query, max_evidence_chars)
    counts: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for event in events:
        tool = str(event["tool"])
        counts[tool][0] += 1
        counts[tool][1] += int(bool(event["success"]))
    unreliable = sum(1 for calls, successes in counts.values() if calls and successes < calls)
    metrics = {"event_count": len(events), "tool_count": len(counts), "tools_with_failure": unreliable}
    return _finding(query, status="ok" if events else "empty", summary="Tool reliability aggregated from bounded redacted labels.", metrics=metrics, refs=_references(events), derivation=("tool_reliability",))


def predecessor_findings(index: "EvidenceIndex", query: "RlmQuery", max_evidence_chars: int) -> "RlmFinding":
    requested = query.parameters.get("finding_ids", ())
    ids = (requested,) if isinstance(requested, str) else tuple(item for item in requested if isinstance(item, str)) if isinstance(requested, (tuple, list)) else ()
    findings = [item for item in index.findings if not ids or item.finding_id in ids]
    metrics = {"predecessor_count": len(findings), "review_only_count": sum(item.review_only for item in findings)}
    return _finding(query, status="ok" if findings else "empty", summary="Predecessor finding references resolved without exposing their source evidence.", metrics=metrics, refs=tuple(item.finding_id for item in findings), derivation=("predecessor_findings",))


_HANDLERS = {
    "aggregate_metrics": aggregate_metrics,
    "objective_bucket": objective_bucket,
    "error_cluster": error_cluster,
    "tool_reliability": tool_reliability,
    "predecessor_findings": predecessor_findings,
}


def execute_query(index: "EvidenceIndex", query: "RlmQuery", *, max_evidence_chars: int) -> "RlmFinding":
    """Execute one fixed, local query handler with its remaining evidence budget."""
    handler = _HANDLERS.get(query.kind)
    if handler is None:
        raise ValueError("unsupported query kind")
    return handler(index, query, max(0, int(max_evidence_chars)))


__all__ = ["aggregate_metrics", "error_cluster", "execute_query", "objective_bucket", "predecessor_findings", "tool_reliability"]
