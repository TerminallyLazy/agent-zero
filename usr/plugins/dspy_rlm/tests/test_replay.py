"""Task 9 contract coverage for frozen paired offline replay."""
from __future__ import annotations

from collections.abc import Mapping

import pytest

from usr.plugins.dspy_rlm.helpers.evaluation import execute_offline_case
from usr.plugins.dspy_rlm.helpers.replay import (
    PROMOTION_READY,
    REJECTED,
    REVIEW_ONLY,
    FrozenReplayManifest,
    freeze_held_out_cases,
    paired_replay,
)


BASELINE = {"name": "baseline", "scores": {"case-1": 0.8, "case-2": 0.9}}
CANDIDATE = {"name": "candidate", "scores": {"case-1": 0.9, "case-2": 1.0}}


def _cases() -> list[dict[str, object]]:
    return [
        {"case_id": "case-1", "bucket": "reasoning", "fixture": {"input": "one"}},
        {"case_id": "case-2", "bucket": "safety", "fixture": {"input": "two"}},
    ]


def _output(candidate: Mapping[str, object], case: Mapping[str, object], **overrides: object) -> dict[str, object]:
    scores = candidate["scores"]
    assert isinstance(scores, Mapping)
    return {
        "schema_valid": True,
        "policy_compliant": True,
        "safety_passed": True,
        "execution_succeeded": True,
        "deterministic_score": scores[case["case_id"]],
        **overrides,
    }


def _replay(manifest: FrozenReplayManifest, executor, **kwargs: object) -> dict[str, object]:
    return paired_replay(
        manifest,
        baseline=BASELINE,
        candidate=CANDIDATE,
        executor=executor,
        baseline_revision="active-7",
        active_baseline_revision="active-7",
        **kwargs,
    )


def test_held_out_manifest_is_immutable_snapshot_and_disjoint_from_training_cases() -> None:
    source_cases = _cases()
    manifest = freeze_held_out_cases(source_cases, training_case_ids={"training-case"})

    source_cases[0]["fixture"]["input"] = "mutated"  # type: ignore[index]
    assert manifest.cases[0]["fixture"]["input"] == "one"  # type: ignore[index]
    assert manifest.digest == FrozenReplayManifest.from_mapping(manifest.to_mapping()).digest
    with pytest.raises(ValueError, match="overlaps training cases"):
        freeze_held_out_cases(_cases(), training_case_ids={"case-1"})


def test_evaluation_requires_core_checks_even_when_a_case_omits_them() -> None:
    case = {"case_id": "core-checks", "required_checks": ["schema_valid"]}

    result = execute_offline_case(
        lambda _case, _candidate: {"schema_valid": True, "deterministic_score": 1.0},
        case,
        CANDIDATE,
        replay_mode="offline_prompt_output_replay",
    )

    assert result.passed is False
    assert result.hard_failures == (
        "execution_succeeded_failed",
        "policy_compliant_failed",
        "safety_passed_failed",
    )


def test_paired_replay_executes_baseline_and_candidate_on_each_same_frozen_case() -> None:
    calls: list[tuple[str, str, str]] = []

    def executor(case: Mapping[str, object], candidate: Mapping[str, object]) -> dict[str, object]:
        calls.append((str(case["case_id"]), str(candidate["name"]), str(case["fixture"]["input"])))  # type: ignore[index]
        return _output(candidate, case)

    result = _replay(freeze_held_out_cases(_cases()), executor)

    assert result["decision"] == PROMOTION_READY
    assert calls == [
        ("case-1", "baseline", "one"),
        ("case-1", "candidate", "one"),
        ("case-2", "baseline", "two"),
        ("case-2", "candidate", "two"),
    ]
    assert result["coverage"] == {"required": 2, "paired": 2, "adequate": True}


def test_missing_baseline_is_review_only_without_running_candidate() -> None:
    manifest = freeze_held_out_cases(_cases())
    executor = pytest.fail

    result = paired_replay(
        manifest,
        baseline=None,
        candidate=CANDIDATE,
        executor=executor,
        baseline_revision="active-7",
        active_baseline_revision="active-7",
    )

    assert result["decision"] == REVIEW_ONLY
    assert result["passed"] is False
    assert result["reason_codes"] == ["missing_baseline"]
    assert result["coverage"] == {"required": 2, "paired": 0}


def test_hard_failure_rejects_even_when_candidate_average_is_higher() -> None:
    def executor(case: Mapping[str, object], candidate: Mapping[str, object]) -> dict[str, object]:
        if candidate is CANDIDATE and case["case_id"] == "case-1":
            return _output(candidate, case, safety_passed=False, deterministic_score=1.0)
        return _output(candidate, case)

    result = _replay(freeze_held_out_cases(_cases()), executor)

    assert result["candidate_score"] > result["baseline_score"]
    assert result["decision"] == REJECTED
    assert any("candidate:safety_passed_failed" in reason for reason in result["reason_codes"])


def test_protected_bucket_allows_zero_regression_only() -> None:
    regressing_candidate = {"name": "candidate", "scores": {"case-1": 1.0, "case-2": 0.8}}

    def executor(case: Mapping[str, object], candidate: Mapping[str, object]) -> dict[str, object]:
        return _output(candidate, case)

    result = paired_replay(
        freeze_held_out_cases(_cases()),
        baseline=BASELINE,
        candidate=regressing_candidate,
        executor=executor,
        baseline_revision="active-7",
        active_baseline_revision="active-7",
        protected_buckets={"safety"},
        tolerable_regression=1.0,
    )

    assert result["bucket_regressions"]["safety"] == pytest.approx(0.1)
    assert result["decision"] == REJECTED
    assert "protected_bucket_regression:safety" in result["reason_codes"]


def test_malformed_judge_response_is_review_only() -> None:
    def executor(case: Mapping[str, object], candidate: Mapping[str, object]) -> dict[str, object]:
        return _output(candidate, case)

    result = _replay(
        freeze_held_out_cases(_cases()),
        executor,
        judge=lambda _payload: {"verdict": "candidate", "confidence": 1.0},
    )

    assert result["decision"] == REVIEW_ONLY
    assert result["passed"] is False
    assert all(row["judge"] is None for row in result["cases"])
    assert all(row["judge_error"] == "judge_invalid_verdict" for row in result["cases"])
