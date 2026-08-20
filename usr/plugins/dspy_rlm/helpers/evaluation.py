"""Deterministic, offline evaluation primitives for candidate replay.

This module intentionally has no model dependency.  It evaluates only an already
recorded offline fixture response and explicit machine-checkable facts.  Similarity
or language-model judgements belong in ``telemetry``/``judge`` and can never make a
candidate promotable by themselves.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import inspect
import json
from typing import Any, Callable, Mapping, Protocol


REPLAY_MODES = frozenset({"offline_prompt_output_replay", "tool_fixture_replay"})
HARD_CHECKS = ("schema_valid", "policy_compliant", "safety_passed", "execution_succeeded")


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)


def _digest(value: Any) -> str:
    return "sha256:" + sha256(_canonical(value).encode("utf-8")).hexdigest()


def _bounded_score(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number != number:
        return default
    return max(0.0, min(1.0, number))


def _case_id(case: Mapping[str, Any], index: int) -> str:
    value = case.get("case_id", case.get("sample_id", case.get("id", "")))
    return str(value or _digest({"index": index, "case": case})[:24])


def _bucket(case: Mapping[str, Any]) -> str:
    return str(case.get("objective_bucket", case.get("bucket", "reasoning")) or "reasoning")


class OfflineExecutor(Protocol):
    """A side-effect-free adapter which returns one output for a frozen fixture."""

    def __call__(self, case: Mapping[str, Any], candidate: Any) -> Mapping[str, Any]: ...


@dataclass(frozen=True)
class DeterministicEvaluation:
    """The machine-checkable component of a single offline replay case."""

    case_id: str
    bucket: str
    passed: bool
    hard_failures: tuple[str, ...]
    checks: Mapping[str, bool]
    score: float
    confidence: float
    output: Mapping[str, Any]
    telemetry: Mapping[str, Any]
    provenance: Mapping[str, Any]

    def to_mapping(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "bucket": self.bucket,
            "passed": self.passed,
            "hard_failures": list(self.hard_failures),
            "checks": dict(self.checks),
            "score": self.score,
            "confidence": self.confidence,
            "output": dict(self.output),
            "telemetry": dict(self.telemetry),
            "provenance": dict(self.provenance),
        }


def _normalise_output(output: Any) -> dict[str, Any]:
    """Accept an adapter mapping only; malformed executor output fails safely."""
    if not isinstance(output, Mapping):
        return {"execution_succeeded": False, "error_code": "invalid_executor_output"}
    return dict(output)


def deterministic_evaluate(
    case: Mapping[str, Any],
    output: Mapping[str, Any] | Any,
    *,
    replay_mode: str,
    evaluator_provenance: Mapping[str, Any] | None = None,
) -> DeterministicEvaluation:
    """Evaluate explicit fixture facts without inferring quality from text.

    Fixtures/adapters may provide each value in ``HARD_CHECKS`` at the top level or
    under ``checks``.  A case may additionally require named checks through
    ``required_checks``.  Missing required facts are failures, never optimistic
    defaults.  ``score`` is reporting-only after hard checks pass; it cannot repair
    a failed safety/schema/policy/execution check.
    """
    if replay_mode not in REPLAY_MODES:
        raise ValueError("replay_mode must be offline_prompt_output_replay or tool_fixture_replay")
    if not isinstance(case, Mapping):
        raise TypeError("case must be a mapping")
    raw = _normalise_output(output)
    supplied = raw.get("checks") if isinstance(raw.get("checks"), Mapping) else {}
    expected = case.get("expected_checks") if isinstance(case.get("expected_checks"), Mapping) else {}
    required = case.get("required_checks", HARD_CHECKS)
    if not isinstance(required, (list, tuple, set, frozenset)):
        required = HARD_CHECKS
    required_names = tuple(dict.fromkeys(str(item) for item in required if str(item)))
    # Baseline required checks always include the core safety contract.  A fixture
    # can add checks but cannot silently remove them.
    required_names = tuple(dict.fromkeys((*HARD_CHECKS, *required_names)))

    checks: dict[str, bool] = {}
    failures: list[str] = []
    for name in required_names:
        actual = supplied.get(name, raw.get(name))
        expected_value = expected.get(name, True)
        # Explicit expected false represents a fixture asserting the negative
        # condition; match it exactly rather than treating it as a pass by truth.
        passed = isinstance(actual, bool) and actual is bool(expected_value)
        checks[name] = passed
        if not passed:
            failures.append(f"{name}_failed")

    explicit_failures = raw.get("hard_failures", raw.get("hard_fail_flags", []))
    if isinstance(explicit_failures, (list, tuple, set, frozenset)):
        failures.extend(str(item) for item in explicit_failures if str(item))
    elif explicit_failures:
        failures.append("executor_hard_failure")

    # Score is an explicit offline fixture score only.  Existing lexical scores,
    # output text, and judge preference are intentionally not consulted here.
    score = _bounded_score(raw.get("deterministic_score", raw.get("score", 1.0 if not failures else 0.0)))
    confidence = _bounded_score(raw.get("confidence", 1.0 if not failures else 0.0))
    telemetry = raw.get("telemetry", {})
    telemetry = dict(telemetry) if isinstance(telemetry, Mapping) else {"adapter_telemetry": str(telemetry)}
    provenance = {
        "evaluator": "deterministic_offline_v1",
        "replay_mode": replay_mode,
        "case_digest": _digest(dict(case)),
        **(dict(evaluator_provenance) if isinstance(evaluator_provenance, Mapping) else {}),
    }
    return DeterministicEvaluation(
        case_id=_case_id(case, 0), bucket=_bucket(case), passed=not failures,
        hard_failures=tuple(sorted(set(failures))), checks=checks, score=score,
        confidence=confidence, output=raw, telemetry=telemetry, provenance=provenance,
    )


def execute_offline_case(
    executor: Callable[..., Any], case: Mapping[str, Any], candidate: Any, *, replay_mode: str,
    evaluator_provenance: Mapping[str, Any] | None = None,
) -> DeterministicEvaluation:
    """Execute one fixture while requiring the candidate argument to be supplied.

    We support conventional positional adapters and keyword-only adapters.  The
    call is deliberately local and synchronous: replay adapters must represent
    fixtures, not invoke tools, networks, or a live agent.
    """
    if not callable(executor):
        raise TypeError("executor must be callable")
    try:
        signature = inspect.signature(executor)
        parameters = signature.parameters
        # Only use keyword dispatch when the adapter explicitly declares both
        # contract names.  A conventional ``(case, guidance)`` adapter must
        # receive the artifact positionally rather than be mis-called.
        if "case" in parameters and "candidate" in parameters:
            output = executor(case=case, candidate=candidate)
        else:
            output = executor(case, candidate)
    except Exception as error:
        output = {"execution_succeeded": False, "hard_failures": ["executor_exception"], "telemetry": {"error_type": type(error).__name__}}
    return deterministic_evaluate(case, output, replay_mode=replay_mode, evaluator_provenance=evaluator_provenance)


# Deliberate aliases for integrations which use the task terminology.
evaluate_offline_case = deterministic_evaluate
run_offline_case = execute_offline_case
