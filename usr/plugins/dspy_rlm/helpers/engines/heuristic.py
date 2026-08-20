"""Dependency-free conversion of typed RLM findings into safe guidance artifacts."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from typing import Any, Iterable, Mapping, Sequence

from ..guidance import GuidanceArtifact, MAX_ARTIFACT_LIFETIME_SECONDS
from ..rlm import RlmFinding
from . import EngineResult


ENGINE_VERSION = "heuristic.v1"


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _hash(value: Any) -> str:
    return "sha256:" + sha256(_canonical(value).encode("utf-8")).hexdigest()


def _utc(value: datetime | None = None) -> datetime:
    result = value or datetime.now(timezone.utc)
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc).replace(microsecond=0)


def _stamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _finding_projection(finding: RlmFinding) -> Mapping[str, Any]:
    """Canonical, aggregate-only projection used for audit linkage and decisions."""
    return {
        "finding_id": finding.finding_id,
        "kind": finding.kind,
        "status": finding.status,
        "metrics": dict(finding.metrics),
        "evidence_refs": list(finding.evidence_refs),
        "predecessor_ids": list(finding.predecessor_ids),
        "derivation": list(finding.derivation),
        "review_only": finding.review_only,
    }


def finding_hashes(findings: Iterable[RlmFinding]) -> tuple[str, ...]:
    """Return stable SHA-256 references without exposing finding prose."""
    checked = _validated_findings(findings)
    return tuple(sorted({_hash(_finding_projection(item)) for item in checked}))


def _validated_findings(findings: Iterable[RlmFinding]) -> tuple[RlmFinding, ...]:
    result: list[RlmFinding] = []
    for finding in findings:
        if not isinstance(finding, RlmFinding):
            raise TypeError("heuristic engine accepts only RlmFinding instances")
        result.append(finding)
    return tuple(result)


def rules_from_findings(findings: Iterable[RlmFinding]) -> list[dict[str, Any]]:
    """Map fixed aggregate metrics to the fixed guidance-rule vocabulary.

    Free-form finding summaries and evidence are deliberately not inputs to this
    function.  Review-only and budget-exhausted findings are non-actionable.
    """
    actionable = [item for item in _validated_findings(findings) if item.status == "ok" and not item.review_only]
    if not actionable:
        return []
    failures = 0
    tool_failures = 0
    for finding in actionable:
        metrics = finding.metrics
        failures += max(0, int(metrics.get("failure_count", 0) or 0))
        tool_failures += max(0, int(metrics.get("tools_with_failure", 0) or 0))
    rules: list[dict[str, Any]] = [{"type": "verify_tool_contract"}]
    if failures or tool_failures:
        rules.append({"type": "check_tool_result"})
        rules.append({"type": "retry_after_failure", "max_retries": 1})
    if failures >= 2 or tool_failures >= 2:
        rules.append({"type": "prefer_reversible_action"})
    # Keep artifacts within guidance.MAX_RULES. The canonical validator also enforces it.
    return rules[:4]


class HeuristicEngine:
    """Build an allowlisted artifact from typed, bounded RLM findings only."""

    kind = "heuristic"
    version = ENGINE_VERSION

    def compile(
        self,
        *,
        context_id: str,
        objective_bucket: str,
        findings: Iterable[RlmFinding],
        source_manifest_hashes: Sequence[str] | None = None,
        now: datetime | None = None,
        lifetime_seconds: int = 7 * 24 * 60 * 60,
    ) -> EngineResult:
        checked = _validated_findings(findings)
        hashes = finding_hashes(checked)
        rules = rules_from_findings(checked)
        base_reproducibility = {
            "engine_version": self.version,
            "finding_count": len(checked),
            "actionable_finding_count": sum(item.status == "ok" and not item.review_only for item in checked),
            "source_finding_hashes": list(hashes),
        }
        if not hashes or not rules:
            return EngineResult("no_candidate", self.kind, reproducibility=base_reproducibility, error="no_actionable_rlm_findings")
        manifests = tuple(sorted(set(source_manifest_hashes or (_hash({"context_id": context_id, "objective_bucket": objective_bucket, "findings": hashes}),))))
        issued = _utc(now)
        bounded_lifetime = max(1, min(int(lifetime_seconds), MAX_ARTIFACT_LIFETIME_SECONDS))
        expires = issued + timedelta(seconds=bounded_lifetime)
        artifact_token = _hash({"engine": self.version, "context_id": context_id, "objective_bucket": objective_bucket, "findings": hashes, "rules": rules})[-20:]
        artifact = GuidanceArtifact.create(
            artifact_id=f"heuristic-{artifact_token}",
            context_id=context_id,
            objective_bucket=objective_bucket,
            rules=rules,
            source_manifest_hashes=manifests,
            source_finding_hashes=hashes,
            issued_at=_stamp(issued),
            expires_at=_stamp(expires),
            engine_kind=self.kind,
            engine_version=self.version,
        )
        return EngineResult("succeeded", self.kind, artifact=artifact, reproducibility={**base_reproducibility, "source_manifest_hashes": list(manifests), "artifact_digest": artifact.artifact_digest})

    run = compile


__all__ = ["ENGINE_VERSION", "HeuristicEngine", "finding_hashes", "rules_from_findings"]
