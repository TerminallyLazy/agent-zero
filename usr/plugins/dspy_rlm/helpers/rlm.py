"""Bounded, deterministic RLM evidence analysis.

This module is deliberately local-only: it neither calls models nor reads/writes trace
storage.  Callers provide already-sanitized evidence, which is projected again onto a
small allowlist before it can be queried.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from hashlib import sha256
import json
import re
from types import MappingProxyType
from typing import Iterable, Mapping


_SUPPORTED_QUERY_KINDS = frozenset(
    {
        "aggregate_metrics",
        "objective_bucket",
        "error_cluster",
        "tool_reliability",
        "predecessor_findings",
    }
)
_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,63}$")
_SECRET_MARKERS = (
    "password",
    "secret",
    "token",
    "authorization",
    "cookie",
    "private_key",
    "api_key",
)


def _freeze_mapping(value: Mapping[str, object] | None) -> Mapping[str, object]:
    """Return an immutable shallow projection with string keys only."""
    if not isinstance(value, Mapping):
        return MappingProxyType({})
    return MappingProxyType({str(key): item for key, item in value.items()})


def _freeze_parameters(value: Mapping[str, object] | None) -> Mapping[str, object]:
    """Keep query routing labels while dropping arbitrary/free-form parameter values."""
    if not isinstance(value, Mapping):
        return MappingProxyType({})
    parameters: dict[str, object] = {}
    for key, item in value.items():
        name = _safe_identifier(key, fallback="")
        if not name:
            continue
        if isinstance(item, str):
            safe = _safe_identifier(item, fallback="")
            if safe:
                parameters[name] = safe
        elif isinstance(item, (tuple, list)):
            safe_items = tuple(_safe_identifier(entry, fallback="") for entry in item)
            parameters[name] = tuple(entry for entry in safe_items if entry)
        elif isinstance(item, bool):
            parameters[name] = item
        elif isinstance(item, int) and not isinstance(item, bool):
            parameters[name] = max(0, item)
    return MappingProxyType(parameters)


def _stable_json(value: object) -> str:
    """Serialize arbitrary query scalars deterministically without raising."""
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    except (TypeError, ValueError):
        return repr(value)


def _digest(prefix: str, value: object) -> str:
    return f"{prefix}_{sha256(_stable_json(value).encode('utf-8')).hexdigest()[:16]}"


def _safe_identifier(value: object, *, fallback: str = "unknown") -> str:
    """Accept only compact labels; never reflect free-form evidence into findings."""
    text = str(value or "").strip()
    if not _SAFE_IDENTIFIER.fullmatch(text):
        return fallback
    lowered = text.lower()
    if any(marker in lowered for marker in _SECRET_MARKERS):
        return fallback
    return text


@dataclass(frozen=True)
class RlmBudget:
    """Hard resource limits for one in-memory recursive analysis."""

    max_depth: int = 2
    max_queries: int = 8
    max_evidence_chars: int = 8_000
    max_findings: int = 16

    def __post_init__(self) -> None:
        for name in ("max_depth", "max_queries", "max_evidence_chars", "max_findings"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")


@dataclass(frozen=True)
class RlmQuery:
    """A bounded request for one of the allowlisted evidence projections."""

    kind: str
    parameters: Mapping[str, object] = field(default_factory=dict)
    query_id: str = ""
    parent_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", str(self.kind).strip())
        object.__setattr__(self, "parameters", _freeze_parameters(self.parameters))
        object.__setattr__(self, "query_id", _safe_identifier(self.query_id, fallback=""))
        if self.parent_id is not None:
            object.__setattr__(self, "parent_id", _safe_identifier(self.parent_id, fallback=""))

    @property
    def digest(self) -> str:
        """Stable identity used for cycle detection, independent of caller query IDs."""
        return _digest("query", {"kind": self.kind, "parameters": dict(self.parameters)})


@dataclass(frozen=True)
class RlmFinding:
    """Typed, non-prompt finding produced from allowlisted aggregate evidence only."""

    finding_id: str
    kind: str
    status: str
    summary: str
    metrics: Mapping[str, object] = field(default_factory=dict)
    evidence_refs: tuple[str, ...] = ()
    predecessor_ids: tuple[str, ...] = ()
    derivation: tuple[str, ...] = ()
    review_only: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "finding_id", _safe_identifier(self.finding_id, fallback="finding_unknown"))
        object.__setattr__(self, "kind", str(self.kind).strip())
        status = str(self.status).strip()
        if status not in {"ok", "empty", "review_only", "budget_exhausted"}:
            status = "review_only"
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "summary", str(self.summary)[:320])
        object.__setattr__(self, "metrics", _freeze_mapping(self.metrics))
        object.__setattr__(self, "evidence_refs", tuple(_safe_identifier(item, fallback="") for item in self.evidence_refs if _safe_identifier(item, fallback="")))
        object.__setattr__(self, "predecessor_ids", tuple(_safe_identifier(item, fallback="") for item in self.predecessor_ids if _safe_identifier(item, fallback="")))
        object.__setattr__(self, "derivation", tuple(str(item)[:96] for item in self.derivation))
        object.__setattr__(self, "review_only", bool(self.review_only or status == "review_only"))


class EvidenceIndex:
    """An in-memory, redacted-only index with deterministic query dispatch.

    Only fixed event labels and booleans are retained.  Raw payloads, previews,
    objectives, arguments, and unrecognized fields are intentionally discarded.
    """

    def __init__(
        self,
        events: Iterable[Mapping[str, object]] = (),
        findings: Iterable[RlmFinding] = (),
    ) -> None:
        self._events = tuple(self._project_event(event) for event in events if isinstance(event, Mapping))
        self._findings: dict[str, RlmFinding] = {}
        for finding in findings:
            if isinstance(finding, RlmFinding):
                self.add_finding(finding)

    @staticmethod
    def _project_event(event: Mapping[str, object]) -> Mapping[str, object]:
        """Reject non-redacted input, then project it onto safe aggregate labels."""
        if event.get("redacted") is not True:
            raise ValueError("RLM evidence must explicitly declare redacted=True")
        raw_fields = {
            "content", "message", "messages", "prompt", "response", "response_preview",
            "objective", "user_intent", "tool_args", "arguments", "transcript", "text",
            "url", "headers", "cookies", "authorization", "password", "secret", "token",
            "api_key", "error",
        }
        present_raw = raw_fields.intersection(str(key).lower() for key in event)
        if present_raw:
            raise ValueError("RLM evidence contains prohibited raw field(s): " + ", ".join(sorted(present_raw)))
        projected = {
            "event_type": _safe_identifier(event.get("event_type"), fallback="unknown"),
            "objective_bucket": _safe_identifier(event.get("objective_bucket"), fallback="unknown"),
            "tool": _safe_identifier(event.get("tool", event.get("tool_name")), fallback="unknown"),
            "success": bool(event.get("success", True)),
            "error_class": _safe_identifier(event.get("error_class"), fallback="none"),
        }
        return MappingProxyType(projected)

    @property
    def event_count(self) -> int:
        return len(self._events)

    @property
    def findings(self) -> tuple[RlmFinding, ...]:
        return tuple(self._findings[key] for key in sorted(self._findings))

    def add_finding(self, finding: RlmFinding) -> None:
        if not isinstance(finding, RlmFinding):
            raise TypeError("finding must be an RlmFinding")
        self._findings[finding.finding_id] = finding

    def events_for(self, *, objective_bucket: str | None = None) -> tuple[Mapping[str, object], ...]:
        """Return only projected events, optionally filtered by a safe bucket label."""
        if objective_bucket is None:
            return self._events
        bucket = _safe_identifier(objective_bucket, fallback="")
        return tuple(event for event in self._events if event["objective_bucket"] == bucket)

    def query(self, query: RlmQuery, *, max_evidence_chars: int) -> RlmFinding:
        """Run an allowlisted deterministic handler with a strict evidence budget."""
        if not isinstance(query, RlmQuery):
            raise TypeError("query must be an RlmQuery")
        if not isinstance(max_evidence_chars, int) or isinstance(max_evidence_chars, bool) or max_evidence_chars < 0:
            raise ValueError("max_evidence_chars must be a non-negative integer")
        if query.kind not in _SUPPORTED_QUERY_KINDS:
            return self._review_finding(query, "unsupported_query")
        # Import here to keep direct module import safe and avoid a type-cycle.
        from .rlm_queries import execute_query

        try:
            return execute_query(self, query, max_evidence_chars=max_evidence_chars)
        except Exception:
            # Evidence analysis must degrade closed rather than expose a trace or fail a loop.
            return self._review_finding(query, "handler_failure")

    @staticmethod
    def _review_finding(query: RlmQuery, reason: str) -> RlmFinding:
        return RlmFinding(
            finding_id=_digest("finding", {"query": query.digest, "reason": reason}),
            kind=query.kind,
            status="review_only",
            summary="Evidence analysis requires review.",
            derivation=(reason,),
            review_only=True,
        )


class RlmController:
    """Deterministic recursive controller with no model, persistence, or side effects."""

    def __init__(self, evidence: EvidenceIndex, budget: RlmBudget | None = None) -> None:
        if not isinstance(evidence, EvidenceIndex):
            raise TypeError("evidence must be an EvidenceIndex")
        self.evidence = evidence
        self.budget = budget if budget is not None else RlmBudget()
        if not isinstance(self.budget, RlmBudget):
            raise TypeError("budget must be an RlmBudget or None")

    def analyze(self, query: RlmQuery) -> tuple[RlmFinding, ...]:
        """Analyze a root query and planned children, returning root then descendants.

        A finding contains predecessor IDs for every child it depends on.  The index is
        in-memory only; findings live no longer than this caller-owned index.
        """
        if not isinstance(query, RlmQuery):
            raise TypeError("query must be an RlmQuery")
        state = {"queries": 0, "evidence_chars": 0, "findings": 0}
        by_id: dict[str, RlmFinding] = {}
        descendants: list[RlmFinding] = []
        root = self._analyze(query, depth=0, ancestors=frozenset(), state=state, by_id=by_id, descendants=descendants)
        return tuple(([root] if root is not None else []) + descendants)

    def _analyze(
        self,
        query: RlmQuery,
        *,
        depth: int,
        ancestors: frozenset[str],
        state: dict[str, int],
        by_id: dict[str, RlmFinding],
        descendants: list[RlmFinding],
    ) -> RlmFinding | None:
        # Every finding, including synthetic budget and cycle findings, consumes the
        # same output budget.  Returning no finding after it is exhausted keeps the
        # public result strictly bounded even when planning produces extra children.
        if state["findings"] >= self.budget.max_findings:
            return None
        if depth > self.budget.max_depth:
            state["findings"] += 1
            return self._budget_finding(query, "depth_budget_exhausted")
        if query.digest in ancestors:
            state["findings"] += 1
            return self._review_cycle_finding(query)
        if state["queries"] >= self.budget.max_queries:
            state["findings"] += 1
            return self._budget_finding(query, "query_budget_exhausted")

        # Reserve an equal slice for every remaining possible query.  Charging the
        # full slice (rather than trusting handler-reported usage) is conservative:
        # aggregate evidence can never exceed the controller's total character cap.
        prior_queries = state["queries"]
        remaining_chars = max(0, self.budget.max_evidence_chars - state["evidence_chars"])
        remaining_slots = max(1, self.budget.max_queries - prior_queries)
        query_chars = remaining_chars // remaining_slots
        state["queries"] += 1
        finding = self.evidence.query(query, max_evidence_chars=query_chars)
        state["evidence_chars"] += query_chars
        state["findings"] += 1

        child_findings: list[RlmFinding] = []
        for child in self._child_queries(query, finding):
            # Do not emit synthetic child findings once a budget closes; this keeps
            # the returned DAG equal to the queries that were actually executed.
            if state["findings"] >= self.budget.max_findings or state["queries"] >= self.budget.max_queries:
                break
            child_finding = self._analyze(
                child,
                depth=depth + 1,
                ancestors=ancestors | {query.digest},
                state=state,
                by_id=by_id,
                descendants=descendants,
            )
            if child_finding is not None:
                child_findings.append(child_finding)

        predecessor_ids = tuple(item.finding_id for item in child_findings)
        if predecessor_ids:
            finding = replace(
                finding,
                predecessor_ids=predecessor_ids,
                derivation=tuple((*finding.derivation, "derived_from_children")),
            )
        self.evidence.add_finding(finding)
        by_id[finding.finding_id] = finding
        # A child has already appended its own descendants.  Append the direct child
        # itself after that work so the public result is root-first, depth-first.
        for child_finding in child_findings:
            if not any(item.finding_id == child_finding.finding_id for item in descendants):
                descendants.append(child_finding)
        return finding

    @staticmethod
    def _child_queries(query: RlmQuery, finding: RlmFinding) -> tuple[RlmQuery, ...]:
        """Fixed plans prevent arbitrary tool-like recursion or prompt-derived plans."""
        if finding.status not in {"ok", "empty"}:
            return ()
        params = dict(query.parameters)
        if query.kind == "aggregate_metrics":
            return (
                RlmQuery("tool_reliability", params, parent_id=query.query_id),
                RlmQuery("error_cluster", params, parent_id=query.query_id),
            )
        if query.kind == "objective_bucket":
            bucket = _safe_identifier(params.get("objective_bucket"), fallback="")
            if not bucket:
                return ()
            child_params = {"objective_bucket": bucket}
            return (
                RlmQuery("tool_reliability", child_params, parent_id=query.query_id),
                RlmQuery("error_cluster", child_params, parent_id=query.query_id),
            )
        return ()

    @staticmethod
    def _budget_finding(query: RlmQuery, reason: str) -> RlmFinding:
        return RlmFinding(
            finding_id=_digest("finding", {"query": query.digest, "reason": reason}),
            kind=query.kind,
            status="budget_exhausted",
            summary="Evidence analysis budget was exhausted.",
            derivation=(reason,),
            review_only=True,
        )

    @staticmethod
    def _review_cycle_finding(query: RlmQuery) -> RlmFinding:
        return RlmFinding(
            finding_id=_digest("finding", {"query": query.digest, "reason": "cycle_detected"}),
            kind=query.kind,
            status="review_only",
            summary="Evidence analysis cycle requires review.",
            derivation=("cycle_detected",),
            review_only=True,
        )


__all__ = ["EvidenceIndex", "RlmBudget", "RlmController", "RlmFinding", "RlmQuery"]
