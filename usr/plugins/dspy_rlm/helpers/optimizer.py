from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime, timezone
from typing import Any

from helpers.print_style import PrintStyle

from . import config as config_module
from . import objective
from . import objective_validation
from . import semantic_evaluator
from . import state as state_module
from .promotion import PromotionCoordinator
from .replay import REVIEW_ONLY, freeze_held_out_cases, paired_replay
from .runtime_policy import RuntimePolicy
from . import trace
from .engines import EngineBudget, GepaEngine, HeuristicEngine
from .guidance import render_guidance_artifact
from .model_resolution import resolve_dspy_model
from .rlm import EvidenceIndex, RlmBudget, RlmController, RlmFinding, RlmQuery
from .dspy_runtime import analyze_with_dspy_rlm
from . import prompt_artifacts
from .engines.prompt_gepa import PromptGepaEngine


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _short(value: Any, max_chars: int) -> str:
    text = str(value or "")
    if len(text) <= max_chars:
        return text
    if max_chars <= 3:
        return text[:max_chars]
    return text[: max_chars - 3] + "..."


def dependency_status() -> tuple[bool, str]:
    """Report GEPA *compile* capability, not merely an import side effect."""
    available, message, _api = GepaEngine.capability()
    return available, message


def _is_in_cooldown(context_state: dict[str, Any], cooldown_hours: int) -> bool:
    if cooldown_hours <= 0:
        return False

    raw_ts = context_state.get("last_optimization_at")
    if not raw_ts:
        return False

    try:
        last = datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00"))
    except Exception:
        return False

    elapsed = datetime.now(timezone.utc) - last
    return elapsed.total_seconds() < (float(cooldown_hours) * 3600.0)


def _build_heuristic_guidance(context_id: str, cfg: dict[str, Any], summary: dict[str, Any], validation: dict[str, Any], objective_summary: dict[str, Any]) -> dict[str, Any]:
    top_tools = summary.get("top_tools", [])
    top_tool = top_tools[0]["tool"] if top_tools else ""
    loop_count = int(summary.get("loop_count", 0) or 0)
    success_rate = float(summary.get("success_rate", 0.0) or 0.0)
    sample_count = int(objective_summary.get("sample_count", 0) or 0)

    lines = [
        "Optimization guidance (heuristic):",
        f"- Context: {context_id or 'unknown'}",
        f"- Last {len(top_tools)} tool families observed; highest cadence: `{top_tool or 'unknown'}`.",
        f"- Loop count: {loop_count}, tool success: {success_rate:.0%}.",
        f"- Samples processed: {sample_count}.",
        f"- Objective gates: {validation.get('reason_code', 'UNKNOWN')}, score={validation.get('global_score', 0.0):.3f}.",
    ]

    by_bucket = sorted(
        ((bucket, details.get("score", 0.0)) for bucket, details in validation.get("bucket_decisions", {}).items()),
        key=lambda item: item[1],
        reverse=True,
    )

    if by_bucket:
        top_bucket, top_score = by_bucket[0]
        lines.append(f"- Lowest-risk bucket to promote first: `{top_bucket}` (score {top_score:.2f}).")

    return {
        "mode": "heuristic",
        "guidance": "\n".join(lines),
        "updated_at": _utc_now_iso(),
    }


