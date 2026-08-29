"""Queue-only optimization coordinator.

HTTP/plugin hooks enqueue durable local-multiprocess work. Worker lifecycle is
owned by the plugin supervisor at explicit install, config-save, or enqueue
seams; status reads never spawn processes. Promotion is intentionally exposed
only by the :mod:`promotion` coordinator, never by a worker.
"""
from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Any

from . import config as config_module
from . import objective as objective_module
from . import state as state_module
from . import trace as trace_module
from .queue import LocalMultiprocessQueue

_COORDINATORS: dict[str, "SchedulerCoordinator"] = {}


def _plugin_key(plugin_dir: str | Path) -> str:
    return str(Path(plugin_dir).resolve())


def _safe_int(value: Any, fallback: int, *, min_value: int = 0, max_value: int | None = None) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError):
        result = fallback
    return max(min_value, min(result, max_value)) if max_value is not None else max(min_value, result)


def _normalize_mode(value: Any) -> str:
    """Migrate old labels without ever claiming SQLite is multi-host distributed."""
    text = str(value or "local_multiprocess").strip().lower()
    return "single" if text == "single" else "local_multiprocess"


def _objective_signature(context_id: str, cfg: dict[str, Any]) -> tuple[str, str, str]:
    rows = objective_module.collect_recent_objectives(context_id, cfg)
    if not rows:
        return "", "reasoning", ""
    top = rows[0]
    return (
        str(top.get("objective_signature") or ""),
        str(top.get("objective_bucket") or "reasoning"),
        str(top.get("objective_id") or ""),
    )


def _job_signature(context_id: str, summary: dict[str, Any], cfg: dict[str, Any], objective_signature: str) -> str:
    optimization = cfg.get("optimization", {}) if isinstance(cfg, dict) else {}
    payload = "|".join((
        str(context_id), str(objective_signature), str(summary.get("latest_ts") or ""),
        str(summary.get("loop_count") or 0), str(summary.get("tool_count") or 0),
        str(optimization.get("min_samples_for_promotion") or 1),
    ))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def get_scheduler(plugin_dir: str | Path | None = None) -> "SchedulerCoordinator":
    root = Path(__file__).resolve().parents[1] if plugin_dir is None else Path(plugin_dir)
    key = _plugin_key(root)
    coordinator = _COORDINATORS.get(key)
    if coordinator is None:
        coordinator = SchedulerCoordinator(root)
        _COORDINATORS[key] = coordinator
    return coordinator


def schedule_optimization_job(context_id: str, cfg: dict[str, Any] | None = None, force: bool = False, *, plugin_dir: str | Path | None = None) -> dict[str, Any]:
    return get_scheduler(plugin_dir).schedule_job(context_id, cfg, force)


def scheduler_status(plugin_dir: str | Path | None = None, cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    return get_scheduler(plugin_dir).status(cfg)


def stop_scheduler(plugin_dir: str | Path | None = None) -> dict[str, Any]:
    """Compatibility no-op: API no longer owns daemon/process lifecycle."""
    return get_scheduler(plugin_dir).stop()


class SchedulerCoordinator:
    """Request-side coordinator that persists jobs and reports external workers."""

    def __init__(self, plugin_dir: str | Path):
        self.plugin_dir = Path(plugin_dir).resolve()
        self.state = state_module.StateStore(self.plugin_dir)
        self.queue = LocalMultiprocessQueue(state_store=self.state)
        self._stop_requested = False

    def stop(self) -> dict[str, Any]:
        self._stop_requested = True
        return {"stopped": [], "mode": "local_multiprocess", "remaining_workers": len(self.queue.active_workers()), "reason": "workers are explicit CLI processes"}

    def schedule_job(self, context_id: str, cfg: dict[str, Any] | None, force: bool = False) -> dict[str, Any]:
        context_id = str(context_id or "").strip()
        if not context_id:
            return {"job_key": "", "dispatched": False, "status": "invalid", "reason": "context_id is required"}
        cfg = config_module.normalize_config(cfg)
        scheduler_cfg = cfg.get("scheduler", {})
        summary = trace_module.summarize_context(context_id, limit=int(cfg.get("optimization_trace_window", 200)))
        objective_signature, objective_bucket, objective_id = _objective_signature(context_id, cfg)
        signature = _job_signature(context_id, summary, cfg, objective_signature)
        payload = {
            "context_id": context_id,
            "force": bool(force),
            "config": cfg,
            "requested_at": time.time(),
            "objective_signature": signature,
            "source_objective_signature": objective_signature,
            "objective_bucket": objective_bucket,
            "objective_id": objective_id,
            "trace_signature": str(summary.get("latest_ts") or ""),
            "trace_version": "v1",
            "max_retries": _safe_int(scheduler_cfg.get("max_retries", 2), 2, max_value=50),
            "requested_by": "manual" if force else "auto",
            "scheduler_mode": "local_multiprocess",
        }
        job_key, created = self.queue.enqueue(context_id, payload, force=force)
        if created:
            previous = self.state.load_context_state(context_id)
            self.state.set_context_state(context_id, {
                "optimization_running": True, "optimization_status": "queued",
                "optimization_status_message": "Optimization queued for an explicit local worker",
                "optimization_requested_by": payload["requested_by"], "optimization_queue": job_key,
                "optimization_count": int(previous.get("optimization_count", 0) or 0) + 1,
            })
        return {
            "job_key": job_key, "dispatched": created, "status": "queued" if created else "already_queued",
            "reason": "" if created else "A matching job already exists; force cannot replace an active lease.",
            "scheduler": "local_multiprocess", "mode": "local_multiprocess", "requested_force": bool(force),
            "objective_bucket": objective_bucket, "objective_signature": objective_signature,
            "objective_id": objective_id, "context_id": context_id, "worker_count": len(self.queue.active_workers()),
        }

    def status(self, cfg: dict[str, Any] | None = None) -> dict[str, Any]:
        cfg = config_module.normalize_config(cfg)
        scheduler_cfg = cfg.get("scheduler", {})
        runtime = self.state.runtime_status()
        workers = self.queue.active_workers()
        jobs = self.state.get_recent_jobs(limit=25)
        return {
            "mode": "local_multiprocess", "target_workers": int(scheduler_cfg.get("max_workers", 1) or 1),
            "running_workers": len(workers), "active_worker_ids": [row["worker_id"] for row in workers],
            "active_workers": workers, "queue_limit": int(scheduler_cfg.get("job_queue_size", 0) or 0),
            "jobs": runtime.get("jobs", {}), "samples": runtime.get("samples", {}),
            "guidance_rows": runtime.get("guidance_rows", 0), "sample_rows": runtime.get("sample_rows", 0),
            "context_states": runtime.get("context_states", 0), "recent_jobs": jobs[:8],
            "running_jobs": [job for job in jobs if str(job.get("status")) in {"pending", "running", "queued"}],
            "stop_requested": self._stop_requested,
        }
