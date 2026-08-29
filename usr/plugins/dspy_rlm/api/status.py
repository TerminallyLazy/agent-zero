"""Context-scoped, redacted status for the DSPy RLM plugin."""
from __future__ import annotations

import asyncio
import math
from collections import Counter
from typing import Any, Callable, Mapping

from agent import AgentContext
from helpers.api import ApiHandler, Request, Response
from helpers.print_style import PrintStyle

from usr.plugins.dspy_rlm.helpers import config as config_module
from usr.plugins.dspy_rlm.helpers.model_resolution import resolve_dspy_model
from usr.plugins.dspy_rlm.helpers.runtime_policy import RuntimePolicy

STATUS_TIMEOUT_SECONDS = 2.0
_PUBLIC_BUCKETS = frozenset({"shell", "tool_retrieval", "reasoning", "decision_making"})
_PUBLIC_JOB_STATUSES = frozenset({"pending", "queued", "running", "candidate", "promoted", "rejected", "succeeded", "failed", "cancelled"})
_PUBLIC_OPTIMIZATION_STATUSES = _PUBLIC_JOB_STATUSES | frozenset({"idle", "skipped", "unknown"})
# Tool labels originate outside this API boundary. Only stable, non-sensitive core
# tool identifiers are allowed in the status projection.
_PUBLIC_TOOL_NAMES = frozenset({
    "a2a_chat", "browser", "call_subordinate", "code_execution", "document_query",
    "editor", "file_browser", "notify_user", "parallel", "python", "response",
    "scheduler", "search", "search_engine", "shell", "skills_tool", "unknown",
    "vision_load", "wait", "web_search",
})
_MAX_PUBLIC_COUNT = 1_000_000


def error_response(status: int, message: str) -> Response:
    """Return deliberately plain public validation errors."""
    return Response(status=status, response=message, mimetype="text/plain")


def resolve_context_config(input: Mapping[str, Any]) -> tuple[Any | None, dict[str, Any] | None, Response | None]:
    """Resolve an already-live Agent Zero context without creating one.

    Plugin APIs are context scoped. ``AgentContext.get`` is intentionally used
    instead of ``use_context``/``AgentContext.use`` so a request cannot select a
    current context or manufacture an unknown one as a side effect.
    """
    context_id = str(input.get("context_id", "") or "").strip()
    if not context_id:
        return None, None, error_response(400, "context_id is required")
    context = AgentContext.get(context_id)
    if context is None:
        return None, None, error_response(404, "context not found")
    agent = getattr(context, "agent0", None) or context
    cfg = config_module.load_config(agent=agent)
    if not RuntimePolicy.from_config(cfg).enabled:
        return None, None, error_response(409, "plugin is disabled for this context")
    return context, cfg, None


def objective_bucket(value: Any) -> str | None:
    bucket = str(value or "").strip()
    return bucket if bucket in _PUBLIC_BUCKETS else None


def required_revision(value: Any) -> int | None:
    """Accept only a non-negative integral CAS revision, never a truthy coercion."""
    if isinstance(value, bool):
        return None
    try:
        revision = int(value)
    except (TypeError, ValueError):
        return None
    if str(value).strip() != str(revision) or revision < 0:
        return None
    return revision


def _nonnegative_int(value: Any, default: int = 0) -> int:
    """Return a bounded integer without letting malformed local state break status."""
    if isinstance(value, bool):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return min(_MAX_PUBLIC_COUNT, max(0, parsed))


def _finite_rate(value: Any) -> float:
    if isinstance(value, bool):
        return 0.0
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError):
        return 0.0
    return min(1.0, max(0.0, parsed)) if math.isfinite(parsed) else 0.0


