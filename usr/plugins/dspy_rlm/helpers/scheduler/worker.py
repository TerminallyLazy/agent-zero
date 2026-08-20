"""Execution loop for explicit local-multiprocess DSPy RLM workers."""
from __future__ import annotations

import concurrent.futures
import hashlib
import time
from typing import Any

from .. import config as config_module
from .. import optimizer
from .. import state as state_module
from ..guidance import validate_guidance_artifact
from ..promotion import PromotionCoordinator
from ..queue import LocalMultiprocessQueue


def _settings(cfg: dict[str, Any]) -> dict[str, int]:
    values = cfg.get("scheduler", {}) if isinstance(cfg, dict) else {}
    return {
        "poll": max(1, int(values.get("poll_interval_seconds", 3) or 3)),
        "heartbeat": max(1, int(values.get("heartbeat_seconds", 8) or 8)),
        "lease": max(10, int(values.get("job_lease_seconds", 45) or 45)),
        "retries": max(0, int(values.get("max_retries", 2) or 2)),
        "worker_ttl": max(20, int(values.get("stale_worker_seconds", 180) or 180)),
    }


def _candidate_id(job_key: str, result: dict[str, Any]) -> str:
    text = f"{job_key}|{result.get('guidance_version', '')}|{result.get('guidance', '')}"
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]


def _run_without_promotion(context_id: str, cfg: dict[str, Any], force: bool) -> dict[str, Any]:
    """Run the public candidate-only optimizer.

    The optimizer persists/stages immutable artifacts itself and deliberately has
    no active-pointer write path.  Keeping this call direct avoids the historical
    monkey-patch replay path, which could silently drop audit persistence.
    """
    result = optimizer.run_optimization_sync(context_id, cfg, force=force)
    return result if isinstance(result, dict) else {"status": "error", "error": "optimizer returned a non-object result"}

