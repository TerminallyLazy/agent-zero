"""Local SQLite queue protocol for explicit DSPy RLM worker processes.

This module deliberately contains no process management.  It adapts the durable
``Store`` job/lease primitives into fenced worker operations so many processes on
one machine can safely consume a local SQLite queue.
"""
from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any, Mapping

from . import state as state_module


TERMINAL_STATUSES = frozenset({"succeeded", "failed", "cancelled", "candidate", "promoted", "rejected"})
TRANSIENT_ERROR_NAMES = frozenset({"TimeoutError", "ConnectionError", "OSError", "OperationalError"})


@dataclass(frozen=True)
class Lease:
    """A worker's unforgeable-in-practice database lease identity."""

    job_key: str
    worker_id: str
    fencing_token: int
    expires_at: float

    @classmethod
    def from_job(cls, job: Mapping[str, Any]) -> "Lease":
        return cls(
            job_key=str(job.get("job_key") or ""),
            worker_id=str(job.get("lease_owner") or job.get("worker_id") or ""),
            fencing_token=int(job.get("fencing_token") or 0),
            expires_at=float(job.get("lease_expires_at") or 0),
        )


@dataclass(frozen=True)
class FailureClassification:
    transient: bool
    reason: str


def classify_failure(error: BaseException | str | None) -> FailureClassification:
    """Classify only transport/runtime failures as retryable.

    Optimizer validation failures are normal candidate outcomes, not retries.
    Unknown exceptions fail closed as terminal so a programming error cannot spin
    indefinitely across explicit worker processes.
    """
    if isinstance(error, BaseException):
        if isinstance(error, (TimeoutError, ConnectionError, OSError)):
            return FailureClassification(True, error.__class__.__name__)
        return FailureClassification(error.__class__.__name__ in TRANSIENT_ERROR_NAMES, error.__class__.__name__)
    text = str(error or "").strip().lower()
    transient = any(token in text for token in ("timeout", "temporar", "connection", "database is locked", "busy"))
    return FailureClassification(transient, "transient_error" if transient else "terminal_error")