def public_config(cfg: Mapping[str, Any]) -> dict[str, Any]:
    optimization = cfg.get("optimization") if isinstance(cfg.get("optimization"), Mapping) else {}
    scheduler = cfg.get("scheduler") if isinstance(cfg.get("scheduler"), Mapping) else {}
    rlm = cfg.get("rlm") if isinstance(cfg.get("rlm"), Mapping) else {}
    prompt_optimization = cfg.get("prompt_optimization") if isinstance(cfg.get("prompt_optimization"), Mapping) else {}
    rlm_model = resolve_dspy_model(cfg, "rlm")
    gepa_enabled = bool(optimization.get("enable_dspy_optimizer", cfg.get("enable_dspy_optimizer", False)))
    configured_engine = str(cfg.get("engine") or "").strip().lower()
    engine = configured_engine if configured_engine in {"heuristic", "gepa"} else ("gepa" if gepa_enabled else "heuristic")
    return {
        "enabled": bool(cfg.get("enabled", False)),
        "instrumentation_enabled": bool(cfg.get("instrumentation_enabled", False)),
        "engine": engine,
        "enable_dspy_optimizer": gepa_enabled,
        "rlm": {
            "enabled": bool(rlm.get("enabled", False)),
            "model_configured": rlm_model.configured,
            "model_source": rlm_model.source,
        },
        "optimization": {
            "enabled": bool(optimization.get("enabled", False)),
            "manual_optimize": bool(optimization.get("manual_optimize", False)),
            "auto_optimize": bool(optimization.get("auto_optimize", False)),
            "auto_promote": bool(optimization.get("auto_promote", False)),
            "dry_run_mode": bool(optimization.get("dry_run_mode", False)),
        },
        "scheduler": {
            # SQLite coordination is local to one host. Do not reflect a stale
            # configuration alias such as "distributed" as a capability.
            "mode": "local_multiprocess",
            "max_workers": _nonnegative_int(scheduler.get("max_workers", 1), 1) or 1,
        },
        "prompt_optimization": {
            "enabled": bool(prompt_optimization.get("enabled", False)),
            "capture_approved": bool(prompt_optimization.get("allow_prompt_capture", False)),
            "target_mode": str(prompt_optimization.get("target_mode") or "guidance_overlay"),
            "activation_mode": str(prompt_optimization.get("activation_mode") or "manual"),
            "canary_percentage": _nonnegative_int(prompt_optimization.get("canary_percentage", 10), 10),
        },
    }


def public_context_state(state: Mapping[str, Any]) -> dict[str, Any]:
    """Expose state machine fields, never trace/prompt/guidance payload text."""
    safe: dict[str, Any] = {}
    for key in (
        "optimization_running", "optimization_status", "optimization_count",
        "optimization_queue", "last_optimization_at", "last_guidance_at",
        "last_guidance_version", "attempts_total", "attempts_since_optimization",
        "success_events", "failure_events", "last_objective_bucket",
    ):
        value = state.get(key)
        if isinstance(value, (str, int, float, bool)) or value is None:
            safe[key] = value
    status = str(safe.get("optimization_status") or "unknown")
    safe["optimization_status"] = status if status in _PUBLIC_OPTIMIZATION_STATUSES else "unknown"
    # Worker/optimizer messages can contain exception strings or model output.
    # Return a stable state label instead of reflecting that untrusted text.
    safe["optimization_status_message"] = safe["optimization_status"]
    return safe


def public_trace_summary(summary: Mapping[str, Any]) -> dict[str, Any]:
    """Return the UI's fixed, metadata-only top-tools row contract.

    ``top_tools`` is always a list of ``{"tool": <allowlisted id>, "count":
    <non-negative int>}`` objects. It never reflects arbitrary tool labels or
    trace payload text.
    """
    raw_tools = summary.get("top_tools") if isinstance(summary.get("top_tools"), list) else []
    tool_counts: Counter[str] = Counter()
    for item in raw_tools[:50]:
        if not isinstance(item, Mapping):
            continue
        tool = str(item.get("tool") or "").strip()
        if tool not in _PUBLIC_TOOL_NAMES:
            continue
        count = _nonnegative_int(item.get("count"))
        if count:
            tool_counts[tool] = min(_MAX_PUBLIC_COUNT, tool_counts[tool] + count)
    return {
        "event_count": _nonnegative_int(summary.get("event_count")),
        "loop_count": _nonnegative_int(summary.get("loop_count")),
        "tool_count": _nonnegative_int(summary.get("tool_count")),
        "success_rate": _finite_rate(summary.get("success_rate")),
        "top_tools": [
            {"tool": tool, "count": count}
            for tool, count in sorted(tool_counts.items(), key=lambda item: (-item[1], item[0]))[:10]
        ],
        "latest_ts": str(summary.get("latest_ts") or "")[:64],
    }


