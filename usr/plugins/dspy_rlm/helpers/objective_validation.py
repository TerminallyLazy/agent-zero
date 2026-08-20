"""Deterministic pre-replay validation gates.

Legacy matrix/lexical values are returned as telemetry for compatibility, but cannot
promote a candidate.  Promotion requires explicit fixture-derived deterministic
checks and then the paired replay gate in :mod:`replay`.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Mapping


HARD_CHECKS = ("schema_valid", "policy_compliant", "safety_passed", "execution_succeeded")


def _unit(value: Any, fallback: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    return max(0.0, min(1.0, number)) if number == number else fallback


def _sample_bucket(row: Mapping[str, Any]) -> str:
    sample = row.get("sample", {})
    return str(sample.get("objective_bucket", "reasoning") if isinstance(sample, Mapping) else "reasoning")


def _explicit_checks(row: Mapping[str, Any]) -> tuple[bool, dict[str, bool], list[str]]:
    deterministic = row.get("deterministic", {})
    if not isinstance(deterministic, Mapping):
        return False, {}, ["deterministic_evidence_missing"]
    raw = deterministic.get("checks", {})
    if not isinstance(raw, Mapping) or not bool(deterministic.get("available", False)):
        return False, {}, ["deterministic_evidence_missing"]
    checks: dict[str, bool] = {}
    failures: list[str] = []
    for name in HARD_CHECKS:
        value = raw.get(name)
        if not isinstance(value, bool):
            failures.append(f"{name}_missing")
        else:
            checks[name] = value
            if not value:
                failures.append(f"{name}_failed")
    declared = deterministic.get("hard_failures", [])
    if isinstance(declared, (list, tuple, set, frozenset)):
        failures.extend(str(item) for item in declared if str(item))
    return not failures, checks, sorted(set(failures))


def _telemetry(rows: list[Mapping[str, Any]]) -> dict[str, float]:
    keys = ("semantic_match", "command_safety", "execution_reliability", "evidence_recall", "evidence_precision", "answer_quality", "policy_compliance")
    total = {key: 0.0 for key in keys}
    if not rows:
        return total
    for row in rows:
        values = row.get("scores", {})
        if isinstance(values, Mapping):
            for key in keys:
                total[key] += _unit(values.get(key, 0.0))
    return {key: _unit(value / len(rows)) for key, value in total.items()}


def validate(objective_results: list[dict[str, Any]], cfg: dict[str, Any]) -> dict[str, Any]:
    """Fail closed unless every result contains passing deterministic facts.

    Existing callers receive the historical score/bucket keys, explicitly marked
    telemetry-only.  This function cannot turn those numbers into a pass.  Lack of
    offline deterministic evidence is ``review_only`` rather than a synthetic
    rejection because operators may attach a frozen replay manifest subsequently.
    """
    cfg = cfg if isinstance(cfg, Mapping) else {}
    optimization = cfg.get("optimization", {}) if isinstance(cfg.get("optimization", {}), Mapping) else {}
    minimum = max(1, int(optimization.get("min_samples_for_promotion", 1) or 1))
    if not objective_results:
        return {"passed": False, "promotion_ready": False, "review_only": False, "global_score": 0.0,
                "reason_code": "NO_OBJECTIVES", "reason": "No objective samples were available for validation",
                "bucket_scores": {}, "bucket_counts": {}, "bucket_decisions": {}, "hard_fail_flags": ["no_objectives"],
                "required_sample_count": minimum, "sample_count": 0, "telemetry_only": True, "telemetry": {}}

    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in objective_results:
        if isinstance(row, Mapping):
            grouped[_sample_bucket(row)].append(row)
    flags: list[str] = []
    decisions: dict[str, Any] = {}
    missing_evidence = False
    deterministic_pass_count = 0
    for bucket, rows in grouped.items():
        failures: list[str] = []
        cases: list[dict[str, Any]] = []
        for row in rows:
            passed, checks, row_failures = _explicit_checks(row)
            objective_id = str((row.get("sample", {}) or {}).get("objective_id", ""))
            if "deterministic_evidence_missing" in row_failures:
                missing_evidence = True
            if passed:
                deterministic_pass_count += 1
            else:
                failures.extend(f"{objective_id or 'sample'}:{failure}" for failure in row_failures)
            cases.append({"objective_id": objective_id, "passed": passed, "checks": checks, "hard_failures": row_failures})
        if failures:
            flags.extend(f"{bucket}:{failure}" for failure in failures if "deterministic_evidence_missing" not in failure)
        decisions[bucket] = {"passed": not failures, "sample_count": len(rows), "cases": cases,
                             "reasons": sorted(set(failures)), "telemetry": _telemetry(rows), "telemetry_only": True}

    count = len(objective_results)
    if count < minimum:
        flags.append("insufficient_samples")
    telemetry_by_bucket = {bucket: _telemetry(rows) for bucket, rows in grouped.items()}
    # Retain a dashboard-compatible numerical summary, but make no decision from it.
    global_score = sum(values.get("answer_quality", 0.0) for values in telemetry_by_bucket.values()) / max(1, len(telemetry_by_bucket))
    review_only = missing_evidence and not flags and count >= minimum
    passed = not missing_evidence and not flags and deterministic_pass_count == count and count >= minimum
    if passed:
        code, reason = "DETERMINISTIC_GATES_PASSED", "Deterministic pre-replay gates passed; paired replay still required"
    elif review_only:
        code, reason = "REVIEW_ONLY_MISSING_DETERMINISTIC_EVIDENCE", "Offline deterministic evidence is required before promotion"
    else:
        code, reason = "REJECTED_DETERMINISTIC_GATE", "Deterministic validation rejected"
    return {"passed": passed, "promotion_ready": False, "review_only": review_only, "global_score": round(global_score, 4),
            "reason_code": code, "reason": reason, "bucket_scores": {bucket: values.get("answer_quality", 0.0) for bucket, values in telemetry_by_bucket.items()},
            "bucket_counts": {bucket: len(rows) for bucket, rows in grouped.items()}, "bucket_decisions": decisions,
            "hard_fail_flags": sorted(set(flags)), "required_sample_count": minimum, "sample_count": count,
            "deterministic_pass_count": deterministic_pass_count, "telemetry_only": True,
            "telemetry": {"by_bucket": telemetry_by_bucket, "global_score": global_score}}
