"""Frozen paired offline baseline/candidate replay and promotion-readiness gates.

Replay is intentionally not a live-agent or tool execution path.  Both arms execute
against the exact same immutable case mappings.  Missing evidence, unavailable
baseline, active-baseline drift, or judge ambiguity produces ``review_only``; none
can be converted into a promotion pass by aggregate or lexical scores.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from hashlib import sha256
import json
from types import MappingProxyType
from typing import Any, Callable, Iterable, Mapping, Protocol, Sequence

from .evaluation import REPLAY_MODES, execute_offline_case


PROMOTION_READY = "promotion_ready"
REJECTED = "rejected"
REVIEW_ONLY = "review_only"


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)


def _digest(value: Any) -> str:
    return "sha256:" + sha256(_canonical(value).encode("utf-8")).hexdigest()


def _score(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, number)) if number == number else 0.0


def _case_id(case: Mapping[str, Any], index: int) -> str:
    return str(case.get("case_id", case.get("sample_id", case.get("id", ""))) or _digest({"case": case, "index": index})[:24])


def _bucket(case: Mapping[str, Any]) -> str:
    return str(case.get("objective_bucket", case.get("bucket", "reasoning")) or "reasoning")


class BlindStructuredJudge(Protocol):
    """Optional judge interface; receives opaque A/B labels and emits structured data."""

    def __call__(self, payload: Mapping[str, Any]) -> Mapping[str, Any]: ...


@dataclass(frozen=True)
class FrozenReplayManifest:
    """Canonical immutable held-out manifest used by both replay arms."""

    manifest_id: str
    cases: tuple[Mapping[str, Any], ...]
    digest: str
    provenance: Mapping[str, Any]
    replay_mode: str

    @classmethod
    def create(
        cls, cases: Sequence[Mapping[str, Any]], *, manifest_id: str = "", replay_mode: str = "offline_prompt_output_replay",
        provenance: Mapping[str, Any] | None = None,
    ) -> "FrozenReplayManifest":
        if replay_mode not in REPLAY_MODES:
            raise ValueError("invalid replay mode")
        if not isinstance(cases, Sequence) or isinstance(cases, (str, bytes)) or not cases:
            raise ValueError("frozen manifest must have at least one held-out case")
        seen: set[str] = set()
        frozen: list[Mapping[str, Any]] = []
        for index, raw in enumerate(cases):
            if not isinstance(raw, Mapping):
                raise TypeError("replay cases must be mappings")
            case = dict(raw)
            case_id = _case_id(case, index)
            if case_id in seen:
                raise ValueError("replay manifest has duplicate case IDs")
            seen.add(case_id)
            case["case_id"] = case_id
            # Keep an immutable snapshot: callers retaining their input list or
            # nested mappings cannot mutate the replay fixture after freezing.
            frozen.append(MappingProxyType(json.loads(_canonical(case))))
        canonical_cases = tuple(frozen)
        digest = _digest({"replay_mode": replay_mode, "cases": [dict(case) for case in canonical_cases]})
        return cls(
            manifest_id=str(manifest_id or "replay-" + digest.split(":", 1)[1][:16]),
            cases=canonical_cases, digest=digest,
            provenance=MappingProxyType(json.loads(_canonical(dict(provenance or {})))), replay_mode=replay_mode,
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "FrozenReplayManifest":
        if not isinstance(value, Mapping):
            raise TypeError("manifest must be a mapping")
        manifest = cls.create(value.get("cases", value.get("held_out_cases", ())), manifest_id=str(value.get("manifest_id", "")),
                              replay_mode=str(value.get("replay_mode", "offline_prompt_output_replay")), provenance=value.get("provenance", {}))
        supplied = value.get("digest", value.get("manifest_digest"))
        if supplied and str(supplied) != manifest.digest:
            raise ValueError("frozen manifest digest mismatch")
        return manifest

    def to_mapping(self) -> dict[str, Any]:
        return {"manifest_id": self.manifest_id, "cases": [dict(case) for case in self.cases], "digest": self.digest,
                "provenance": dict(self.provenance), "replay_mode": self.replay_mode}


def freeze_held_out_cases(
    cases: Sequence[Mapping[str, Any]], *, training_case_ids: Iterable[str] = (), manifest_id: str = "",
    replay_mode: str = "offline_prompt_output_replay", provenance: Mapping[str, Any] | None = None,
) -> FrozenReplayManifest:
    """Freeze a held-out set and reject any train/holdout case identity overlap."""
    manifest = FrozenReplayManifest.create(cases, manifest_id=manifest_id, replay_mode=replay_mode, provenance=provenance)
    training = {str(item) for item in training_case_ids if str(item)}
    overlap = training & {_case_id(case, index) for index, case in enumerate(manifest.cases)}
    if overlap:
        raise ValueError("held-out replay manifest overlaps training cases")
    return manifest


def _judge_payload(case: Mapping[str, Any], baseline: Mapping[str, Any], candidate: Mapping[str, Any], index: int) -> dict[str, Any]:
    # Labels are stable but do not disclose which arm is incumbent/candidate.
    # Fixture input is included; neither artifact identity nor arm name is exposed.
    a, b = (baseline, candidate) if index % 2 == 0 else (candidate, baseline)
    return {"schema_version": "blind_paired_judge.v1", "case_id": _case_id(case, index), "fixture": dict(case),
            "outputs": {"A": dict(a.get("output", {})), "B": dict(b.get("output", {}))}, "labels_blinded": True}


def _run_judge(judge: BlindStructuredJudge | None, payload: Mapping[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    if judge is None:
        return None, None
    try:
        result = judge(payload)
    except Exception as error:
        return None, f"judge_exception:{type(error).__name__}"
    if not isinstance(result, Mapping):
        return None, "judge_invalid_response"
    verdict = str(result.get("verdict", result.get("winner", ""))).lower()
    if verdict not in {"a", "b", "tie", "inconclusive"}:
        return None, "judge_invalid_verdict"
    confidence = _score(result.get("confidence", 0.0))
    if verdict == "inconclusive" or confidence <= 0.0:
        return None, "judge_inconclusive"
    return {"verdict": verdict, "confidence": confidence, "schema_version": str(result.get("schema_version", "judge.v1"))}, None


def paired_replay(
    manifest: FrozenReplayManifest | Mapping[str, Any], *, baseline: Any | None, candidate: Any,
    executor: Callable[..., Any], baseline_revision: str | None = None, active_baseline_revision: str | None = None,
    protected_buckets: Iterable[str] = (), tolerable_regression: float = 0.0,
    judge: BlindStructuredJudge | None = None, evaluator_provenance: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Run paired same-case offline evaluation and return a fail-closed decision.

    ``baseline is None`` is an explicit review state for an initial deployment.  It
    is deliberately not a pass.  A judge can add human-like review evidence, but
    any unavailable/invalid judge response also makes the result review-only.
    """
    frozen = manifest if isinstance(manifest, FrozenReplayManifest) else FrozenReplayManifest.from_mapping(manifest)
    tolerance = max(0.0, _score(tolerable_regression))
    base_prov = {"manifest_id": frozen.manifest_id, "manifest_digest": frozen.digest, "harness": "paired_offline_replay_v1",
                 **(dict(evaluator_provenance) if isinstance(evaluator_provenance, Mapping) else {})}
    common = {"enabled": True, "replay_mode": frozen.replay_mode, "manifest_id": frozen.manifest_id,
              "manifest_digest": frozen.digest, "manifest_provenance": dict(frozen.provenance), "provenance": base_prov,
              "baseline_revision": baseline_revision, "active_baseline_revision": active_baseline_revision,
              "tolerable_regression": tolerance, "candidate_supplied": candidate is not None}
    if baseline is None:
        return {**common, "passed": False, "decision": REVIEW_ONLY, "promotion_ready": False, "reason": "missing_baseline",
                "reason_codes": ["missing_baseline"], "cases": [], "coverage": {"required": len(frozen.cases), "paired": 0}}
    if candidate is None:
        return {**common, "passed": False, "decision": REJECTED, "promotion_ready": False, "reason": "missing_candidate",
                "reason_codes": ["missing_candidate"], "cases": [], "coverage": {"required": len(frozen.cases), "paired": 0}}
    if baseline_revision is None or active_baseline_revision is None or str(baseline_revision) != str(active_baseline_revision):
        return {**common, "passed": False, "decision": REVIEW_ONLY, "promotion_ready": False, "reason": "baseline_revision_mismatch",
                "reason_codes": ["baseline_revision_mismatch"], "cases": [], "coverage": {"required": len(frozen.cases), "paired": 0}}

    rows: list[dict[str, Any]] = []
    reasons: list[str] = []
    bucket_scores: dict[str, list[tuple[float, float]]] = defaultdict(list)
    candidate_scores: list[float] = []
    baseline_scores: list[float] = []
    for index, case in enumerate(frozen.cases):
        base = execute_offline_case(executor, case, baseline, replay_mode=frozen.replay_mode, evaluator_provenance=base_prov).to_mapping()
        trial = execute_offline_case(executor, case, candidate, replay_mode=frozen.replay_mode, evaluator_provenance=base_prov).to_mapping()
        case_reasons = [f"baseline:{item}" for item in base["hard_failures"]] + [f"candidate:{item}" for item in trial["hard_failures"]]
        if case_reasons:
            reasons.extend(f"{base['case_id']}:{item}" for item in case_reasons)
        judgment, judge_error = _run_judge(judge, _judge_payload(case, base, trial, index))
        if judge_error:
            reasons.append(f"{base['case_id']}:{judge_error}")
        bucket = _bucket(case)
        bucket_scores[bucket].append((_score(base["score"]), _score(trial["score"])))
        baseline_scores.append(_score(base["score"])); candidate_scores.append(_score(trial["score"]))
        rows.append({"case_id": base["case_id"], "bucket": bucket, "baseline": base, "candidate": trial,
                     "hard_failures": case_reasons, "judge": judgment, "judge_error": judge_error,
                     "paired": True, "case_digest": _digest(dict(case))})

    # Callers may centrally designate protected buckets and fixtures may mark a
    # case protected.  The latter is useful when a held-out set mixes critical
    # and ordinary cases; neither source can weaken the other.
    protected = {str(item) for item in protected_buckets if str(item)}
    protected.update(
        _bucket(case) for case in frozen.cases
        if bool(case.get("protected", case.get("protected_bucket", False)))
    )
    regressions: dict[str, float] = {}
    for bucket, scores in bucket_scores.items():
        base_avg = sum(pair[0] for pair in scores) / len(scores)
        candidate_avg = sum(pair[1] for pair in scores) / len(scores)
        regression = max(0.0, base_avg - candidate_avg)
        regressions[bucket] = regression
        # Protected buckets are a strict no-regression contract. Ordinary
        # buckets are still promotion gates: their regression must remain within
        # the configured tolerance rather than being hidden by a better global
        # average in another bucket.
        if bucket in protected and regression > 0.0:
            reasons.append(f"protected_bucket_regression:{bucket}")
        elif regression > tolerance:
            reasons.append(f"tolerable_regression_exceeded:{bucket}")
    if len(rows) != len(frozen.cases):
        reasons.append("inadequate_coverage")
    # A configured judge is additional review evidence.  Its absence or
    # malformed/inconclusive response must not become a deterministic pass.
    if any("judge_" in reason for reason in reasons):
        decision = REVIEW_ONLY
    elif reasons:
        decision = REJECTED
    else:
        decision = PROMOTION_READY
    baseline_average = sum(baseline_scores) / len(baseline_scores) if baseline_scores else 0.0
    candidate_average = sum(candidate_scores) / len(candidate_scores) if candidate_scores else 0.0
    return {**common, "passed": decision == PROMOTION_READY, "decision": decision, "promotion_ready": decision == PROMOTION_READY,
            "reason": "passed" if decision == PROMOTION_READY else decision, "reason_codes": sorted(set(reasons)), "cases": rows,
            "coverage": {"required": len(frozen.cases), "paired": len(rows), "adequate": len(rows) == len(frozen.cases)},
            "baseline_score": baseline_average, "candidate_score": candidate_average,
            "regression": max(0.0, baseline_average - candidate_average), "bucket_regressions": regressions,
            "protected_buckets": sorted(protected), "judge_enabled": judge is not None}


# Compatibility-oriented explicit names for service callers.
run_paired_replay = paired_replay
replay_candidate = paired_replay
