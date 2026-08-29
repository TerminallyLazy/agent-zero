"""Telemetry-oriented lexical diagnostics and optional structured judge seam.

This module is deliberately *not* a promotion oracle.  Its historical lexical and
trace-derived scores remain useful for dashboards and calibration, but are labelled
telemetry-only.  Promotion code must consume deterministic offline checks from
``evaluation``/``replay`` instead.
"""
from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any, Mapping, Protocol

from .objective import collect_recent_objectives
from .dspy_runtime import semantic_judge


class StructuredJudge(Protocol):
    """Optional blind judge contract used by offline replay adapters.

    Implementations receive only the blinded structured payload and must return a
    mapping containing ``verdict`` (``a``, ``b``, ``tie``, or ``inconclusive``) and
    a numeric ``confidence`` in [0, 1].  Callers treat exceptions/malformed output
    as review-only; this protocol never provides a fallback pass.
    """

    def __call__(self, payload: Mapping[str, Any]) -> Mapping[str, Any]: ...


def _safe_text(value: Any, limit: int = 220) -> str:
    text = str(value or "").strip()
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _coerce_unit(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, number)) if number == number else default


def _contains_policy_issue(response: str, policy_keywords: list[str], risk_threshold: float) -> tuple[bool, list[str]]:
    flags: list[str] = []
    if response:
        lower = response.lower()
        for keyword in policy_keywords:
            if str(keyword).strip().lower() in lower:
                flags.append(f"keyword:{keyword}")
    return min(1.0, len(flags) * 0.3) >= risk_threshold, flags


def _explicit_deterministic_evidence(sample: Mapping[str, Any], *, policy_breach: bool) -> dict[str, Any]:
    """Expose fixture-provided hard checks without inventing a pass from prose."""
    raw = sample.get("deterministic_checks", sample.get("offline_checks", {}))
    checks = dict(raw) if isinstance(raw, Mapping) else {}
    required = ("schema_valid", "policy_compliant", "safety_passed", "execution_succeeded")
    # A detected configured policy violation is deterministic negative evidence.
    if policy_breach:
        checks["policy_compliant"] = False
    available = all(name in checks and isinstance(checks[name], bool) for name in required)
    passed = available and all(checks[name] for name in required)
    failures = [f"{name}_failed" for name in required if available and not checks[name]]
    return {"available": available, "passed": passed, "checks": {name: checks.get(name) for name in required if name in checks},
            "hard_failures": failures}


def _normalize_payload(sample: Mapping[str, Any]) -> str:
    return _safe_text(str(sample.get("user_intent", "")) + "\n" + str(sample.get("latest_response", "")), 4000)


def evaluate_objective_samples(samples: list[dict[str, Any]], cfg: dict[str, Any]) -> list[dict[str, Any]]:
    """Return telemetry plus any explicit deterministic fixture evidence.

    ``semantic_match`` and ``overall_score`` intentionally retain their legacy
    fields for dashboard compatibility, but each is marked telemetry-only and must
    never be used to make a promotion decision.
    """
    evaluator_cfg = cfg.get("evaluator", {}) if isinstance(cfg, Mapping) else {}
    policy_keywords = evaluator_cfg.get("policy_breach_keywords", []) if isinstance(evaluator_cfg, Mapping) else []
    policy_words = [str(item).strip() for item in policy_keywords if str(item).strip()] if isinstance(policy_keywords, list) else []
    risk_threshold = _coerce_unit(evaluator_cfg.get("risk_threshold", 0.25), 0.25) if isinstance(evaluator_cfg, Mapping) else 0.25

    scored: list[dict[str, Any]] = []
    for sample in samples:
        sample = sample if isinstance(sample, Mapping) else {}
        objective = _safe_text(sample.get("user_intent", ""), 1200)
        response = _safe_text(sample.get("latest_response", ""), 3000)
        lexical_similarity = SequenceMatcher(None, objective.lower(), response.lower()).ratio() if objective and response else 0.0
        policy_breach, risk_flags = _contains_policy_issue(response, policy_words, risk_threshold)
        event_count = max(1, int(sample.get("event_count", 0) or 0))
        failures = max(0, int(sample.get("failure_events", 0) or 0))
        tool_names = " ".join(str(item) for item in sample.get("tool_contract", [])).lower() if isinstance(sample.get("tool_contract", []), list) else ""
        command_safety = 0.2 if any(item in tool_names for item in ("rm ", "format", "delete", "shutdown", "kill", "drop")) else (0.95 if any(item in tool_names for item in ("grep", "cat", "ls", "cd", "find")) else 1.0)
        reliability = float(int(sample.get("success_events", 0) or 0)) / event_count
        evidence_recall = min(1.0, event_count / 8.0)
        evidence_precision = max(0.0, 1.0 - failures / event_count)
        answer_quality = min(1.0, lexical_similarity * 0.9 + evidence_precision * 0.1)
        policy_compliance = 1.0 - min(1.0, len(risk_flags) * 0.4)
        telemetry_score = max(0.0, lexical_similarity * .2 + command_safety * .2 + reliability * .18 + evidence_recall * .13 + evidence_precision * .12 + answer_quality * .12 + policy_compliance * .13)
        deterministic = _explicit_deterministic_evidence(sample, policy_breach=policy_breach)
        judge = semantic_judge(sample, cfg)
        if judge is not None:
            lexical_similarity = float(judge["score"])
            answer_quality = float(judge["score"])
            telemetry_score = max(0.0, min(1.0, telemetry_score * 0.35 + float(judge["score"]) * 0.65))
        scored.append({
            "sample": dict(sample),
            "scores": {"semantic_match": float(lexical_similarity), "command_safety": float(command_safety),
                       "execution_reliability": float(reliability), "evidence_recall": float(evidence_recall),
                       "evidence_precision": float(evidence_precision), "answer_quality": float(answer_quality),
                       "policy_compliance": float(policy_compliance)},
            "score_kind": "telemetry_only", "telemetry_only": True,
            "telemetry": {"lexical_similarity": float(lexical_similarity), "telemetry_score": float(telemetry_score),
                          "lexical_method": "sequence_matcher", "semantic_judge": judge},
            "deterministic": deterministic, "risk_flags": risk_flags, "policy_breach": policy_breach,
            "overall_score": float(telemetry_score),
            "rationale": f"telemetry_only lexical={lexical_similarity:.2f}; deterministic_available={deterministic['available']}; policy_flags={','.join(risk_flags) or 'none'}",
            "payload_signature": _safe_text(_normalize_payload(sample), 260),
        })
    return scored


def sample_matrix_scores(results: list[dict[str, Any]]) -> dict[str, float]:
    """Aggregate legacy telemetry only; returned values are not promotion gates."""
    keys = ("command_safety", "execution_reliability", "evidence_recall", "evidence_precision", "answer_quality", "policy_compliance", "semantic_match")
    totals = {key: 0.0 for key in keys}
    if not results:
        return totals
    for result in results:
        scores = result.get("scores", {}) if isinstance(result, Mapping) else {}
        if not isinstance(scores, Mapping):
            continue
        for key in keys:
            totals[key] += _coerce_unit(scores.get(key, 0.0))
    return {key: _coerce_unit(value / len(results)) for key, value in totals.items()}