def _build_matrix_scores(scored_samples: list[dict[str, Any]]) -> dict[str, Any]:
    scores = semantic_evaluator.sample_matrix_scores(scored_samples)
    bucket_scores: dict[str, float] = {}
    bucket_counts: dict[str, int] = {}
    bucket_matrix: dict[str, Any] = {}
    for row in scored_samples:
        bucket = str(row.get("sample", {}).get("objective_bucket", "reasoning"))
        bucket_scores.setdefault(bucket, 0.0)
        bucket_counts.setdefault(bucket, 0)
        bucket_counts[bucket] += 1
        matrix_row = bucket_matrix.setdefault(
            bucket,
            {
                "rows": 0,
                "semantic_match": 0.0,
                "command_safety": 0.0,
                "execution_reliability": 0.0,
                "evidence_recall": 0.0,
                "evidence_precision": 0.0,
                "answer_quality": 0.0,
                "policy_compliance": 0.0,
            },
        )
        row_scores = row.get("scores", {}) if isinstance(row.get("scores", {}), dict) else {}
        for metric in (
            "semantic_match",
            "command_safety",
            "execution_reliability",
            "evidence_recall",
            "evidence_precision",
            "answer_quality",
            "policy_compliance",
        ):
            matrix_row[metric] += float(row_scores.get(metric, 0.0) or 0.0)
        matrix_row["rows"] += 1

    for matrix_row in bucket_matrix.values():
        denom = max(1, int(matrix_row.get("rows", 0) or 0))
        for metric in (
            "semantic_match",
            "command_safety",
            "execution_reliability",
            "evidence_recall",
            "evidence_precision",
            "answer_quality",
            "policy_compliance",
        ):
            matrix_row[metric] = round(max(0.0, min(1.0, float(matrix_row[metric] / denom))), 6)
    return {
        "overall": scores,
        "bucket_scores": bucket_scores,
        "bucket_counts": bucket_counts,
        "bucket_matrix": bucket_matrix,
    }


def _artifact_fixture_keys(arm: dict[str, Any]) -> tuple[str, ...]:
    """Return stable identities for the exact artifact supplied to replay."""
    artifact = arm.get("guidance_artifact")
    artifact = artifact if isinstance(artifact, dict) else {}
    values = (
        arm.get("guidance_version"), arm.get("artifact_id"), arm.get("artifact_digest"),
        artifact.get("artifact_id"), artifact.get("artifact_digest"), artifact.get("guidance_version"),
    )
    return tuple(dict.fromkeys(str(value) for value in values if isinstance(value, str) and value))


def _artifact_fixture_output(case: dict[str, Any], arm: dict[str, Any]) -> dict[str, Any] | None:
    """Select a frozen output by supplied artifact identity, never just arm role."""
    keys = _artifact_fixture_keys(arm)
    if not keys:
        return None
    for name in ("artifact_outputs", "outputs_by_artifact", "replay_outputs_by_artifact"):
        outputs = case.get(name)
        if not isinstance(outputs, dict):
            continue
        for key in keys:
            value = outputs.get(key)
            if isinstance(value, dict):
                return dict(value)
    # Permit an arm namespace only when it contains identity-indexed fixtures.
    outputs = case.get("replay_outputs")
    role = str(arm.get("role") or "")
    nested = outputs.get(role) if isinstance(outputs, dict) else None
    if isinstance(nested, dict):
        for key in keys:
            value = nested.get(key)
            if isinstance(value, dict):
                return dict(value)
    return None


def _replay_output(case: dict[str, Any], arm: dict[str, Any]) -> dict[str, Any]:
    """Read an artifact-bound offline fixture result; never run a live agent/tool.

    Selecting a direct ``candidate_output`` by role would make replay invariant to
    the supplied guidance artifact, which cannot measure a candidate effect. Frozen
    fixtures must therefore map an artifact version/ID/digest to its recorded output.
    """
    output = _artifact_fixture_output(case, arm)
    if output is not None:
        return output
    return {
        "execution_succeeded": False,
        "hard_failures": ["missing_artifact_bound_offline_replay_output"],
        "telemetry": {"fixture_artifact_keys": list(_artifact_fixture_keys(arm))},
    }


def _replay_case(row: dict[str, Any], index: int) -> dict[str, Any]:
    """Build a held-out fixture from an explicit replay fixture when available."""
    supplied = row.get("replay_case")
    case = dict(supplied) if isinstance(supplied, dict) else {}
    case.setdefault("case_id", str(row.get("sample_id") or row.get("objective_id") or f"objective-{index}"))
    case.setdefault("objective_bucket", str(row.get("objective_bucket") or "reasoning"))
    # Copy only artifact-bound offline fixture data.  This keeps the replay
    # manifest independent from arbitrary objective/trace text and prevents a
    # role-only baseline/candidate fixture from claiming a candidate effect.
    for name in (
        "artifact_outputs", "outputs_by_artifact", "replay_outputs_by_artifact", "replay_outputs",
        "required_checks", "expected_checks", "protected", "protected_bucket",
    ):
        if name in row and name not in case:
            case[name] = row[name]
    return case