def _execute_job(queue: LocalMultiprocessQueue, job: dict[str, Any], cfg: dict[str, Any], settings: dict[str, int]) -> tuple[dict[str, Any], str]:
    lease = job["lease"]
    payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
    context_id = str(job.get("context_id") or "")
    run_cfg = payload.get("config") if isinstance(payload.get("config"), dict) else cfg
    run_cfg = config_module.normalize_config(run_cfg)
    force = bool(payload.get("force", False))
    if not context_id:
        return {"status": "error", "error": "Missing context_id in queued job"}, "failed"

    # Run in a thread so the owning process can keep the lease alive during a
    # long optimizer call and stop on a cancellation/fencing loss.
    with concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="dspy-rlm-job") as executor:
        future = executor.submit(_run_without_promotion, context_id, run_cfg, force)
        while not future.done():
            if queue.is_cancelled(lease.job_key):
                # The optimizer cannot be safely killed mid-call; deny its later
                # result because the lease/cancellation no longer authorizes it.
                return {"status": "cancelled", "reason": "cancelled while executing"}, "cancelled"
            if not queue.heartbeat(lease, settings["lease"]):
                return {"status": "lost_lease", "reason": "lease heartbeat rejected"}, "lost_lease"
            queue.heartbeat_worker(lease.worker_id, ttl_seconds=settings["worker_ttl"], current_job=lease.job_key)
            time.sleep(min(settings["heartbeat"], max(1, settings["lease"] // 3)))
        result = future.result()

    result.update({
        "worker_id": lease.worker_id, "scheduler_job_key": lease.job_key,
        "scheduler_job_attempts": int(job.get("attempts", 0) or 0),
        "objective_bucket": str(job.get("objective_bucket") or "reasoning"),
        "objective_signature": str(job.get("objective_signature") or ""),
        "scheduler_mode": "local_multiprocess",
    })

    # The optimizer has already staged a complete immutable artifact set in the
    # authoritative store. Validate the exact serialized artifact again at the
    # worker boundary before making the queued candidate discoverable.
    guidance = str(result.get("guidance") or "")
    metadata = result.get("guidance_metadata") if isinstance(result.get("guidance_metadata"), dict) else {}
    serialized_artifact = metadata.get("guidance_artifact") if isinstance(metadata, dict) else None
    candidate_id = str(result.get("candidate_id") or _candidate_id(lease.job_key, result))
    if guidance and isinstance(serialized_artifact, dict):
        try:
            artifact = validate_guidance_artifact(serialized_artifact)
        except (TypeError, ValueError) as error:
            result.update({"status": "candidate_rejected", "promotion_decision": "reject", "reason": f"invalid_guidance_artifact:{error}"})
            return result, "rejected"
        if artifact.artifact_id != str(result.get("guidance_version") or ""):
            result.update({"status": "candidate_rejected", "promotion_decision": "reject", "reason": "guidance_artifact_version_mismatch"})
            return result, "rejected"
        required = ("run_id", "candidate_id", "evaluation_id", "replay_audit_id", "training_manifest_id", "replay_manifest_id")
        missing = [name for name in required if not str(result.get(name) or "")]
        if missing:
            result.update({"status": "candidate_rejected", "promotion_decision": "reject", "reason": "missing_candidate_audit_records", "missing_records": missing})
            return result, "rejected"
        # Materialize the candidate in the queue's authoritative StateStore too.
        # This is idempotent (all rows are append-only INSERT OR IGNORE) and
        # makes a worker configured with a non-default plugin root self-contained.
        identifiers = {name: str(result[name]) for name in required}
        coordinator = PromotionCoordinator(state_store=queue.state, coordinator_id="worker-stage")
        version = coordinator.stage(
            context_id, str(result.get("objective_bucket") or job.get("objective_bucket") or artifact.objective_bucket), guidance,
            objective_signature=str(result.get("objective_signature") or ""),
            guidance_version=artifact.artifact_id, metadata=metadata,
        )
        replay_manifest = result.get("replay_manifest") if isinstance(result.get("replay_manifest"), dict) else None
        queue.store.append_manifest(
            identifiers["training_manifest_id"], context_id, "optimization_training",
            [str(row.get("sample_id") or row.get("objective_id") or "") for row in result.get("objective_rows", []) if isinstance(row, dict)],
            {"objective_bucket": artifact.objective_bucket, "objective_signature": str(result.get("objective_signature") or "")},
        )
        if replay_manifest is not None:
            queue.store.append_manifest(
                identifiers["replay_manifest_id"], context_id, "paired_replay",
                [str(case.get("case_id") or "") for case in replay_manifest.get("cases", []) if isinstance(case, dict)], replay_manifest,
            )
        queue.store.append_run(identifiers["run_id"], context_id, "candidate", {
            "run_id": identifiers["run_id"], "candidate_id": identifiers["candidate_id"],
            "guidance_version": version, "objective_bucket": artifact.objective_bucket,
            "validation": result.get("validation", {}), "replay_manifest_id": identifiers["replay_manifest_id"],
            "replay_audit_id": identifiers["replay_audit_id"],
        })
        queue.store.append_candidate(identifiers["candidate_id"], context_id, artifact.objective_bucket, {
            "candidate_id": identifiers["candidate_id"], "run_id": identifiers["run_id"],
            "guidance_version": version, "guidance_artifact": artifact.to_mapping(),
            "guidance_metadata": metadata, "validation": result.get("validation", {}),
            "matrix_scores": result.get("matrix_scores", {}), "replay_manifest_id": identifiers["replay_manifest_id"],
            "replay_audit_id": identifiers["replay_audit_id"],
        }, run_id=identifiers["run_id"], guidance_version=version)
        queue.store.append_evaluation(identifiers["evaluation_id"], identifiers["candidate_id"], {
            "run_id": identifiers["run_id"], "validation": result.get("validation", {}),
            "matrix_scores": result.get("matrix_scores", {}), "replay_manifest_id": identifiers["replay_manifest_id"],
        })
        queue.store.append_replay_audit(
            identifiers["replay_audit_id"], identifiers["candidate_id"],
            result.get("replay_audit", {}) if isinstance(result.get("replay_audit"), dict) else {},
            manifest_id=identifiers["replay_manifest_id"],
        )
        # A failed deterministic gate is still a useful immutable candidate
        # record, but it must remain a rejected queue outcome rather than look
        # promotion-ready to a coordinator.
        rejected = str(result.get("status") or "") in {"rejected", "candidate_rejected"} or str(result.get("promotion_decision") or "") == "reject"
        result.update({
            "status": "rejected" if rejected else "candidate", "candidate_id": candidate_id,
            "promotion_decision": str(result.get("promotion_decision") or "candidate_staged"),
            "guidance_artifact": artifact.to_mapping(),
            "candidate_metadata": metadata,
        })
        return result, "rejected" if rejected else "candidate"
    if str(result.get("status")) in {"rejected", "candidate_rejected"}:
        return result, "rejected"
    if str(result.get("status")) == "error":
        return result, "failed"
    return result, "succeeded"


def worker_loop(plugin_dir: str, worker_id: str, max_iterations: int | None = None, *, once: bool = False) -> int:
    """Consume queued jobs; returns the number of claims made."""
    store = state_module.StateStore(plugin_dir)
    queue = LocalMultiprocessQueue(state_store=store)
    claims = 0
    iterations = 0
    while max_iterations is None or iterations < max_iterations:
        iterations += 1
        cfg = config_module.normalize_config(config_module.load_config(None))
        settings = _settings(cfg)
        queue.reclaim_expired()
        queue.heartbeat_worker(worker_id, ttl_seconds=settings["worker_ttl"])
        job = queue.claim(worker_id, settings["lease"], max_retries=settings["retries"])
        if not job:
            if once:
                break
            time.sleep(settings["poll"])
            continue
        claims += 1
        lease = job["lease"]
        try:
            result, terminal = _execute_job(queue, job, cfg, settings)
            if terminal == "lost_lease":
                continue
            if terminal == "failed":
                queue.fail(lease, str(result.get("error") or result.get("reason") or "worker failure"), max_retries=settings["retries"])
            elif terminal != "cancelled":
                queue.complete(lease, result, status=terminal)
                # The optimizer is a candidate generator in worker mode; reflect
                # its fenced terminal queue state rather than its legacy direct
                # promotion-oriented status in the context cache.
                store.set_context_state(str(job.get("context_id") or ""), {
                    "optimization_running": False,
                    "optimization_status": terminal,
                    "optimization_status_message": "candidate staged; coordinator promotion required" if terminal == "candidate" else str(result.get("reason") or terminal),
                    "optimization_result": result,
                })
        except BaseException as error:
            queue.fail(lease, error, max_retries=settings["retries"])
        finally:
            queue.heartbeat_worker(worker_id, ttl_seconds=settings["worker_ttl"])
        if once:
            break
    return claims
