from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any


PLUGIN_NAME = "dspy_rlm"


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return bool(int(value))
    if isinstance(value, str):
        text = value.strip().lower()
        return text in {"1", "true", "yes", "on", "y", "enabled"}
    return default


def _as_int(
    value: Any,
    default: int,
    min_value: int = 0,
    max_value: int | None = None,
) -> int:
    try:
        numeric = int(value)
    except Exception:
        return default
    if numeric < min_value:
        numeric = min_value
    if max_value is not None:
        numeric = min(max_value, numeric)
    return numeric


def _as_float(
    value: Any,
    default: float,
    min_value: float = 0.0,
    max_value: float | None = None,
) -> float:
    try:
        numeric = float(value)
    except Exception:
        return default
    if numeric < min_value:
        numeric = min_value
    if max_value is not None:
        numeric = min(max_value, numeric)
    return numeric


def _as_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def _as_list(value: Any, default: list[str] | None = None) -> list[str]:
    if default is None:
        default = []
    if value is None:
        return list(default)
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, tuple):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return list(default)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _coerce_matrix_bucket(source: dict[str, Any], defaults: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(defaults)
    for key, value in source.items():
        if key not in normalized:
            normalized[key] = value
            continue

        current = normalized[key]
        if isinstance(current, bool):
            normalized[key] = _as_bool(value, current)
            continue
        if isinstance(current, int):
            normalized[key] = _as_int(value, current)
            continue
        if isinstance(current, float):
            normalized[key] = _as_float(value, current)
            continue
        if isinstance(current, list):
            normalized[key] = _as_list(value, current)
            continue
        normalized[key] = value

    return normalized


def deep_merge_config(base: dict[str, Any] | None, override: dict[str, Any] | None) -> dict[str, Any]:
    """Return a non-mutating recursive merge for plugin configuration maps.

    Lists and scalar values are replaced wholesale.  That avoids accidentally
    combining policy lists or partial scalar values from different config scopes.
    """
    merged = deepcopy(base) if isinstance(base, dict) else {}
    if not isinstance(override, dict):
        return merged
    for key, value in override.items():
        previous = merged.get(key)
        if isinstance(previous, dict) and isinstance(value, dict):
            merged[key] = deep_merge_config(previous, value)
        else:
            merged[key] = deepcopy(value)
    return merged


def _nested_value(source: dict[str, Any], section: str, key: str | None) -> Any:
    if key is None:
        return source.get(section)
    value = source.get(section)
    return value.get(key) if isinstance(value, dict) else None


def _set_nested_value(source: dict[str, Any], section: str, key: str | None, value: Any) -> None:
    if key is None:
        source[section] = value
        return
    bucket = source.get(section)
    if not isinstance(bucket, dict):
        bucket = {}
        source[section] = bucket
    bucket[key] = value


def _alias_values_match(values: list[Any], *, boolean: bool) -> bool:
    if boolean:
        return len({_as_bool(value, False) for value in values}) == 1
    # Config files routinely represent numbers as strings.  Treat equivalent
    # textual values as one setting, while retaining a fail-closed conflict for
    # genuinely different aliases.
    normalized: set[str] = set()
    for value in values:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            normalized.add(str(value))
        else:
            normalized.add(str(value).strip())
    return len(normalized) == 1


def _legacy_to_nested(source: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Migrate flat v1 aliases without allowing conflicting gates to enable work.

    Migration operates on caller-provided settings before defaults are merged, so
    an omitted v1 field never conflicts with a v2 default.  Compatibility aliases
    are retained later in :func:`normalize_config` for existing UI/runtime callers.
    """
    migrated = deepcopy(source)
    diagnostics: list[str] = []
    mappings: tuple[tuple[str, str | None, tuple[str, ...], bool], ...] = (
        ("enabled", None, ("plugin_enabled",), True),
        ("instrumentation_enabled", None, ("trace_enabled",), True),
        ("status_refresh_seconds", None, (), False),
        ("optimization", "auto_optimize", ("auto_optimize", "auto_optimize_enabled", "auto_enqueue"), True),
        ("optimization", "auto_optimize_interval_messages", ("optimization_interval_messages",), False),
        ("optimization", "min_samples_for_promotion", ("optimization_min_samples",), False),
        ("optimization", "optimization_preview_limit", ("optimization_preview_limit",), False),
        ("optimization", "cooldown_hours", ("optimization_cooldown_hours",), False),
        ("optimization", "enable_dspy_optimizer", ("enable_dspy_optimizer",), True),
        ("optimization", "dry_run_mode", ("dry_run_mode",), True),
        ("optimization", "dry_run_promote_only", ("dry_run_promote_only",), True),
        ("optimization", "ge_pa_steps", ("gepa_steps", "ge_pa_steps"), False),
        ("optimization", "ge_pa_threads", ("gepa_threads", "ge_pa_threads"), False),
        ("optimization", "auto_optimize_interval_minutes", ("optimization_interval_minutes",), False),
        ("optimization", "retain_samples_per_context", ("max_samples_per_context",), False),
        ("trace_capture", "max_events_per_context", ("optimization_trace_window", "max_events_per_context"), False),
        ("trace_capture", "event_ttl_seconds", ("trace_retention_limit",), False),
        ("trace_capture", "max_event_payload_chars", ("trace_capture_max_event_payload_chars",), False),
        ("trace_capture", "min_tool_calls_for_sample", ("trace_capture_min_tool_calls_for_sample",), False),
        ("trace_capture", "max_events_per_loop", ("max_events_per_loop",), False),
        ("scheduler", "mode", ("scheduler_mode",), False),
        ("scheduler", "max_workers", ("scheduler_max_workers",), False),
        ("scheduler", "poll_interval_seconds", ("scheduler_poll_interval_seconds",), False),
        ("scheduler", "job_lease_seconds", ("scheduler_job_lease_seconds",), False),
        ("scheduler", "max_retries", ("scheduler_max_retries",), False),
    )
    for section, destination, aliases, is_boolean in mappings:
        entries: list[tuple[str, Any]] = []
        canonical = _nested_value(migrated, section, destination)
        if canonical is not None:
            entries.append((f"{section}.{destination}" if destination else section, canonical))
        for alias in aliases:
            if alias in migrated:
                entries.append((alias, migrated[alias]))
        if not entries:
            continue
        values = [value for _, value in entries]
        if not _alias_values_match(values, boolean=is_boolean):
            names = ", ".join(name for name, _ in entries)
            diagnostics.append(f"conflicting legacy aliases for {section}.{destination}: {names}")
            # A conflicting enablement alias must never turn a capability on.
            if is_boolean:
                _set_nested_value(migrated, section, destination, False)
            continue
        _set_nested_value(migrated, section, destination, values[0])
    return migrated, diagnostics


def _load_default() -> dict[str, Any]:
    plugin_root = Path(__file__).resolve().parents[1]
    config_path = plugin_root / "default_config.yaml"
    if not config_path.exists():
        return {}

    try:
        text = config_path.read_text(encoding="utf-8")
    except Exception:
        return {}

    from helpers import yaml as yaml_helper

    try:
        payload = yaml_helper.loads(text)
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def normalize_config(config: dict[str, Any] | None) -> dict[str, Any]:
    """Normalize an effective v2 configuration without mutating caller data.

    Defaults are always merged before coercion.  This makes a sparse saved
    configuration behave exactly like a complete one and preserves defaults for
    sections introduced in newer plugin versions.
    """
    default_settings, default_diagnostics = _legacy_to_nested(_load_default())
    supplied_settings, supplied_diagnostics = _legacy_to_nested(_as_dict(config))
    cfg = deep_merge_config(default_settings, supplied_settings)
    diagnostics = [*default_diagnostics, *supplied_diagnostics]

    normalized: dict[str, Any] = {
        "schema_version": "2",
        "config_version": 2,
        "enabled": _as_bool(cfg.get("enabled"), False),
        # These fallbacks also apply when the checked-in default file cannot be
        # read.  They must therefore be inert rather than convenience-on.
        "instrumentation_enabled": _as_bool(cfg.get("instrumentation_enabled", False), False),
        "status_refresh_seconds": _as_int(cfg.get("status_refresh_seconds", 8), 8, 1, 120),
    }

    trace_capture_defaults = {
        "max_events_per_context": 1800,
        "max_events_per_loop": 160,
        "max_event_payload_chars": 1400,
        "min_tool_calls_for_sample": 1,
        "event_ttl_seconds": 604_800,
    }
    normalized["trace_capture"] = _coerce_matrix_bucket(
        _as_dict(cfg.get("trace_capture")),
        trace_capture_defaults,
    )
    normalized["trace_capture"]["max_events_per_context"] = _as_int(
        normalized["trace_capture"].get("max_events_per_context"),
        trace_capture_defaults["max_events_per_context"],
        10,
        2_000_000,
    )
    normalized["trace_capture"]["max_events_per_loop"] = _as_int(
        normalized["trace_capture"].get("max_events_per_loop"),
        trace_capture_defaults["max_events_per_loop"],
        1,
        10_000,
    )
    normalized["trace_capture"]["max_event_payload_chars"] = _as_int(
        normalized["trace_capture"].get("max_event_payload_chars"),
        trace_capture_defaults["max_event_payload_chars"],
        64,
        20_000,
    )
    normalized["trace_capture"]["min_tool_calls_for_sample"] = _as_int(
        normalized["trace_capture"].get("min_tool_calls_for_sample"),
        trace_capture_defaults["min_tool_calls_for_sample"],
        0,
    )
    normalized["trace_capture"]["event_ttl_seconds"] = _as_int(
        normalized["trace_capture"].get("event_ttl_seconds"),
        trace_capture_defaults["event_ttl_seconds"],
        60,
        31_536_000,
    )

    optimization_defaults = {
        # Fall closed if packaged defaults are unavailable.  A sparse explicit
        # config can opt in to each capability independently.
        "enabled": False,
        "auto_optimize": False,
        "auto_promote": False,
        # This only controls the manual entry point and is ineffective until the
        # primary optimization capability is explicitly enabled.
        "manual_optimize": True,
        "auto_optimize_interval_messages": 12,
        "auto_optimize_interval_minutes": 180,
        "min_samples_for_promotion": 10,
        "confidence_floor": 0.70,
        "global_score_threshold": 0.80,
        "max_samples_per_objective": 40,
        "max_active_objectives_per_context": 8,
        "objective_signature_lookback": 25,
        "retain_samples_per_context": 3_000,
        "max_sample_size_chars": 2_400,
        "cooldown_hours": 6,
        "enable_dspy_optimizer": True,
        "dry_run_mode": False,
        "dry_run_promote_only": False,
        "replay_set_size": 6,
        "replay_tolerable_regression": 0.10,
        "ge_pa_steps": 3,
        "ge_pa_threads": 2,
        "max_evaluation_batch": 10,
        "optimization_preview_limit": 20,
        "enable_replay_audit": True,
        "replay_audit_sample_size": 6,
        "max_concurrent_candidates": 4,
        "max_compile_seconds": 120.0,
        "max_cost_usd": 5.0,
    }
    normalized["optimization"] = _coerce_matrix_bucket(
        _as_dict(cfg.get("optimization")),
        optimization_defaults,
    )
    normalized_opt = normalized["optimization"]
    normalized_opt["enabled"] = _as_bool(
        normalized_opt.get("enabled"), optimization_defaults["enabled"]
    )
    normalized_opt["auto_optimize"] = _as_bool(
        normalized_opt.get("auto_optimize"), optimization_defaults["auto_optimize"]
    )
    # Promotion is deliberately opt-in, even for legacy configurations.  A
    # missing value must not make an optimizer eligible to change guidance.
    normalized_opt["auto_promote"] = _as_bool(normalized_opt.get("auto_promote"), False)
    normalized_opt["manual_optimize"] = _as_bool(normalized_opt.get("manual_optimize"), True)
    normalized_opt["enable_dspy_optimizer"] = _as_bool(
        normalized_opt.get("enable_dspy_optimizer"), optimization_defaults["enable_dspy_optimizer"]
    )
    normalized_opt["dry_run_mode"] = _as_bool(
        normalized_opt.get("dry_run_mode"), optimization_defaults["dry_run_mode"]
    )
    normalized_opt["dry_run_promote_only"] = _as_bool(
        normalized_opt.get("dry_run_promote_only"), optimization_defaults["dry_run_promote_only"]
    )
    normalized_opt["auto_optimize_interval_messages"] = _as_int(
        normalized_opt.get("auto_optimize_interval_messages"),
        optimization_defaults["auto_optimize_interval_messages"],
        1,
        10_000,
    )
    normalized_opt["min_samples_for_promotion"] = _as_int(
        normalized_opt.get("min_samples_for_promotion"),
        optimization_defaults["min_samples_for_promotion"],
        1,
        1_000,
    )
    normalized_opt["confidence_floor"] = _as_float(
        normalized_opt.get("confidence_floor"),
        optimization_defaults["confidence_floor"],
        0.0,
        1.0,
    )
    normalized_opt["global_score_threshold"] = _as_float(
        normalized_opt.get("global_score_threshold"),
        optimization_defaults["global_score_threshold"],
        0.0,
        1.0,
    )
    normalized_opt["replay_tolerable_regression"] = _as_float(
        normalized_opt.get("replay_tolerable_regression"),
        optimization_defaults["replay_tolerable_regression"],
        0.0,
        1.0,
    )
    normalized_opt["max_sample_size_chars"] = _as_int(
        normalized_opt.get("max_sample_size_chars"),
        optimization_defaults["max_sample_size_chars"],
        64,
        100_000,
    )
    normalized_opt["cooldown_hours"] = _as_int(
        normalized_opt.get("cooldown_hours"),
        optimization_defaults["cooldown_hours"],
        0,
        8_760,
    )
    normalized_opt["ge_pa_steps"] = _as_int(
        normalized_opt.get("ge_pa_steps", normalized_opt.get("gepa_steps", optimization_defaults["ge_pa_steps"])),
        optimization_defaults["ge_pa_steps"],
        1,
        64,
    )
    normalized_opt["ge_pa_threads"] = _as_int(
        normalized_opt.get("ge_pa_threads", normalized_opt.get("gepa_threads", optimization_defaults["ge_pa_threads"])),
        optimization_defaults["ge_pa_threads"],
        1,
        32,
    )
    normalized_opt["max_active_objectives_per_context"] = _as_int(
        normalized_opt.get("max_active_objectives_per_context"),
        optimization_defaults["max_active_objectives_per_context"],
        1,
        64,
    )
    normalized_opt["replay_set_size"] = _as_int(
        normalized_opt.get("replay_set_size"),
        optimization_defaults["replay_set_size"],
        1,
        20,
    )
    normalized_opt["max_evaluation_batch"] = _as_int(
        normalized_opt.get("max_evaluation_batch"),
        optimization_defaults["max_evaluation_batch"],
        1,
        128,
    )
    normalized_opt["optimization_preview_limit"] = _as_int(
        normalized_opt.get("optimization_preview_limit"),
        optimization_defaults["optimization_preview_limit"],
        10,
        10_000,
    )
    normalized_opt["objective_signature_lookback"] = _as_int(
        normalized_opt.get("objective_signature_lookback"),
        optimization_defaults["objective_signature_lookback"],
        1,
        400,
    )
    normalized_opt["retain_samples_per_context"] = _as_int(
        normalized_opt.get("retain_samples_per_context"),
        optimization_defaults["retain_samples_per_context"],
        10,
        200_000,
    )
    normalized_opt["max_active_objectives_per_context"] = _as_int(
        normalized_opt.get("max_active_objectives_per_context"),
        optimization_defaults["max_active_objectives_per_context"],
        1,
        200,
    )
    normalized_opt["gepa_steps"] = _as_int(
        normalized_opt.get("gepa_steps", normalized_opt.get("ge_pa_steps", normalized_opt["ge_pa_steps"])),
        normalized_opt["ge_pa_steps"],
        1,
        128,
    )
    normalized_opt["gepa_threads"] = _as_int(
        normalized_opt.get("gepa_threads", normalized_opt.get("ge_pa_threads", normalized_opt["ge_pa_threads"])),
        normalized_opt["ge_pa_threads"],
        1,
        64,
    )
    normalized_opt["max_concurrent_candidates"] = _as_int(
        normalized_opt.get("max_concurrent_candidates"),
        optimization_defaults["max_concurrent_candidates"],
        1,
        16,
    )
    normalized_opt["max_compile_seconds"] = _as_float(
        normalized_opt.get("max_compile_seconds"), optimization_defaults["max_compile_seconds"], 5.0, 3600.0
    )
    normalized_opt["max_cost_usd"] = _as_float(
        normalized_opt.get("max_cost_usd"), optimization_defaults["max_cost_usd"], 0.0, 1000.0
    )

    scheduler_defaults = {
        "mode": "distributed",
        "max_workers": 2,
        "poll_interval_seconds": 3,
        "job_lease_seconds": 45,
        "max_retries": 2,
        "heartbeat_seconds": 8,
        "stale_worker_seconds": 180,
        "scheduler_lock_ttl_seconds": 30,
        "enforce_single_tenant_per_context": False,
        "backoff_base_seconds": 2,
    }
    normalized["scheduler"] = _coerce_matrix_bucket(
        _as_dict(cfg.get("scheduler")),
        scheduler_defaults,
    )
    normalized["scheduler"]["mode"] = _as_str(
        normalized["scheduler"].get("mode", scheduler_defaults["mode"]),
        scheduler_defaults["mode"],
    ).lower()
    if normalized["scheduler"]["mode"] not in {"single", "distributed"}:
        normalized["scheduler"]["mode"] = "distributed"

    normalized["scheduler"]["max_workers"] = _as_int(
        normalized["scheduler"].get("max_workers"),
        scheduler_defaults["max_workers"],
        1,
        64,
    )
    normalized["scheduler"]["poll_interval_seconds"] = _as_int(
        normalized["scheduler"].get("poll_interval_seconds"),
        scheduler_defaults["poll_interval_seconds"],
        1,
        300,
    )
    normalized["scheduler"]["job_lease_seconds"] = _as_int(
        normalized["scheduler"].get("job_lease_seconds"),
        scheduler_defaults["job_lease_seconds"],
        10,
        2_000,
    )
    normalized["scheduler"]["max_retries"] = _as_int(
        normalized["scheduler"].get("max_retries"),
        scheduler_defaults["max_retries"],
        0,
        50,
    )
    normalized["scheduler"]["heartbeat_seconds"] = _as_int(
        normalized["scheduler"].get("heartbeat_seconds"),
        scheduler_defaults["heartbeat_seconds"],
        2,
        120,
    )
    normalized["scheduler"]["stale_worker_seconds"] = _as_int(
        normalized["scheduler"].get("stale_worker_seconds"),
        scheduler_defaults["stale_worker_seconds"],
        20,
        3_600,
    )
    normalized["scheduler"]["scheduler_lock_ttl_seconds"] = _as_int(
        normalized["scheduler"].get("scheduler_lock_ttl_seconds"),
        scheduler_defaults["scheduler_lock_ttl_seconds"],
        10,
        600,
    )
    normalized["scheduler"]["enforce_single_tenant_per_context"] = _as_bool(
        normalized["scheduler"].get("enforce_single_tenant_per_context"),
        scheduler_defaults["enforce_single_tenant_per_context"],
    )
    normalized["scheduler"]["backoff_base_seconds"] = _as_int(
        normalized["scheduler"].get("backoff_base_seconds"),
        scheduler_defaults["backoff_base_seconds"],
        1,
        120,
    )

    matrix_defaults = {
        "version": "2.0",
        "shell": {
            "enabled": True,
            "command_safety_weight": 0.35,
            "command_safety_threshold": 0.95,
            "command_safety_hard_fail": 0.60,
            "semantic_match_weight": 0.35,
            "semantic_match_threshold": 0.82,
            "execution_reliability_weight": 0.30,
            "execution_reliability_threshold": 0.75,
            "execution_reliability_hard_fail": 0.65,
            "confidence_floor": 0.70,
        },
        "tool_retrieval": {
            "enabled": True,
            "evidence_recall_weight": 0.40,
            "evidence_recall_threshold": 0.78,
            "evidence_recall_hard_fail": 0.50,
            "evidence_precision_weight": 0.40,
            "evidence_precision_threshold": 0.80,
            "semantic_match_weight": 0.20,
            "semantic_match_threshold": 0.70,
            "evidence_precision_hard_fail": 0.55,
            "confidence_floor": 0.70,
        },
        "reasoning": {
            "enabled": True,
            "answer_quality_weight": 0.60,
            "answer_quality_threshold": 0.80,
            "answer_quality_hard_fail": 0.65,
            "policy_compliance_weight": 0.40,
            "policy_compliance_threshold": 1.0,
            "policy_compliance_hard_fail": 1.0,
            "semantic_match_weight": 0.20,
            "semantic_match_threshold": 0.72,
            "semantic_match_hard_fail": 0.50,
            "confidence_floor": 0.75,
        },
        "decision_making": {
            "enabled": True,
            "policy_compliance_weight": 1.0,
            "policy_compliance_threshold": 1.0,
            "policy_compliance_hard_fail": 1.0,
            "semantic_match_weight": 0.30,
            "semantic_match_threshold": 0.75,
            "semantic_match_hard_fail": 0.55,
            "answer_quality_weight": 0.35,
            "answer_quality_threshold": 0.70,
            "answer_quality_hard_fail": 0.50,
            "confidence_floor": 0.70,
        },
    }
    matrix_src = _as_dict(cfg.get("matrix"))
    normalized["matrix"] = {
        "version": _as_str(matrix_src.get("version", matrix_defaults["version"]), matrix_defaults["version"]),
        "shell": _coerce_matrix_bucket(_as_dict(matrix_src.get("shell", {})), matrix_defaults["shell"]),
        "tool_retrieval": _coerce_matrix_bucket(_as_dict(matrix_src.get("tool_retrieval", {})), matrix_defaults["tool_retrieval"]),
        "reasoning": _coerce_matrix_bucket(_as_dict(matrix_src.get("reasoning", {})), matrix_defaults["reasoning"]),
        "decision_making": _coerce_matrix_bucket(_as_dict(matrix_src.get("decision_making", {})), matrix_defaults["decision_making"]),
    }

    evaluator_defaults = {
        "enable_semantic_judge": True,
        "preferred_dspy_model": "",
        "semantic_loop_batch_size": 8,
        "policy_breach_keywords": [
            "forbidden",
            "delete production",
            "drop table",
            "rm -rf /",
            "exfiltrate",
            "secret",
            "pwn",
            "overwrite backups",
            "disable auth",
        ],
        "risk_threshold": 0.25,
        "enable_replay_audit": True,
        "max_replay_depth": 6,
    }
    normalized["evaluator"] = _coerce_matrix_bucket(_as_dict(cfg.get("evaluator")), evaluator_defaults)
    normalized["evaluator"]["policy_breach_keywords"] = _as_list(
        normalized["evaluator"].get("policy_breach_keywords"),
        evaluator_defaults["policy_breach_keywords"],
    )
    normalized["evaluator"]["semantic_loop_batch_size"] = _as_int(
        normalized["evaluator"].get("semantic_loop_batch_size"),
        evaluator_defaults["semantic_loop_batch_size"],
        1,
        64,
    )
    normalized["evaluator"]["risk_threshold"] = _as_float(
        normalized["evaluator"].get("risk_threshold"),
        evaluator_defaults["risk_threshold"],
        0.0,
        1.0,
    )
    normalized["evaluator"]["max_replay_depth"] = _as_int(
        normalized["evaluator"].get("max_replay_depth"),
        evaluator_defaults["max_replay_depth"],
        1,
        20,
    )

    rlm_defaults = {
        "enabled": True,
        "model_ref": "",
        "max_iters": 6,
        "max_llm_calls": 8,
        "max_output_chars": 12_000,
        "max_findings": 12,
    }
    rlm_src = _as_dict(cfg.get("rlm"))
    normalized["rlm"] = {
        "enabled": _as_bool(rlm_src.get("enabled"), rlm_defaults["enabled"]),
        "model_ref": _as_str(rlm_src.get("model_ref"), rlm_defaults["model_ref"]).strip(),
        "max_iters": _as_int(rlm_src.get("max_iters"), rlm_defaults["max_iters"], 1, 20),
        "max_llm_calls": _as_int(rlm_src.get("max_llm_calls"), rlm_defaults["max_llm_calls"], 1, 50),
        "max_output_chars": _as_int(rlm_src.get("max_output_chars"), rlm_defaults["max_output_chars"], 1000, 50_000),
        "max_findings": _as_int(rlm_src.get("max_findings"), rlm_defaults["max_findings"], 1, 32),
    }

    dependency_defaults = {
        "install_mode": "isolated_worker",
        "dependency_file": "requirements.txt",
        "fallback_to_pip": False,
        "ensure_at_startup": True,
        "install_timeout_seconds": 115,
    }
    normalized["dependencies"] = _coerce_matrix_bucket(
        _as_dict(cfg.get("dependencies")), dependency_defaults
    )

    prompt_defaults = {
        # No synthesized guidance may enter the prompt unless an operator has
        # explicitly enabled injection and an artifact exists.
        "inject_guidance": False,
        "inject_even_without_guidance": False,
        "max_injected_chars": 1800,
        "fallback_guidance": "",
    }
    normalized["prompt"] = _coerce_matrix_bucket(_as_dict(cfg.get("prompt")), prompt_defaults)
    normalized["prompt"]["inject_guidance"] = _as_bool(
        normalized["prompt"].get("inject_guidance"), prompt_defaults["inject_guidance"]
    )
    normalized["prompt"]["inject_even_without_guidance"] = _as_bool(
        normalized["prompt"].get("inject_even_without_guidance"), prompt_defaults["inject_even_without_guidance"]
    )
    normalized["prompt"]["max_injected_chars"] = _as_int(
        normalized["prompt"].get("max_injected_chars"),
        prompt_defaults["max_injected_chars"],
        120,
        30_000,
    )
    normalized["prompt"]["fallback_guidance"] = _as_str(
        normalized["prompt"].get("fallback_guidance", prompt_defaults["fallback_guidance"]),
        prompt_defaults["fallback_guidance"],
    )

    prompt_optimization_defaults = {
        "enabled": False,
        "allow_prompt_capture": False,
        "target_mode": "guidance_overlay",
        "activation_mode": "manual",
        "selected_components": [],
        "max_snapshot_chars": 60_000,
        "max_components_per_compile": 4,
        "canary_percentage": 10,
        "canary_min_observations": 10,
        "canary_max_observations": 40,
        "automatic_requires_canary": True,
        "rollback": {
            "enabled": True,
            "maximum_score_regression": 0.05,
            "maximum_failure_rate_increase": 0.05,
        },
    }
    prompt_optimization = _coerce_matrix_bucket(
        _as_dict(cfg.get("prompt_optimization")), prompt_optimization_defaults
    )
    target_mode = _as_str(prompt_optimization.get("target_mode"), "guidance_overlay").strip().lower()
    activation_mode = _as_str(prompt_optimization.get("activation_mode"), "manual").strip().lower()
    selected_components = []
    for component in _as_list(prompt_optimization.get("selected_components")):
        if component.startswith("segment:") and len(component) <= 48 and all(
            character.isalnum() or character in ":_-" for character in component
        ):
            selected_components.append(component)
    rollback = _coerce_matrix_bucket(
        _as_dict(prompt_optimization.get("rollback")),
        prompt_optimization_defaults["rollback"],
    )
    normalized["prompt_optimization"] = {
        "enabled": _as_bool(prompt_optimization.get("enabled"), False),
        "allow_prompt_capture": _as_bool(prompt_optimization.get("allow_prompt_capture"), False),
        "target_mode": target_mode if target_mode in {"guidance_overlay", "selected_components", "assembled_prompt"} else "guidance_overlay",
        "activation_mode": activation_mode if activation_mode in {"manual", "canary", "automatic"} else "manual",
        "selected_components": list(dict.fromkeys(selected_components))[:32],
        "max_snapshot_chars": _as_int(prompt_optimization.get("max_snapshot_chars"), 60_000, 1_000, 250_000),
        "max_components_per_compile": _as_int(prompt_optimization.get("max_components_per_compile"), 4, 1, 12),
        "canary_percentage": _as_int(prompt_optimization.get("canary_percentage"), 10, 1, 100),
        "canary_min_observations": _as_int(prompt_optimization.get("canary_min_observations"), 10, 3, 1_000),
        "canary_max_observations": _as_int(prompt_optimization.get("canary_max_observations"), 40, 3, 5_000),
        # Automatic prompt activation is never allowed to skip the canary phase.
        "automatic_requires_canary": True,
        "rollback": {
            "enabled": _as_bool(rollback.get("enabled"), True),
            "maximum_score_regression": _as_float(rollback.get("maximum_score_regression"), 0.05, 0.0, 1.0),
            "maximum_failure_rate_increase": _as_float(rollback.get("maximum_failure_rate_increase"), 0.05, 0.0, 1.0),
        },
    }
    if normalized["prompt_optimization"]["canary_max_observations"] < normalized["prompt_optimization"]["canary_min_observations"]:
        normalized["prompt_optimization"]["canary_max_observations"] = normalized["prompt_optimization"]["canary_min_observations"]

    # Accept the v2 nested telemetry section.  Flat names remain compatibility
    # aliases only, so a nested explicit false cannot be silently overridden.
    telemetry_src = _as_dict(cfg.get("telemetry"))
    normalized["telemetry"] = {
        "enabled": _as_bool(
            telemetry_src.get("enabled", cfg.get("telemetry_enabled", False)), False
        ),
        "trace_to_runtime": _as_bool(
            telemetry_src.get("trace_to_runtime", cfg.get("trace_to_runtime", False)), False
        ),
    }

    # Schema-v2 controls are intentionally normalized even though their runtime
    # consumers arrive in later phases.  Keeping them here avoids one caller
    # observing a raw setting while another observes an effective default.
    engine = _as_str(cfg.get("engine", "heuristic"), "heuristic").strip().lower()
    normalized["engine"] = engine if engine in {"heuristic", "gepa"} else "heuristic"
    worker_src = _as_dict(cfg.get("worker"))
    worker_backend = _as_str(worker_src.get("backend", "sqlite_local"), "sqlite_local").strip().lower()
    normalized["worker"] = {
        "backend": worker_backend if worker_backend in {"sqlite_local"} else "sqlite_local",
        "max_workers": _as_int(worker_src.get("max_workers", 1), 1, 1, 64),
    }

    normalized.update(
        {
            "auto_optimize_enabled": _as_bool(normalized_opt.get("auto_optimize"), normalized_opt.get("auto_optimize", False)),
            "optimization_interval_messages": _as_int(
                normalized_opt.get("auto_optimize_interval_messages"),
                optimization_defaults["auto_optimize_interval_messages"],
                1,
            ),
            "optimization_min_samples": _as_int(
                normalized_opt.get("min_samples_for_promotion"),
                optimization_defaults["min_samples_for_promotion"],
                1,
            ),
            "optimization_trace_window": _as_int(
                normalized["trace_capture"].get("max_events_per_context", trace_capture_defaults["max_events_per_context"]),
                trace_capture_defaults["max_events_per_context"],
                10,
            ),
            "optimization_cooldown_hours": _as_int(
                normalized_opt.get("cooldown_hours"),
                optimization_defaults["cooldown_hours"],
                0,
            ),
            "enable_dspy_optimizer": _as_bool(normalized_opt.get("enable_dspy_optimizer"), False),
            "gepa_steps": _as_int(normalized_opt.get("ge_pa_steps", optimization_defaults["ge_pa_steps"]), optimization_defaults["ge_pa_steps"], 1),
            "gepa_threads": _as_int(normalized_opt.get("ge_pa_threads", optimization_defaults["ge_pa_threads"]), optimization_defaults["ge_pa_threads"], 1),
            "trace_enabled": _as_bool(normalized.get("instrumentation_enabled"), True),
            "trace_retention_limit": _as_int(
                normalized["trace_capture"].get("event_ttl_seconds"),
                trace_capture_defaults["event_ttl_seconds"],
                60,
            ),
            "status_refresh_seconds": normalized["status_refresh_seconds"],
            "auto_optimize": normalized_opt.get("auto_optimize", False),
            "auto_enqueue": normalized_opt.get("auto_optimize", False),
            "auto_promote": normalized_opt.get("auto_promote", False),
            "manual_optimize": normalized_opt.get("manual_optimize", True),
            "diagnostics": diagnostics,
            "scheduler": normalized["scheduler"],
            "matrix": normalized["matrix"],
            "evaluator": normalized["evaluator"],
            "dependencies": normalized["dependencies"],
            "optimization": normalized["optimization"],
            "trace_capture": normalized["trace_capture"],
            "prompt": normalized["prompt"],
            "telemetry": normalized["telemetry"],
            "engine": normalized["engine"],
            "worker": normalized["worker"],
            "rlm": normalized["rlm"],
        }
    )

    return normalized


def plugin_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_config(agent: Any = None, default: dict[str, Any] | None = None) -> dict[str, Any]:
    """Resolve the effective config through Agent Zero for every caller scope.

    Agent Zero resolves global, project, profile, and project/profile settings.
    Passing ``agent=None`` intentionally still asks that resolver for the global
    setting instead of bypassing saved plugin configuration.
    """
    try:
        from helpers import plugins as plugin_helpers

        resolved = plugin_helpers.get_plugin_config(PLUGIN_NAME, agent=agent)
        if isinstance(resolved, dict):
            return normalize_config(resolved)
    except Exception:
        # Plugin helpers are not available in isolated scripts and unit tests.
        # A supplied fallback remains useful there and never triggers I/O.
        pass
    return normalize_config(default)


def load_config_from_text(raw_text: str | None) -> dict[str, Any]:
    """Compatibility helper retained for callers that only need safe defaults."""
    if not raw_text:
        return normalize_config(None)
    return normalize_config({"_raw": raw_text})