def _paired_replay_audit(
    context_id: str,
    cfg: dict[str, Any],
    objective_rows: list[dict[str, Any]],
    candidate_artifact: Any,
    objective_bucket: str,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Freeze and execute the paired replay gate against the current active artifact.

    Unlike the retired score-comparison path, this always delegates readiness to
    ``paired_replay``.  An absent active baseline is deliberately ``review_only``
    and can never be treated as an initial-deployment pass.
    """
    opt = cfg.get("optimization", {}) if isinstance(cfg, dict) else {}
    depth = max(1, int(opt.get("replay_audit_sample_size", opt.get("replay_set_size", 6)) or 6))
    held_out_rows = list(objective_rows[:depth])
    training_ids = [str(row.get("sample_id") or row.get("objective_id") or "") for row in objective_rows[depth:]]
    cases = [_replay_case(row, index) for index, row in enumerate(held_out_rows)]
    # Objective collection has already ensured rows exist; retain a fail-closed
    # audit shape for callers which invoke this helper independently.
    if not cases:
        return ({
            "enabled": True, "passed": False, "decision": REVIEW_ONLY, "promotion_ready": False,
            "reason": "missing_replay_cases", "reason_codes": ["missing_replay_cases"],
            "coverage": {"required": 0, "paired": 0, "adequate": False},
        }, None)
    manifest = freeze_held_out_cases(
        cases,
        training_case_ids=(item for item in training_ids if item),
        provenance={"context_id": context_id, "objective_bucket": objective_bucket, "source": "optimizer_objectives"},
    )
    state = state_module._store_for_root()
    active = state.get_active_guidance(context_id, objective_bucket)
    baseline_artifact = active.get("metadata", {}).get("guidance_artifact") if isinstance(active, dict) and isinstance(active.get("metadata"), dict) else None
    baseline_revision = str(active.get("guidance_version") or "") if isinstance(active, dict) else None
    candidate = {"role": "candidate", "guidance_version": candidate_artifact.artifact_id, "guidance_artifact": candidate_artifact.to_mapping()}
    baseline = (
        {"role": "baseline", "guidance_version": baseline_revision, "guidance_artifact": baseline_artifact}
        if isinstance(baseline_artifact, dict) and baseline_revision else None
    )

    def executor(case: dict[str, Any], arm: dict[str, Any]) -> dict[str, Any]:
        return _replay_output(case, arm)

    audit = paired_replay(
        manifest,
        baseline=baseline,
        candidate=candidate,
        executor=executor,
        baseline_revision=baseline_revision,
        active_baseline_revision=baseline_revision,
        protected_buckets=opt.get("protected_replay_buckets", ()),
        tolerable_regression=float(opt.get("replay_tolerable_regression", 0.10) or 0.10),
        evaluator_provenance={"context_id": context_id, "candidate_guidance_version": candidate_artifact.artifact_id},
    )
    return audit, manifest.to_mapping()

def _build_guidance_metadata(
    context_id: str,
    objective_rows: list[dict[str, Any]],
    validation: dict[str, Any],
    replay: dict[str, Any],
    matrix_scores: dict[str, Any],
    mode: str,
    candidate_guidance: str,
) -> dict[str, Any]:
    objective_signature = ""
    objective_bucket = "reasoning"
    if objective_rows:
        candidate = objective_rows[0]
        objective_signature = str(candidate.get("objective_signature") or candidate.get("objective_id") or "")
        objective_bucket = str(candidate.get("objective_bucket") or "reasoning")

    guid_hash = hashlib.sha1(
        (f"{context_id}|{objective_signature}|{_short(candidate_guidance, 120)}").encode("utf-8")
    ).hexdigest()[:16]

    return {
        "objective_signature": objective_signature,
        "objective_bucket": objective_bucket,
        "guidance_version": f"dspy-rlm-{guid_hash}",
        "mode": mode,
        "generated_at": _utc_now_iso(),
        "validation": {
            "passed": validation.get("passed", False),
            "reason_code": validation.get("reason_code"),
            "global_score": validation.get("global_score"),
            "hard_fail_flags": validation.get("hard_fail_flags", []),
            "bucket_scores": validation.get("bucket_scores", {}),
            "sample_count": validation.get("sample_count", 0),
        },
        "replay": {
            "enabled": replay.get("enabled", False),
            "passed": replay.get("passed", False),
            "reason": replay.get("reason"),
        },
        "matrix_scores": matrix_scores,
    }


def _engine_budget(cfg: dict[str, Any]) -> EngineBudget:
    """Build a bounded GEPA budget from existing normalized settings only."""
    opt = cfg.get("optimization", {}) if isinstance(cfg, dict) else {}
    return EngineBudget(
        max_examples=max(1, int(opt.get("max_samples_per_objective", 40) or 40)),
        # No cost estimate is trustworthy without a configured accounting adapter.
        # Zero is persisted as an explicit no-unbounded-cost budget declaration.
        max_cost_usd=max(0.0, float(opt.get("max_cost_usd", 5.0) or 0.0)),
        max_compile_seconds=max(5.0, float(opt.get("max_compile_seconds", 120.0) or 120.0)),
        max_steps=max(1, int(opt.get("gepa_steps", opt.get("ge_pa_steps", 3)) or 3)),
        num_threads=max(1, int(opt.get("gepa_threads", opt.get("ge_pa_threads", 1)) or 1)),
    )


def _rlm_findings_for_context(context_id: str, objective_bucket: str) -> tuple[RlmFinding, ...]:
    """Analyze trace projections through the typed, bounded RLM seam only."""
    events = trace.read_context_events(context_id, limit=160)
    try:
        index = EvidenceIndex(events)
        query = RlmQuery("objective_bucket", {"objective_bucket": objective_bucket})
        return RlmController(index, RlmBudget(max_depth=1, max_queries=3, max_evidence_chars=8_000, max_findings=3)).analyze(query)
    except (TypeError, ValueError):
        # Failed evidence projection must not become a free-form fallback candidate.
        return ()


def _configured_rlm_findings(context_id: str, objective_bucket: str, cfg: dict[str, Any]) -> tuple[RlmFinding, ...]:
    events = trace.read_context_events(context_id, limit=160)
    try:
        index = EvidenceIndex(events)
    except (TypeError, ValueError):
        return ()
    model_findings = analyze_with_dspy_rlm(index, objective_bucket, cfg)
    if model_findings:
        return model_findings
    return RlmController(index, RlmBudget(max_depth=1, max_queries=3, max_evidence_chars=8_000, max_findings=3)).analyze(
        RlmQuery("objective_bucket", {"objective_bucket": objective_bucket})
    )


def _candidate_engine_result(
    context_id: str,
    objective_bucket: str,
    cfg: dict[str, Any],
) -> tuple[Any, Any | None]:
    """Return the selected successful result and a separate GEPA attempt result.

    GEPA is selected only after its actual ``compile`` returns a valid artifact.  A
    missing dependency or compile error remains visible as ``gepa_unavailable`` or
    ``failed`` and never turns a heuristic artifact into a GEPA-labelled one.
    """
    findings = _configured_rlm_findings(context_id, objective_bucket, cfg)
    heuristic = HeuristicEngine().compile(
        context_id=context_id,
        objective_bucket=objective_bucket,
        findings=findings,
    )
    opt = cfg.get("optimization", {}) if isinstance(cfg, dict) else {}
    if not bool(opt.get("enable_dspy_optimizer", False)):
        return heuristic, None
    model_ref = resolve_dspy_model(cfg, "gepa").selector
    gepa = GepaEngine().compile(
        context_id=context_id,
        objective_bucket=objective_bucket,
        findings=findings,
        model_config_ref=model_ref,
        budget=_engine_budget(cfg),
    )
    return (gepa if gepa.succeeded else heuristic), gepa


def _prompt_component_candidate(
    context_id: str,
    cfg: dict[str, Any],
    objective_rows: list[dict[str, Any]],
    validation: dict[str, Any],
) -> dict[str, Any] | None:
    settings = cfg.get("prompt_optimization") if isinstance(cfg.get("prompt_optimization"), dict) else {}
    target_mode = str(settings.get("target_mode") or "guidance_overlay")
    if not bool(settings.get("enabled")) or target_mode == "guidance_overlay":
        return None
    if not bool(settings.get("allow_prompt_capture")):
        return {"status": "review_only", "reason": "prompt_capture_not_approved", "target_mode": target_mode, "promotion_decision": "review_only"}
    if not bool(validation.get("passed")):
        return {"status": "rejected", "reason": "validation_failed", "target_mode": target_mode, "promotion_decision": "reject"}
    snapshot = prompt_artifacts.latest_snapshot(context_id)
    if not snapshot:
        return {"status": "review_only", "reason": "prompt_snapshot_required", "target_mode": target_mode, "promotion_decision": "review_only"}
    activation_mode = str(settings.get("activation_mode") or "manual")
    artifact, compile_result = PromptGepaEngine().compile(
        context_id=context_id, snapshot=snapshot, objective_rows=objective_rows,
        model_config_ref=resolve_dspy_model(cfg, "gepa").selector,
        target_mode=target_mode, activation_mode=activation_mode,
        selected_components=settings.get("selected_components", ()), budget=_engine_budget(cfg),
        max_components=int(settings.get("max_components_per_compile", 4) or 4),
    )
    if artifact is None:
        return {"status": str(compile_result.get("status") or "failed"), "reason": str(compile_result.get("error") or "prompt_compile_failed"), "target_mode": target_mode, "activation_mode": activation_mode, "compile": compile_result, "promotion_decision": "review_only"}
    prompt_artifacts.stage_artifact(artifact)
    activation = prompt_artifacts.begin_activation(artifact, cfg)
    return {
        "status": "candidate" if activation_mode == "manual" else "canary",
        "reason": str(activation.get("reason") or "prompt_candidate_staged"),
        "target_mode": target_mode, "activation_mode": activation_mode,
        "prompt_artifact_id": artifact.artifact_id, "prompt_artifact": artifact.to_mapping(),
        "compile": compile_result, "activation": activation,
        "promotion_decision": "manual_review" if activation_mode == "manual" else "canary",
    }


def _collect_objectives(context_id: str, cfg: dict[str, Any]) -> list[dict[str, Any]]:
    optimization_cfg = cfg.get("optimization", {}) if isinstance(cfg, dict) else {}
    limit = int(optimization_cfg.get("max_samples_per_objective", 40) or 40)
    min_samples = max(1, int(optimization_cfg.get("min_samples_for_promotion", 10) or 10))

    objective_rows = objective.collect_recent_objectives(context_id, cfg)
    if not objective_rows:
        return []

    if len(objective_rows) < min_samples:
        return objective_rows

    if len(objective_rows) > limit:
        return objective_rows[:limit]

    return objective_rows


def _persist_samples(context_id: str, cfg: dict[str, Any], objective_rows: list[dict[str, Any]]) -> list[str]:
    if not objective_rows:
        return []

    stored: list[str] = []
    for item in objective_rows:
        payload = dict(item)
        if not payload.get("objective_id"):
            payload["objective_id"] = objective.objective_payload_key(item)
        payload.setdefault("trace_version", "v1")
        payload.setdefault("baseline_guidance_version", "")
        payload.setdefault("compiled_guidance_version", "")
        if not payload.get("objective_signature"):
            payload["objective_signature"] = str(item.get("objective_signature") or "")

        stored_id = state_module.add_objective_sample(payload)
        stored.append(stored_id)

    # Enforce retention once this batch is recorded.
    retain = int(cfg.get("optimization", {}).get("retain_samples_per_context", 3000) or 3000)
    if retain > 0:
        deleted = state_module._store_for_root().prune_samples(context_id, retain) if hasattr(state_module, "_store_for_root") else 0
    else:
        deleted = 0

    # Keep trace snapshot bounded for the configured event ttl.
    retention_limit = int(cfg.get("trace_retention_limit", 0) or 0)
    if retention_limit > 0:
        try:
            trace.truncate_file(retention_limit)
        except Exception:
            pass

    PrintStyle.debug(f"dspy_rlm persisted {len(stored)} objective samples for {context_id}")
    return stored



def _artifact_id(prefix: str, *parts: Any) -> str:
    value = "|".join(str(part) for part in parts)
    return f"{prefix}-{hashlib.sha256(value.encode('utf-8')).hexdigest()[:24]}"


def _persist_candidate_artifacts(
    context_id: str,
    objective_bucket: str,
    objective_signature: str,
    objective_rows: list[dict[str, Any]],
    candidate_artifact: Any,
    guidance_text: str,
    metadata: dict[str, Any],
    validation: dict[str, Any],
    matrix_scores: dict[str, Any],
    replay_audit: dict[str, Any],
    replay_manifest: dict[str, Any] | None,
    summary: dict[str, Any],
    started_at: str,
) -> dict[str, str]:
    """Append a coherent immutable candidate/run/evaluation/replay record set.

    Staging is intentionally the final guidance operation here: it appends the
    candidate version but never changes ``active_guidance``.  Promotion remains
    an explicit coordinator action in a separate transaction.
    """
    sample_ids = [str(row.get("sample_id") or row.get("objective_id") or "") for row in objective_rows]
    train_manifest_id = _artifact_id("training", context_id, objective_bucket, *sample_ids)
    replay_manifest_id = str((replay_manifest or {}).get("manifest_id") or "")
    run_id = _artifact_id("run", context_id, candidate_artifact.artifact_id, started_at)
    candidate_id = _artifact_id("candidate", run_id, candidate_artifact.artifact_id)
    evaluation_id = _artifact_id("evaluation", candidate_id, candidate_artifact.artifact_digest)
    replay_audit_id = _artifact_id("replay-audit", candidate_id, replay_manifest_id or "none")
    identifiers = {
        "run_id": run_id, "candidate_id": candidate_id, "evaluation_id": evaluation_id,
        "replay_audit_id": replay_audit_id, "training_manifest_id": train_manifest_id,
        "replay_manifest_id": replay_manifest_id,
    }
    metadata.update({
        "candidate_only": True,
        "persistence": identifiers,
        "guidance_artifact": candidate_artifact.to_mapping(),
        "guidance_artifact_digest": candidate_artifact.artifact_digest,
    })
    state = state_module._store_for_root()
    state.store.append_manifest(
        train_manifest_id, context_id, "optimization_training", sample_ids,
        {"objective_bucket": objective_bucket, "objective_signature": objective_signature},
    )
    if replay_manifest is not None:
        replay_ids = [str(case.get("case_id") or "") for case in replay_manifest.get("cases", []) if isinstance(case, dict)]
        state.store.append_manifest(replay_manifest_id, context_id, "paired_replay", replay_ids, replay_manifest)
    PromotionCoordinator(state_store=state, coordinator_id="optimizer").stage(
        context_id, objective_bucket, guidance_text,
        objective_signature=objective_signature,
        guidance_version=candidate_artifact.artifact_id,
        metadata=metadata,
    )
    run_payload = {
        "run_id": run_id, "candidate_id": candidate_id, "context_id": context_id,
        "objective_bucket": objective_bucket, "objective_signature": objective_signature,
        "guidance_version": candidate_artifact.artifact_id, "started_at": started_at,
        "training_manifest_id": train_manifest_id, "replay_manifest_id": replay_manifest_id,
        "validation": validation, "matrix_scores": matrix_scores, "replay_audit_id": replay_audit_id,
        "summary": summary,
    }
    state.store.append_run(run_id, context_id, "candidate", run_payload)
    candidate_payload = {
        "candidate_id": candidate_id, "run_id": run_id, "guidance_version": candidate_artifact.artifact_id,
        "guidance_artifact": candidate_artifact.to_mapping(), "guidance_metadata": metadata,
        "validation": validation, "matrix_scores": matrix_scores, "replay_audit_id": replay_audit_id,
        "replay_manifest_id": replay_manifest_id,
    }
    state.store.append_candidate(candidate_id, context_id, objective_bucket, candidate_payload, run_id=run_id, guidance_version=candidate_artifact.artifact_id)
    state.store.append_evaluation(evaluation_id, candidate_id, {
        "run_id": run_id, "validation": validation, "matrix_scores": matrix_scores,
        "replay_manifest_id": replay_manifest_id,
    })
    state.store.append_replay_audit(replay_audit_id, candidate_id, replay_audit, manifest_id=replay_manifest_id or None)
    return identifiers

def run_optimization_sync(context_id: str, cfg: dict[str, Any], *, force: bool = False) -> dict[str, Any]:
    if not context_id:
        return {"status": "error", "error": "context_id is required"}

    if not cfg:
        cfg = config_module.load_config()

    cfg = config_module.normalize_config(cfg)
    cfg_opt = cfg.get("optimization", {}) if isinstance(cfg, dict) else {}
    policy = RuntimePolicy.from_config(cfg)

    # `force` is intentionally limited to operational admission checks below.
    # It cannot enable a disabled plugin, optimizer, or manual entry point.
    capability_reasons = policy.reasons_for("optimize", force=True)
    if capability_reasons:
        return {
            "status": "skipped",
            "reason": capability_reasons[0],
            "reasons": list(capability_reasons),
        }

    context_state = state_module.load_context_state(context_id)
    if not force and context_state.get("optimization_running"):
        return {"status": "skipped", "reason": "optimization already running", "context_state": context_state}

    cooldown_hours = int(cfg_opt.get("cooldown_hours", 0) or 0)
    if not force and _is_in_cooldown(context_state, cooldown_hours):
        return {
            "status": "skipped",
            "reason": "cooldown_not_elapsed",
            "cooldown_hours": cooldown_hours,
            "last_optimization_at": context_state.get("last_optimization_at", ""),
        }

    state_module.mark_optimization_started(context_id, trigger="manual" if force else "auto")

    optimization_result: dict[str, Any] = {
        "status": "skipped",
        "mode": "heuristic",
        "summary": {},
        "guidance": "",
        "guidance_version": "",
        "validation": {},
        "replay_audit": {},
        "objective_rows": [],
        "matrix_scores": {},
        "trace_summary": {},
        "objective_signature": "",
        "error": "",
        "promotion_decision": "pending",
        "started_at": _utc_now_iso(),
    }

    try:
        trace_window = int(cfg.get("optimization_trace_window", 220) or 220)
        if trace_window <= 0:
            trace_window = 220

        summary = trace.summarize_context(context_id, limit=trace_window)
        optimization_result["trace_summary"] = summary

        objective_rows = _collect_objectives(context_id, cfg)
        objective_count = int(len(objective_rows))

        min_samples = int(cfg_opt.get("min_samples_for_promotion", 10) or 10)
        if objective_count < min_samples and not force:
            result = {
                "status": "skipped",
                "reason": "not_enough_objectives",
                "required_samples": min_samples,
                "available_samples": objective_count,
                "trace_summary": summary,
                "objective_rows": objective_rows,
                "promotion_decision": "defer",
            }
            state_module.mark_optimization_complete(context_id, result)
            return result

        if not objective_rows:
            result = {
                "status": "skipped",
                "reason": "no_objective_samples",
                "trace_summary": summary,
                "objective_rows": objective_rows,
                "promotion_decision": "defer",
            }
            state_module.mark_optimization_complete(context_id, result)
            return result

        if objective_rows:
            _persist_samples(context_id, cfg, objective_rows)

        scored_rows = semantic_evaluator.evaluate_objective_samples(objective_rows, cfg)
        objective_count = max(objective_count, len(scored_rows))
        validation = objective_validation.validate(scored_rows, cfg)
        matrix_scores = _build_matrix_scores(scored_rows)
        prompt_result = _prompt_component_candidate(context_id, cfg, objective_rows, validation)
        if prompt_result is not None:
            prompt_result.update({
                "validation": validation, "matrix_scores": matrix_scores,
                "objective_rows": objective_rows, "trace_summary": summary,
                "started_at": optimization_result["started_at"],
            })
            state_module.mark_optimization_complete(context_id, prompt_result)
            return prompt_result
        objective_bucket = str((objective_rows[0] if objective_rows else {}).get("objective_bucket", "reasoning") or "reasoning")
        objective_signature = str((objective_rows[0] or {}).get("objective_signature") if objective_rows else "")
        candidate, gepa_attempt = _candidate_engine_result(context_id, objective_bucket, cfg)
        candidate_artifact = candidate.artifact if candidate.succeeded else None
        mode = candidate.engine_kind if candidate_artifact is not None else "none"
        guidance_text = render_guidance_artifact(candidate_artifact) if candidate_artifact is not None else ""

        if candidate_artifact is not None:
            replay, replay_manifest = _paired_replay_audit(
                context_id, cfg, objective_rows, candidate_artifact, objective_bucket,
            )
        else:
            replay, replay_manifest = ({
                "enabled": True, "passed": False, "decision": "rejected", "promotion_ready": False,
                "reason": "missing_candidate", "reason_codes": ["missing_candidate"],
                "coverage": {"required": 0, "paired": 0, "adequate": False},
            }, None)
        guidance_meta = _build_guidance_metadata(context_id, objective_rows, validation, replay, matrix_scores, mode, guidance_text)
        guidance_meta.update({
            "engine_result": candidate.to_mapping(),
            "guidance_artifact": candidate_artifact.to_mapping() if candidate_artifact is not None else None,
            "reproducibility": dict(candidate.reproducibility),
            "replay_manifest": replay_manifest,
        })
        if candidate_artifact is not None:
            guidance_meta["guidance_version"] = candidate_artifact.artifact_id
        if gepa_attempt is not None:
            guidance_meta["gepa_attempt"] = gepa_attempt.to_mapping()
        guidance_meta["replay"] = {
            "enabled": replay.get("enabled", False), "passed": replay.get("passed", False),
            "decision": replay.get("decision"), "reason": replay.get("reason"),
            "manifest_id": replay.get("manifest_id", ""), "manifest_digest": replay.get("manifest_digest", ""),
        }

        if candidate_artifact is None:
            optimization_result.update({
                "promotion_decision": "reject", "status": "candidate_rejected",
                "reason": str(candidate.error or "no_valid_guidance_artifact"),
            })
        else:
            identifiers = _persist_candidate_artifacts(
                context_id, objective_bucket, objective_signature, objective_rows, candidate_artifact,
                guidance_text, guidance_meta, validation, matrix_scores, replay, replay_manifest,
                summary, optimization_result["started_at"],
            )
            optimization_result.update(identifiers)
            # The optimizer only stages a candidate. Even a fully-ready replay
            # result needs a distinct coordinator-owned CAS promotion.
            if not bool(validation.get("passed")):
                optimization_result.update({"promotion_decision": "reject", "status": "rejected", "reason": "validation_failed"})
            elif replay.get("decision") == REVIEW_ONLY:
                optimization_result.update({"promotion_decision": REVIEW_ONLY, "status": "candidate", "reason": str(replay.get("reason") or REVIEW_ONLY)})
            elif bool(replay.get("promotion_ready")):
                optimization_result.update({"promotion_decision": "candidate_ready", "status": "candidate", "reason": "candidate_staged_coordinator_promotion_required"})
            else:
                optimization_result.update({"promotion_decision": "reject", "status": "rejected", "reason": str(replay.get("reason") or "replay_reject")})

        optimization_result.update(
            {
                "mode": mode,
                "guidance": guidance_text,
                "guidance_version": guidance_meta.get("guidance_version", ""),
                "validation": validation,
                "replay_audit": replay,
                "replay_manifest": replay_manifest,
                "guidance_metadata": guidance_meta,
                "objective_rows": objective_rows,
                "matrix_scores": matrix_scores,
                "trace_summary": summary,
                "objective_signature": objective_signature,
            }
        )
        state_module.mark_optimization_complete(context_id, optimization_result)
        return optimization_result

    except Exception as error:
        message = str(error)
        PrintStyle.error(f"dspy_rlm optimization failed for {context_id}: {message}")
        optimization_result.update({
            "status": "error",
            "error": message,
            "reason": "optimization_exception",
            "promotion_decision": "reject",
        })
        state_module.mark_optimization_complete(context_id, optimization_result)
        return optimization_result


async def run_optimization(context_id: str, cfg: dict[str, Any], *, force: bool = False) -> dict[str, Any]:
    return await asyncio.to_thread(run_optimization_sync, context_id, cfg, force=force)