class LocalMultiprocessQueue:
    """Fenced queue operations over a plugin-local :class:`StateStore`.

    ``worker_id`` and ``fencing_token`` are mandatory for every mutating worker
    operation.  An expired/reclaimed worker can therefore never finish or renew a
    job later claimed by another worker.
    """

    mode = "local_multiprocess"

    def __init__(self, plugin_dir: str | None = None, *, state_store: state_module.StateStore | None = None):
        self.state = state_store or state_module.StateStore(plugin_dir or __file__.rsplit("/helpers/", 1)[0])
        self.store = self.state.store

    def enqueue(self, context_id: str, payload: Mapping[str, Any], *, force: bool = False) -> tuple[str, bool]:
        if not str(context_id or "").strip():
            raise ValueError("context_id is required")
        return self.state.enqueue_job(str(context_id), dict(payload or {}), force=force)

    def claim(
        self,
        worker_id: str,
        lease_ttl_seconds: int,
        *,
        context_id: str | None = None,
        max_retries: int | None = None,
    ) -> dict[str, Any] | None:
        if not str(worker_id or "").strip():
            raise ValueError("worker_id is required")
        job = self.state.claim_next_job(
            str(worker_id), max(1, int(lease_ttl_seconds)), context_id=context_id, max_retries=max_retries
        )
        if job:
            job["lease"] = Lease.from_job(job)
        return job

    # Descriptive aliases keep call sites clear without exposing Store directly.
    claim_next = claim
    acquire_lease = claim

    @staticmethod
    def _lease(job_or_lease: Mapping[str, Any] | Lease) -> Lease:
        return job_or_lease if isinstance(job_or_lease, Lease) else Lease.from_job(job_or_lease)

    def heartbeat(self, job_or_lease: Mapping[str, Any] | Lease, lease_ttl_seconds: int) -> bool:
        lease = self._lease(job_or_lease)
        if not lease.job_key or not lease.worker_id or lease.fencing_token <= 0:
            return False
        return self.store.heartbeat_job(lease.job_key, lease.worker_id, lease.fencing_token, max(1, int(lease_ttl_seconds)))

    renew = heartbeat

    def heartbeat_worker(self, worker_id: str, *, ttl_seconds: int, current_job: str = "") -> None:
        self.store.heartbeat_worker(
            str(worker_id),
            {"mode": self.mode, "current_job": str(current_job or ""), "pid": __import__("os").getpid()},
            ttl_seconds=max(1, int(ttl_seconds)),
        )

    def complete(self, job_or_lease: Mapping[str, Any] | Lease, result: Mapping[str, Any], *, status: str = "succeeded") -> bool:
        lease = self._lease(job_or_lease)
        if status not in TERMINAL_STATUSES:
            raise ValueError(f"invalid terminal job status: {status}")
        return self.store.complete_job(lease.job_key, lease.worker_id, lease.fencing_token, dict(result), status=status)

    def fail(self, job_or_lease: Mapping[str, Any] | Lease, error: BaseException | str, *, max_retries: int) -> tuple[bool, str]:
        """Finish a fenced attempt, requeuing only explicitly transient failures."""
        lease = self._lease(job_or_lease)
        job = self.state.get_job(lease.job_key) or {}
        classification = classify_failure(error)
        attempts = int(job.get("attempts") or 0)
        retry = classification.transient and attempts < max(0, int(max_retries))
        status = "pending" if retry else "failed"
        message = str(error)[:2000]
        applied = self.store.complete_job(
            lease.job_key, lease.worker_id, lease.fencing_token, None, status=status, error=message
        )
        return applied, status

    def cancel(self, job_key: str, *, reason: str = "cancelled", lease: Mapping[str, Any] | Lease | None = None) -> bool:
        """Cancel pending or running work transactionally.

        A caller holding a lease must present its owner and fencing token.  An
        operator cancellation has no lease and invalidates any running worker by
        deleting its lease; that worker's later fenced completion is rejected.
        """
        key = str(job_key or "")
        if not key:
            return False
        now = time.time()
        supplied = self._lease(lease) if lease is not None else None
        with self.store._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT status FROM jobs WHERE job_key=?", (key,)).fetchone()
            if not row or str(row["status"]) in TERMINAL_STATUSES:
                conn.execute("ROLLBACK")
                return False
            if supplied is not None:
                owned = conn.execute(
                    "SELECT 1 FROM job_leases WHERE job_key=? AND owner_id=? AND fencing_token=? AND expires_at>?",
                    (key, supplied.worker_id, supplied.fencing_token, now),
                ).fetchone()
                if not owned:
                    conn.execute("ROLLBACK")
                    return False
            cursor = conn.execute(
                "UPDATE jobs SET status='cancelled',last_error=?,updated_at=? WHERE job_key=?",
                (str(reason)[:2000], now, key),
            )
            conn.execute("DELETE FROM job_leases WHERE job_key=?", (key,))
            conn.execute("COMMIT")
        return bool(cursor.rowcount)

    def reclaim_expired(self) -> int:
        return self.store.reclaim_expired_jobs()

    reclaim = reclaim_expired

    def is_cancelled(self, job_key: str) -> bool:
        job = self.state.get_job(str(job_key))
        return bool(job and str(job.get("status")) == "cancelled")

    def get(self, job_key: str) -> dict[str, Any] | None:
        return self.state.get_job(str(job_key))

    def active_workers(self) -> list[dict[str, Any]]:
        return self.store.active_workers()

    def remove_workers(self, worker_ids: list[str]) -> int:
        return self.store.remove_workers(worker_ids)

    def status(self) -> dict[str, Any]:
        runtime = self.state.runtime_status()
        workers = self.active_workers()
        return {**runtime, "mode": self.mode, "active_workers": workers, "running_workers": len(workers)}


# Short aliases and functional adapters support bounded plugin integrations.
Queue = LocalMultiprocessQueue
JobQueue = LocalMultiprocessQueue


def enqueue_job(plugin_dir: str, context_id: str, payload: Mapping[str, Any], *, force: bool = False) -> tuple[str, bool]:
    return LocalMultiprocessQueue(plugin_dir).enqueue(context_id, payload, force=force)


def acquire_lease(plugin_dir: str, worker_id: str, lease_ttl_seconds: int, *, max_retries: int | None = None) -> dict[str, Any] | None:
    return LocalMultiprocessQueue(plugin_dir).claim(worker_id, lease_ttl_seconds, max_retries=max_retries)


def report_result(plugin_dir: str, lease: Mapping[str, Any] | Lease, result: Mapping[str, Any], *, status: str = "succeeded") -> bool:
    return LocalMultiprocessQueue(plugin_dir).complete(lease, result, status=status)


def cancel_job(plugin_dir: str, job_key: str, *, reason: str = "cancelled") -> bool:
    return LocalMultiprocessQueue(plugin_dir).cancel(job_key, reason=reason)
