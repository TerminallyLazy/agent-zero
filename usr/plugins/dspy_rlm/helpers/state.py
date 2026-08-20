"""Compatibility state facade backed by :mod:`store`.

SQLite is authoritative.  ``runtime_state.json`` remains an atomically-written
read cache for existing UI/diagnostic consumers; failures to write that cache do
not affect durable state.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from datetime import datetime, timezone
from hashlib import sha1
from pathlib import Path
from typing import Any, Mapping

from .paths import COMPILED_STATE_FILE, STATE_FILE, STORE_FILE
from .store import Store

DB_FILE = "dspy_rlm_runtime.sqlite"
_LOCK = threading.RLock()
_RUNTIME_LOCK = threading.RLock()

_DEFAULT_CONTEXT_STATE: dict[str, Any] = {
    "optimization_running": False, "optimization_status": "idle",
    "optimization_count": 0, "attempts_total": 0,
    "attempts_since_optimization": 0, "last_optimization_at": "",
    "last_optimization_error": "", "last_guidance": "",
    "last_guidance_at": "", "last_guidance_version": "",
    "last_objective": "", "last_objective_bucket": "",
    "last_response_preview": "", "last_loop_iteration": -1,
    "tool_histogram": {}, "recent_tools": [], "last_updated_at": "",
    "optimization_result": {},
}


def _short_id(seed: str) -> str:
    return sha1(seed.encode("utf-8")).hexdigest()[:24]


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _atomic_json_write(path: Path, payload: Mapping[str, Any]) -> None:
    """Best-effort cache write; never make JSON a persistence dependency."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass


class StateStore:
    """Legacy-compatible state API using a migration-managed :class:`Store`."""

    def __init__(self, plugin_dir: str | Path, db_path: str | Path | None = None):
        root = Path(plugin_dir).resolve()
        self.plugin_dir = root
        self.state_dir = root / "state"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        # db_path remains a direct database override for temporary-path callers.
        self.db_path = Path(db_path) if db_path is not None else self.state_dir / DB_FILE
        self.runtime_state_file = self.state_dir / "runtime_state.json"
        self.store = Store(self.db_path)

    def _write_runtime_cache(self) -> None:
        """Write a derived cache only. Readers must tolerate its absence/staleness."""
        try:
            with self.store._connect() as conn:  # narrow read-only cache projection
                rows = conn.execute("SELECT context_id,state_json FROM runtime_context_state").fetchall()
            contexts: dict[str, Any] = {}
            for row in rows:
                try:
                    value = json.loads(row["state_json"])
                except (TypeError, ValueError):
                    continue
                if isinstance(value, dict):
                    contexts[str(row["context_id"])] = value
            _atomic_json_write(self.runtime_state_file, {"contexts": contexts, "updated_at": time.time()})
        except Exception:
            pass

    def load_context_state(self, context_id: str) -> dict[str, Any]:
        if not context_id:
            return dict(_DEFAULT_CONTEXT_STATE)
        state, _revision = self.store.get_context_state(str(context_id))
        merged = dict(_DEFAULT_CONTEXT_STATE)
        if isinstance(state, dict):
            merged.update(state)
        return merged

    def set_context_state(self, context_id: str, updates: Mapping[str, Any]) -> dict[str, Any]:
        if not context_id or not isinstance(updates, Mapping):
            return self.load_context_state(context_id)
        with _RUNTIME_LOCK:
            current, revision = self.store.get_context_state(str(context_id))
            merged = dict(_DEFAULT_CONTEXT_STATE)
            if isinstance(current, dict):
                merged.update(current)
            merged.update(dict(updates))
            merged["last_updated_at"] = _utc_now()
            # Retry once on an external process writing this context concurrently.
            applied, _ = self.store.put_context_state(str(context_id), merged, expected_revision=revision)
            if not applied:
                current, revision = self.store.get_context_state(str(context_id))
                merged = dict(_DEFAULT_CONTEXT_STATE)
                if isinstance(current, dict):
                    merged.update(current)
                merged.update(dict(updates)); merged["last_updated_at"] = _utc_now()
                self.store.put_context_state(str(context_id), merged, expected_revision=revision)
            self._write_runtime_cache()
        return merged

    # Objective samples are immutable. Historical pruning is intentionally a no-op.
    def add_objective_sample(self, sample: Mapping[str, Any], *, sample_id: str | None = None) -> str:
        payload = dict(sample)
        context_id = str(payload.get("context_id") or "")
        if not context_id:
            raise ValueError("context_id is required for sample persistence")
        created = float(payload.get("created_at") or time.time())
        window = payload.get("trace_window") if isinstance(payload.get("trace_window"), dict) else {}
        sid = str(sample_id or payload.get("sample_id") or _short_id("|".join((context_id, str(payload.get("objective_id") or ""), str(payload.get("objective_signature") or ""), str(window.get("start_ts", created)), str(window.get("end_ts", created))))))
        payload["sample_id"] = sid
        # The old API intentionally excluded raw tool events from its durable record.
        payload.pop("tool_events", None)
        self.store.append_sample(sid, payload, created_at=created)
        return sid

    def get_objective_sample(self, sample_id: str) -> dict[str, Any] | None:
        return self.store.get_sample(sample_id)

    def latest_objective_samples(self, context_id: str, bucket: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        return self.store.list_samples(context_id, bucket, limit)

    def sample_count(self, context_id: str, bucket: str | None = None) -> int:
        return self.store.count_samples(context_id, bucket)

    def prune_samples(self, context_id: str, max_rows: int) -> int:
        # Immutable evidence/sample retention is managed by a future TTL policy.
        return 0

    # Compatibility jobs ----------------------------------------------------
    def enqueue_job(self, context_id: str, payload: Mapping[str, Any], *, force: bool = False) -> tuple[str, bool]:
        body = dict(payload or {})
        key = str(body.get("job_key") or _short_id("|".join((str(context_id), str(body.get("objective_bucket") or "reasoning"), str(body.get("objective_signature") or ""), str(body.get("trace_version") or "baseline")))))
        body["job_key"] = key
        return self.store.enqueue_job(key, str(context_id), body, max_retries=_as_int(body.get("max_retries"), 2), force=force)

    @staticmethod
    def _job_view(job: Mapping[str, Any] | None) -> dict[str, Any] | None:
        if not job:
            return None
        result = dict(job)
        payload = result.get("payload") if isinstance(result.get("payload"), dict) else {}
        result.update({
            "job_key": str(result.get("job_key") or ""),
            "context_id": str(result.get("context_id") or ""),
            "objective_id": str(payload.get("objective_id") or ""),
            "objective_bucket": str(payload.get("objective_bucket") or "reasoning"),
            "objective_signature": str(payload.get("objective_signature") or ""),
            "trace_version": str(payload.get("trace_version") or "baseline"),
            "payload": payload,
        })
        return result

    def claim_next_job(self, worker_id: str, lease_ttl_seconds: int, *, context_id: str | None = None, enforce_single_tenant_per_context: bool = False, max_retries: int | None = None) -> dict[str, Any] | None:
        # The legacy single-context flag is enforced before claim so a worker cannot
        # hold two active jobs for the same context.
        if enforce_single_tenant_per_context and context_id:
            with self.store._connect() as conn:
                row = conn.execute("SELECT 1 FROM jobs j JOIN job_leases l ON l.job_key=j.job_key WHERE j.context_id=? AND j.status='running' AND l.expires_at>? LIMIT 1", (str(context_id), time.time())).fetchone()
            if row:
                return None
        return self._job_view(self.store.claim_job(worker_id, lease_ttl_seconds, context_id=context_id, max_retries=max_retries))

    def set_job_running(self, job_key: str, worker_id: str, lease_ttl_seconds: int) -> bool:
        # Existing callers only use this after enqueue; claim is the safe transition.
        with self.store._connect() as conn:
            row = conn.execute("SELECT context_id FROM jobs WHERE job_key=?", (str(job_key),)).fetchone()
        if not row:
            return False
        claim = self.store.claim_job(worker_id, lease_ttl_seconds, context_id=str(row["context_id"]))
        return bool(claim and claim.get("job_key") == job_key)

    def _set_job_status(self, job_key: str, status: str, *, worker_id: str | None = None, lease_ttl_seconds: int | None = None, result: Mapping[str, Any] | None = None, error: str | None = None) -> bool:
        # Retained for module callers. Unfenced legacy transitions are allowed only
        # for terminal state compatibility; workers should use Store.complete_job.
        terminal = str(status) in {"succeeded", "failed", "pending", "rejected", "candidate", "promoted"}
        if not terminal:
            return self.set_job_running(str(job_key), str(worker_id or "legacy"), int(lease_ttl_seconds or 1))
        return self.store.complete_job(str(job_key), None, None, result, status=str(status), error=error)

    def mark_job_done(self, job_key: str, summary: Mapping[str, Any]) -> None:
        self.store.complete_job(str(job_key), None, None, summary)

    def fail_job(self, job_key: str, error: str, *, max_retries: int) -> None:
        with self.store._connect() as conn:
            row = conn.execute("SELECT attempts FROM jobs WHERE job_key=?", (str(job_key),)).fetchone()
        if not row:
            return
        status = "pending" if int(row["attempts"]) < int(max_retries) else "failed"
        self.store.complete_job(str(job_key), None, None, None, status=status, error=str(error))

    def reclaim_stale_jobs(self, lease_ttl_seconds: int) -> int:
        # Expiry is already recorded at claim/heartbeat time; no double TTL offset.
        return self.store.reclaim_expired_jobs()

    def _raw_job(self, job_key: str) -> dict[str, Any] | None:
        with self.store._connect() as conn:
            row = conn.execute("""SELECT j.*,l.owner_id AS lease_owner,l.expires_at AS lease_expires_at,l.fencing_token
                FROM jobs j LEFT JOIN job_leases l ON l.job_key=j.job_key WHERE j.job_key=?""", (str(job_key),)).fetchone()
        if not row:
            return None
        raw = dict(row)
        raw["payload"] = json.loads(raw.pop("payload_json"))
        raw["result"] = json.loads(raw.pop("result_json")) if raw.get("result_json") else None
        return raw

    def get_job(self, job_key: str) -> dict[str, Any] | None:
        return self._job_view(self._raw_job(job_key))

    def recent_jobs(self, context_id: str | None = None, limit: int = 25) -> list[dict[str, Any]]:
        sql, args = "SELECT job_key FROM jobs", []
        if context_id:
            sql += " WHERE context_id=?"; args.append(str(context_id))
        sql += " ORDER BY updated_at DESC LIMIT ?"; args.append(max(0, int(limit)))
        with self.store._connect() as conn:
            keys = [str(row["job_key"]) for row in conn.execute(sql, args).fetchall()]
        return [job for key in keys if (job := self.get_job(key)) is not None]

    get_recent_jobs = recent_jobs

    # Guidance compatibility -----------------------------------------------
    def set_active_guidance(self, context_id: str, objective_bucket: str, objective_signature: str, guidance_text: str, guidance_version: str, metadata: Mapping[str, Any] | None = None) -> None:
        """Compatibility staging shim; it never changes the active pointer.

        Active guidance has a single writer: :class:`PromotionCoordinator`, which
        supplies a coordinator identity and an observed-revision CAS.  Historical
        callers of this facade still retain their immutable guidance artifact,
        but must explicitly use that coordinator to promote it.
        """
        self.store.append_guidance_version(guidance_version, context_id, objective_bucket, objective_signature, guidance_text, metadata)

    def get_active_guidance(self, context_id: str, objective_bucket: str) -> dict[str, Any] | None:
        return self.store.get_active_guidance(context_id, objective_bucket)

    def get_context_samples_distribution(self, context_id: str) -> dict[str, int]:
        with self.store._connect() as conn:
            rows = conn.execute("SELECT objective_bucket,COUNT(*) AS count FROM samples WHERE context_id=? GROUP BY objective_bucket", (str(context_id),)).fetchall()
        return {str(row["objective_bucket"]): int(row["count"]) for row in rows}

    def most_recent_payload(self, context_id: str) -> dict[str, Any]:
        rows = self.latest_objective_samples(context_id, limit=1)
        return rows[0] if rows else {}

    def purge_context(self, context_id: str) -> int:
        # Append-only records are intentionally never silently purged.
        return 0

    def aggregate_metrics(self, context_id: str) -> dict[str, Any]:
        rows = self.latest_objective_samples(context_id, limit=1000000)
        counts: dict[str, int] = {}; confidence: dict[str, list[float]] = {}
        for sample in rows:
            bucket = str(sample.get("objective_bucket") or "reasoning")
            counts[bucket] = counts.get(bucket, 0) + 1
            confidence.setdefault(bucket, []).append(float(sample.get("objective_confidence", 1.0) or 0.0))
        return {"counts": counts, "confidence": {key: sum(values) / len(values) for key, values in confidence.items() if values}}

    def runtime_status(self) -> dict[str, Any]:
        with self.store._connect() as conn:
            jobs = {str(r["status"]): int(r["count"]) for r in conn.execute("SELECT status,COUNT(*) AS count FROM jobs GROUP BY status")}
            samples = {str(r["objective_bucket"]): int(r["count"]) for r in conn.execute("SELECT objective_bucket,COUNT(*) AS count FROM samples GROUP BY objective_bucket")}
            guidance = int(conn.execute("SELECT COUNT(*) FROM guidance_versions").fetchone()[0])
            contexts = int(conn.execute("SELECT COUNT(*) FROM runtime_context_state").fetchone()[0])
        return {"jobs": jobs, "samples": samples, "guidance_rows": guidance, "sample_rows": sum(samples.values()), "context_states": contexts}

    # Legacy convenience state transitions ---------------------------------
    def record_loop_attempt(self, context_id: str, objective: str, response_preview: str, iteration: int, objective_bucket: str | None = None) -> dict[str, Any]:
        state = self.load_context_state(context_id)
        state.update({"attempts_total": _as_int(state.get("attempts_total")) + 1, "attempts_since_optimization": _as_int(state.get("attempts_since_optimization")) + 1, "last_loop_iteration": _as_int(iteration, -1), "last_objective": str(objective or "")[:400], "last_response_preview": str(response_preview or "")[:600], "optimization_status_message": "collecting"})
        if objective_bucket: state["last_objective_bucket"] = str(objective_bucket)
        return self.set_context_state(context_id, state)

    def record_tool_result(self, context_id: str, tool_name: str, success: bool, response_preview: str) -> dict[str, Any]:
        state = self.load_context_state(context_id); histogram = dict(state.get("tool_histogram") or {}); tool = str(tool_name or "unknown")
        histogram[tool] = _as_int(histogram.get(tool)) + 1
        state.update({"success_events": _as_int(state.get("success_events")) + int(bool(success)), "failure_events": _as_int(state.get("failure_events")) + int(not success), "tool_histogram": histogram, "recent_tools": [tool, *[str(item) for item in state.get("recent_tools", []) if str(item) != tool]][:6]})
        if response_preview: state["last_response_preview"] = str(response_preview)
        return self.set_context_state(context_id, state)

    def should_auto_optimize(self, context_id: str, interval_messages: int, cooldown_hours: int = 0) -> bool:
        state = self.load_context_state(context_id)
        if state.get("optimization_running") or (_as_int(interval_messages) > 0 and _as_int(state.get("attempts_since_optimization")) < _as_int(interval_messages)):
            return False
        if cooldown_hours and state.get("last_optimization_at"):
            try:
                return (datetime.now(timezone.utc) - datetime.fromisoformat(str(state["last_optimization_at"]).replace("Z", "+00:00"))).total_seconds() >= int(cooldown_hours) * 3600
            except (TypeError, ValueError): pass
        return True

    def mark_optimization_started(self, context_id: str, trigger: str) -> dict[str, Any]:
        state = self.load_context_state(context_id); state.update({"optimization_running": True, "optimization_status": "running", "optimization_status_message": f"started:{trigger}", "optimization_requested_by": str(trigger), "optimization_count": _as_int(state.get("optimization_count")) + 1, "optimization_start_ts": _utc_now()})
        return self.set_context_state(context_id, state)

    def mark_optimization_complete(self, context_id: str, result: Mapping[str, Any]) -> dict[str, Any]:
        status = str(result.get("status") or "unknown"); state = self.load_context_state(context_id)
        state.update({"optimization_running": False, "optimization_status": status, "optimization_status_message": str(result.get("reason") or status), "optimization_result": dict(result)})
        if status == "success": state.update({"last_optimization_at": _utc_now(), "attempts_since_optimization": 0, "last_optimization_error": ""})
        else: state["last_optimization_error"] = str(result.get("error") or "")
        if isinstance(result.get("guidance"), str) and result["guidance"]: state.update({"last_guidance": result["guidance"], "last_guidance_at": _utc_now(), "last_guidance_version": str(result.get("guidance_version") or "")})
        return self.set_context_state(context_id, state)


def _store_for_root(plugin_root: str | Path | None = None) -> StateStore:
    return StateStore(Path(plugin_root) if plugin_root else Path(__file__).resolve().parents[1])

# Module-level compatibility wrappers used by extensions and API handlers.
def load_context_state(context_id: str) -> dict[str, Any]: return _store_for_root().load_context_state(context_id)
def record_loop_attempt(context_id: str, objective: str, response_preview: str, iteration: int, objective_bucket: str | None = None) -> dict[str, Any]: return _store_for_root().record_loop_attempt(context_id, objective, response_preview, iteration, objective_bucket)
def record_tool_result(context_id: str, tool_name: str, success: bool, response_preview: str) -> dict[str, Any]: return _store_for_root().record_tool_result(context_id, tool_name, success, response_preview)
def should_auto_optimize(context_id: str, interval_messages: int, cooldown_hours: int = 0) -> bool: return _store_for_root().should_auto_optimize(context_id, interval_messages, cooldown_hours)
def mark_optimization_started(context_id: str, trigger: str) -> dict[str, Any]: return _store_for_root().mark_optimization_started(context_id, trigger)
def mark_optimization_complete(context_id: str, result: Mapping[str, Any]) -> dict[str, Any]: return _store_for_root().mark_optimization_complete(context_id, result)
def get_runtime_status() -> dict[str, Any]: return _store_for_root().runtime_status()
def claim_next_job(worker_id: str, lease_ttl_seconds: int, *, context_id: str | None = None, enforce_single_tenant_per_context: bool = False, max_retries: int | None = None) -> dict[str, Any] | None: return _store_for_root().claim_next_job(worker_id, lease_ttl_seconds, context_id=context_id, enforce_single_tenant_per_context=enforce_single_tenant_per_context, max_retries=max_retries)
def set_job_status(job_key: str, status: str, *, worker_id: str | None = None, lease_ttl_seconds: int | None = None, result: Mapping[str, Any] | None = None, error: str | None = None) -> bool: return _store_for_root()._set_job_status(job_key, status, worker_id=worker_id, lease_ttl_seconds=lease_ttl_seconds, result=result, error=error)
def latest_objective_samples(context_id: str, bucket: str | None = None, limit: int = 20) -> list[dict[str, Any]]: return _store_for_root().latest_objective_samples(context_id, bucket=bucket, limit=limit)
def sample_count(context_id: str, bucket: str | None = None) -> int: return _store_for_root().sample_count(context_id, bucket)
def aggregate_metrics(context_id: str) -> dict[str, Any]: return _store_for_root().aggregate_metrics(context_id)
def set_active_guidance(context_id: str, objective_bucket: str, objective_signature: str, guidance_text: str, guidance_version: str, metadata: Mapping[str, Any] | None = None) -> None: _store_for_root().set_active_guidance(context_id, objective_bucket, objective_signature, guidance_text, guidance_version, metadata)
def add_objective_sample(sample: Mapping[str, Any], sample_id: str | None = None) -> str: return _store_for_root().add_objective_sample(sample, sample_id=sample_id)
def get_recent_jobs(context_id: str | None = None, limit: int = 25) -> list[dict[str, Any]]: return _store_for_root().recent_jobs(context_id=context_id, limit=limit)
def get_job(job_key: str) -> dict[str, Any] | None: return _store_for_root().get_job(job_key)
def enqueue_job(context_id: str, payload: Mapping[str, Any], force: bool = False) -> tuple[str, bool]: return _store_for_root().enqueue_job(context_id, payload, force=force)
def set_job_running(job_key: str, worker_id: str, lease_ttl_seconds: int) -> bool: return _store_for_root().set_job_running(job_key, worker_id, lease_ttl_seconds)
def mark_job_done(job_key: str, summary: Mapping[str, Any]) -> None: _store_for_root().mark_job_done(job_key, summary)
def fail_job(job_key: str, error: str, max_retries: int) -> None: _store_for_root().fail_job(job_key, error, max_retries=max_retries)
