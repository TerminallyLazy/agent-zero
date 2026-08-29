"""A small, injectable adapter for genuine DSPy GEPA compilation.

The module deliberately does not import DSPy at module import time.  Production can
inject its configured DSPy facade, and tests inject a fake facade.  No installation,
network operation, or global DSPy model configuration is performed here.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import time
from typing import Any, Iterable, Mapping, Sequence

from ..guidance import GuidanceArtifact, GuidanceValidationError, MAX_ARTIFACT_LIFETIME_SECONDS
from ..model_resolution import build_dspy_lm
from ..rlm import RlmFinding
from . import EngineBudget, EngineResult
from .heuristic import finding_hashes, rules_from_findings


ENGINE_VERSION = "gepa.dspy.v1"
PROGRAM_SIGNATURE = "finding_kind,metrics -> rules"
METRIC_NAME = "allowlisted_rule_match"


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)


def _hash(value: Any) -> str:
    return "sha256:" + sha256(_canonical(value).encode("utf-8")).hexdigest()


def _utc(value: datetime | None = None) -> datetime:
    result = value or datetime.now(timezone.utc)
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc).replace(microsecond=0)


def _stamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _safe_metrics(finding: RlmFinding) -> dict[str, float]:
    """Expose only finite numeric aggregates to the declared DSPy program."""
    result: dict[str, float] = {}
    for key, value in finding.metrics.items():
        if not isinstance(key, str):
            continue
        if isinstance(value, bool):
            result[key] = float(value)
        elif isinstance(value, (int, float)):
            number = float(value)
            if number == number and number not in (float("inf"), float("-inf")):
                result[key] = max(-1_000_000.0, min(1_000_000.0, number))
    return dict(sorted(result.items()))


def _findings(findings: Iterable[RlmFinding]) -> tuple[RlmFinding, ...]:
    result: list[RlmFinding] = []
    for finding in findings:
        if not isinstance(finding, RlmFinding):
            raise TypeError("GEPA engine accepts only RlmFinding instances")
        if finding.status == "ok" and not finding.review_only:
            result.append(finding)
    return tuple(result)


def _manifest_hashes(value: Sequence[str] | None, *, fallback: Mapping[str, Any]) -> tuple[str, ...]:
    supplied = tuple(sorted(set(str(item) for item in (value or ()))))
    if supplied and all(item.startswith("sha256:") and len(item) == 71 for item in supplied):
        return supplied
    return (_hash(fallback),)


def _example_payload(finding: RlmFinding) -> dict[str, Any]:
    return {
        "finding_kind": finding.kind,
        "metrics": _safe_metrics(finding),
        # Labels are application-owned rule types, never free-form finding text.
        "rules": tuple(rule["type"] for rule in rules_from_findings((finding,))),
    }


def _make_example(dspy_api: Any, payload: Mapping[str, Any]) -> Any:
    example_type = getattr(dspy_api, "Example", None)
    if not callable(example_type):
        raise TypeError("DSPy Example API is unavailable")
    example = example_type(**dict(payload))
    inputs = getattr(example, "with_inputs", None)
    if not callable(inputs):
        raise TypeError("DSPy Example.with_inputs API is unavailable")
    return inputs("finding_kind", "metrics")


def _make_program(dspy_api: Any) -> Any:
    predict = getattr(dspy_api, "Predict", None)
    if not callable(predict):
        raise TypeError("DSPy Predict API is unavailable")
    # A compact declared signature is portable across DSPy 2.x and simple fakes.
    return predict(PROGRAM_SIGNATURE)


def _metric_score(example: Any, prediction: Any) -> float:
    """Score only allowlisted rule labels.  It must not execute prediction text."""
    expected = getattr(example, "rules", None)
    if expected is None and isinstance(example, Mapping):
        expected = example.get("rules", ())
    observed = getattr(prediction, "rules", None)
    if observed is None and isinstance(prediction, Mapping):
        observed = prediction.get("rules", ())
    expected_set = {str(item) for item in (expected or ())}
    observed_set = {str(item) for item in (observed or ())}
    allowed = {"verify_tool_contract", "check_tool_result", "retry_after_failure", "prefer_reversible_action", "bound_tool_scope"}
    if not observed_set.issubset(allowed):
        return 0.0
    if not expected_set:
        return 1.0 if not observed_set else 0.0
    return len(expected_set & observed_set) / float(len(expected_set | observed_set))


def _metric_factory(dspy_api: Any):
    def metric(example: Any, prediction: Any, trace: Any = None, pred_name: Any = None, pred_trace: Any = None) -> Any:
        score = _metric_score(example, prediction)
        feedback = "Use only approved rule labels and match the evidence-derived target rules."
        prediction_type = getattr(dspy_api, "Prediction", None)
        return prediction_type(score=score, feedback=feedback) if callable(prediction_type) else score
    return metric


def _rule_labels(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (ValueError, TypeError):
            value = [item.strip() for item in value.split(",")]
    if not isinstance(value, (list, tuple, set, frozenset)):
        return ()
    allowed = {"verify_tool_contract", "check_tool_result", "retry_after_failure", "prefer_reversible_action", "bound_tool_scope"}
    return tuple(dict.fromkeys(str(item) for item in value if str(item) in allowed))


class GepaEngine:
    """Invoke DSPy's pinned GEPA API through an injectable adapter boundary."""

    kind = "gepa"
    version = ENGINE_VERSION

    def __init__(self, dspy_api: Any | None = None) -> None:
        self._dspy_api = dspy_api

    @staticmethod
    def capability(dspy_api: Any | None = None) -> tuple[bool, str, Any | None]:
        api = dspy_api
        if api is None:
            try:
                import dspy as api  # type: ignore[no-redef]
            except Exception as error:
                return False, f"dspy import failed: {error}", None
        gepa = getattr(api, "GEPA", None)
        if not callable(gepa):
            return False, "DSPy GEPA API is unavailable", None
        for name in ("Example", "Predict"):
            if not callable(getattr(api, name, None)):
                return False, f"DSPy {name} API is unavailable", None
        return True, "GEPA compile API available", api

    def compile(
        self,
        *,
        context_id: str,
        objective_bucket: str,
        findings: Iterable[RlmFinding],
        model_config_ref: str,
        budget: EngineBudget | None = None,
        train_manifest_hashes: Sequence[str] | None = None,
        dev_manifest_hashes: Sequence[str] | None = None,
        dspy_api: Any | None = None,
        now: datetime | None = None,
        lifetime_seconds: int = 7 * 24 * 60 * 60,
    ) -> EngineResult:
        budget = budget or EngineBudget()
        if not isinstance(budget, EngineBudget):
            raise TypeError("budget must be an EngineBudget")
        if not isinstance(model_config_ref, str) or not model_config_ref.strip() or len(model_config_ref) > 96:
            return EngineResult("failed", self.kind, error="model_config_ref is required")
        selected = _findings(findings)[: budget.max_examples]
        hashes = finding_hashes(selected)
        train_hashes = _manifest_hashes(train_manifest_hashes, fallback={"split": "train", "findings": hashes})
        dev_hashes = _manifest_hashes(dev_manifest_hashes, fallback={"split": "dev", "findings": hashes})
        reproducibility: dict[str, Any] = {
            "engine_version": self.version,
            "dspy_api": "",
            "program_signature": PROGRAM_SIGNATURE,
            "metric": METRIC_NAME,
            "model_config_ref": model_config_ref.strip(),
            "budget": budget.to_mapping(),
            "train_manifest_hashes": list(train_hashes),
            "dev_manifest_hashes": list(dev_hashes),
            "source_finding_hashes": list(hashes),
            "example_count": len(selected),
        }
        if not selected:
            return EngineResult("failed", self.kind, reproducibility=reproducibility, error="no_actionable_rlm_findings")
        available, message, api = self.capability(dspy_api if dspy_api is not None else self._dspy_api)
        if not available:
            return EngineResult("gepa_unavailable", self.kind, reproducibility=reproducibility, error=message)
        assert api is not None
        reproducibility["dspy_api"] = f"{getattr(api, '__name__', api.__class__.__name__)}:{getattr(api, '__version__', 'unknown')}"
        try:
            examples = [_make_example(api, _example_payload(finding)) for finding in selected]
            # Keep train and dev non-empty and deterministic for tiny bounded sets.
            split = max(1, len(examples) - 1)
            trainset = examples[:split]
            valset = examples[split:] or examples[:1]
            program = _make_program(api)
            reflection_lm = build_dspy_lm(api, model_config_ref) if callable(getattr(api, "LM", None)) else None
            compiler = api.GEPA(
                metric=_metric_factory(api),
                max_metric_calls=max(8, budget.max_steps * max(2, len(examples)) * 2),
                reflection_lm=reflection_lm,
                num_threads=budget.num_threads,
            )
            started = time.monotonic()
            # This is the pinned DSPy GEPA operation.  Do not substitute a
            # local reflective prompt when this compile fails or is unavailable.
            context = getattr(api, "context", None)
            if callable(context) and reflection_lm is not None:
                with context(lm=reflection_lm):
                    compiled = compiler.compile(student=program, trainset=trainset, valset=valset)
            else:
                compiled = compiler.compile(student=program, trainset=trainset, valset=valset)
            elapsed = time.monotonic() - started
            reproducibility["compile_seconds"] = round(elapsed, 6)
            reproducibility["compile_return_type"] = f"{type(compiled).__module__}.{type(compiled).__qualname__}"
            observed_cost = self._reported_cost(compiled)
            if observed_cost is not None:
                reproducibility["reported_cost_usd"] = observed_cost
            if elapsed > budget.max_compile_seconds:
                return EngineResult("failed", self.kind, reproducibility=reproducibility, error="compile_runtime_budget_exceeded", compiled_program=compiled)
            if observed_cost is not None and observed_cost > budget.max_cost_usd:
                return EngineResult("failed", self.kind, reproducibility=reproducibility, error="compile_cost_budget_exceeded", compiled_program=compiled)
            artifact = self._artifact_from_compilation(
                compiled=compiled,
                context_id=context_id,
                objective_bucket=objective_bucket,
                findings=selected,
                finding_hashes=hashes,
                manifest_hashes=tuple(sorted(set(train_hashes + dev_hashes))),
                now=now,
                lifetime_seconds=lifetime_seconds,
            )
            reproducibility["artifact_digest"] = artifact.artifact_digest
            # The exact compile return is retained for caller-owned candidate
            # persistence/audit, while GuidanceArtifact remains renderer-safe.
            return EngineResult("succeeded", self.kind, artifact=artifact, reproducibility=reproducibility, compiled_program=compiled)
        except Exception as error:
            return EngineResult("failed", self.kind, reproducibility=reproducibility, error=f"GEPA compile failed: {error}")

    run = compile

    @staticmethod
    def _reported_cost(compiled: Any) -> float | None:
        """Read an explicit numeric cost only; unknown cost is never invented."""
        value = getattr(compiled, "cost_usd", None)
        if value is None and isinstance(compiled, Mapping):
            value = compiled.get("cost_usd")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            numeric = float(value)
            if numeric == numeric and 0.0 <= numeric < float("inf"):
                return numeric
        return None

    def _artifact_from_compilation(
        self,
        *,
        compiled: Any,
        context_id: str,
        objective_bucket: str,
        findings: tuple[RlmFinding, ...],
        finding_hashes: tuple[str, ...],
        manifest_hashes: tuple[str, ...],
        now: datetime | None,
        lifetime_seconds: int,
    ) -> GuidanceArtifact:
        """Accept a returned artifact only if it validates, otherwise build fixed rules.

        A fake or future DSPy program may expose ``guidance_artifact``/``artifact``.
        It is never trusted unless it is a valid GEPA-labelled artifact scoped to this
        invocation.  Normal DSPy programs return a program object, so fixed rules are
        derived only from typed aggregate findings after successful compilation.
        """
        for name in ("guidance_artifact", "artifact"):
            candidate = getattr(compiled, name, None)
            if candidate is None and isinstance(compiled, Mapping):
                candidate = compiled.get(name)
            if isinstance(candidate, GuidanceArtifact):
                candidate = candidate.to_mapping()
            if isinstance(candidate, Mapping):
                try:
                    artifact = GuidanceArtifact.from_mapping(candidate)
                    if artifact.engine_kind == self.kind and artifact.context_id == context_id and artifact.objective_bucket == objective_bucket:
                        return artifact
                except GuidanceValidationError:
                    pass
        # Execute the compiled program and project only its approved rule labels.
        observed: list[str] = []
        if callable(compiled):
            for finding in findings:
                prediction = compiled(finding_kind=finding.kind, metrics=_safe_metrics(finding))
                raw_rules = getattr(prediction, "rules", prediction.get("rules") if isinstance(prediction, Mapping) else ())
                observed.extend(_rule_labels(raw_rules))
        rules = [
            {"type": label, **({"max_retries": 1} if label == "retry_after_failure" else {})}
            for label in dict.fromkeys(observed)
        ]
        if not rules:
            raise GuidanceValidationError("compiled GEPA program produced no approved guidance rules")
        issued = _utc(now)
        expires = issued + timedelta(seconds=max(1, min(int(lifetime_seconds), MAX_ARTIFACT_LIFETIME_SECONDS)))
        token = _hash({"compiled_type": f"{type(compiled).__module__}.{type(compiled).__qualname__}", "findings": finding_hashes, "manifests": manifest_hashes})[-20:]
        return GuidanceArtifact.create(
            artifact_id=f"gepa-{token}", context_id=context_id, objective_bucket=objective_bucket,
            rules=rules, source_manifest_hashes=manifest_hashes, source_finding_hashes=finding_hashes,
            issued_at=_stamp(issued), expires_at=_stamp(expires), engine_kind=self.kind, engine_version=self.version,
        )


__all__ = ["ENGINE_VERSION", "GepaEngine", "METRIC_NAME", "PROGRAM_SIGNATURE"]