def public_job(job: Mapping[str, Any]) -> dict[str, Any]:
    status = str(job.get("status") or "unknown")
    bucket = objective_bucket(job.get("objective_bucket"))
    return {
        "job_key": str(job.get("job_key") or "")[:128],
        "status": status if status in _PUBLIC_JOB_STATUSES else "unknown",
        "objective_bucket": bucket or "",
        "attempts": _nonnegative_int(job.get("attempts")),
        "created_at": job.get("created_at") if isinstance(job.get("created_at"), (str, int, float)) else None,
        "updated_at": job.get("updated_at") if isinstance(job.get("updated_at"), (str, int, float)) else None,
    }


def public_context_samples(metrics: Mapping[str, Any]) -> dict[str, dict[str, int | float]]:
    """Project aggregate sample metrics into the fixed per-bucket UI contract."""
    raw_counts = metrics.get("counts") if isinstance(metrics.get("counts"), Mapping) else {}
    raw_confidence = metrics.get("confidence") if isinstance(metrics.get("confidence"), Mapping) else {}
    return {
        "counts": {
            bucket: _nonnegative_int(value)
            for key, value in raw_counts.items()
            if (bucket := objective_bucket(key)) is not None
        },
        "confidence": {
            bucket: _finite_rate(value)
            for key, value in raw_confidence.items()
            if (bucket := objective_bucket(key)) is not None
        },
    }


def public_active_guidance(active: Mapping[str, Any] | None) -> dict[str, int | str]:
    """Return only the active pointer identity, never rendered guidance or metadata."""
    if not isinstance(active, Mapping):
        return {"guidance_version": "", "revision": 0}
    version = str(active.get("guidance_version") or "").strip()
    # Guidance artifact identifiers are compact and bounded. Do not reflect an
    # arbitrary database string into a browser-facing endpoint if corruption or
    # a legacy record bypassed normal validation.
    if not version or len(version) > 128 or any(character not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.:-" for character in version):
        version = ""
    return {"guidance_version": version, "revision": _nonnegative_int(active.get("revision"))}


def public_scheduler(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    jobs = snapshot.get("recent_jobs") if isinstance(snapshot.get("recent_jobs"), list) else []
    raw_jobs = snapshot.get("jobs") if isinstance(snapshot.get("jobs"), Mapping) else {}
    raw_samples = snapshot.get("samples") if isinstance(snapshot.get("samples"), Mapping) else {}
    return {
        "mode": "local_multiprocess",
        "target_workers": _nonnegative_int(snapshot.get("target_workers")),
        "running_workers": _nonnegative_int(snapshot.get("running_workers")),
        "queue_limit": _nonnegative_int(snapshot.get("queue_limit")),
        "jobs": {
            str(key): _nonnegative_int(value)
            for key, value in raw_jobs.items()
            if str(key) in _PUBLIC_JOB_STATUSES
        },
        "samples": {
            bucket: _nonnegative_int(value)
            for key, value in raw_samples.items()
            if (bucket := objective_bucket(key)) is not None
        },
        "recent_jobs": [public_job(job) for job in jobs[:8] if isinstance(job, Mapping)],
    }


async def safe_eval(label: str, fn: Callable[[], Any], fallback: Any) -> Any:
    try:
        return await asyncio.wait_for(asyncio.to_thread(fn), timeout=STATUS_TIMEOUT_SECONDS)
    except Exception as exc:
        PrintStyle.error(f"dspy_rlm status: {label} unavailable: {exc}")
        return fallback


class Status(ApiHandler):
    async def process(self, input: dict, request: Request) -> dict | Response:
        context, cfg, error = resolve_context_config(input)
        if error:
            return error
        assert context is not None and cfg is not None

        from usr.plugins.dspy_rlm.helpers import dependencies
        from usr.plugins.dspy_rlm.helpers import _scheduler_coordinator as scheduler
        from usr.plugins.dspy_rlm.helpers import state, trace
        from usr.plugins.dspy_rlm.helpers import worker_supervisor
        from usr.plugins.dspy_rlm.helpers import prompt_artifacts

        context_id = str(context.id)
        supervisor = await safe_eval("worker_supervisor.snapshot", lambda: worker_supervisor.snapshot(cfg), {})
        scheduler_snapshot, context_state, trace_summary, recent_jobs, metrics, active_guidance, prompt_status = await asyncio.gather(
            safe_eval("scheduler.status", lambda: scheduler.scheduler_status(cfg=cfg), {}),
            safe_eval("state.load_context_state", lambda: state.load_context_state(context_id), {}),
            safe_eval("trace.summarize_context", lambda: trace.summarize_context(context_id, limit=_nonnegative_int(cfg.get("optimization_trace_window", 200), 200)), {}),
            safe_eval("state.get_recent_jobs", lambda: state.get_recent_jobs(context_id=context_id, limit=10), []),
            safe_eval("state.aggregate_metrics", lambda: state.aggregate_metrics(context_id), {}),
            safe_eval(
                "state.get_active_guidance",
                lambda: {
                    bucket: state._store_for_root().get_active_guidance(context_id, bucket)
                    for bucket in sorted(_PUBLIC_BUCKETS)
                },
                {},
            ),
            safe_eval("prompt_artifacts.public_status", lambda: prompt_artifacts.public_status(context_id), {}),
        )
        diagnostics = dependencies.dependency_diagnostics()
        return {
            "plugin": "dspy_rlm",
            "enabled": True,
            "context_id": context_id,
            "config": public_config(cfg),
            "scheduler": public_scheduler(scheduler_snapshot if isinstance(scheduler_snapshot, Mapping) else {}),
            "worker_supervisor": {
                "desired": _nonnegative_int(supervisor.get("desired")) if isinstance(supervisor, Mapping) else 0,
                "running": _nonnegative_int(supervisor.get("running")) if isinstance(supervisor, Mapping) else 0,
                "reason": str(supervisor.get("reason") or "unknown") if isinstance(supervisor, Mapping) else "unknown",
            },
            # These names are the stable WebUI contract. No diagnostic paths,
            # package-index URLs, import errors, or host environment details leave
            # the process through the status endpoint.
            "dependencies": {
                "gepa_worker_ready": bool(diagnostics.get("ready", False)),
                "lock_manifest": "requirements-gepa.lock",
                "missing_count": _nonnegative_int(len(diagnostics.get("missing", []))),
                "hash_complete": bool(diagnostics.get("hash_complete", False)),
                "setup_mode": "isolated_worker_venv",
            },
            "context_state": public_context_state(context_state if isinstance(context_state, Mapping) else {}),
            "active_guidance": {
                bucket: public_active_guidance(active)
                for bucket, active in (active_guidance.items() if isinstance(active_guidance, Mapping) else ())
            },
            "trace_summary": public_trace_summary(trace_summary if isinstance(trace_summary, Mapping) else {}),
            "recent_jobs": [public_job(job) for job in recent_jobs[:10] if isinstance(job, Mapping)],
            "context_samples": public_context_samples(metrics if isinstance(metrics, Mapping) else {}),
            "prompt_optimization": prompt_status if isinstance(prompt_status, Mapping) else {},
        }
