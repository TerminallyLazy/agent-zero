"""Task 7 contract coverage for the public local-multiprocess queue API."""
from __future__ import annotations

from typing import Callable

import pytest

from usr.plugins.dspy_rlm.helpers import queue as queue_module
from usr.plugins.dspy_rlm.helpers import store as store_module
from usr.plugins.dspy_rlm.helpers.queue import Lease, LocalMultiprocessQueue
from usr.plugins.dspy_rlm.helpers.state import StateStore


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Callable[[], float]:
    """Use one deterministic clock for Store leases and queue cancellation."""
    now = [100.0]
    monkeypatch.setattr(store_module, "_now", lambda: now[0])
    monkeypatch.setattr(queue_module.time, "time", lambda: now[0])

    def advance(seconds: float) -> float:
        now[0] += seconds
        return now[0]

    return advance


@pytest.fixture
def queue(tmp_path) -> LocalMultiprocessQueue:
    return LocalMultiprocessQueue(state_store=StateStore(tmp_path))


def test_enqueue_is_idempotent_and_force_never_replaces_a_live_lease(queue: LocalMultiprocessQueue) -> None:
    payload = {"job_key": "job-1", "objective_bucket": "reasoning", "input": "first"}

    assert queue.enqueue("ctx-1", payload) == ("job-1", True)
    assert queue.enqueue("ctx-1", {**payload, "input": "replacement"}) == ("job-1", False)
    assert queue.get("job-1")["payload"]["input"] == "first"

    lease = queue.claim("worker-a", 30)
    assert lease is not None
    assert queue.enqueue("ctx-1", {**payload, "input": "forced replacement"}, force=True) == ("job-1", False)
    assert queue.get("job-1")["payload"]["input"] == "first"


def test_only_one_worker_claims_and_only_the_current_owner_and_fence_can_renew_or_complete(
    queue: LocalMultiprocessQueue,
) -> None:
    assert queue.enqueue("ctx-1", {"job_key": "job-1"}) == ("job-1", True)

    claimed = queue.claim("worker-a", 30)
    assert claimed is not None
    lease = claimed["lease"]
    assert isinstance(lease, Lease)
    assert queue.claim("worker-b", 30) is None

    wrong_owner = Lease(lease.job_key, "worker-b", lease.fencing_token, lease.expires_at)
    wrong_fence = Lease(lease.job_key, lease.worker_id, lease.fencing_token + 1, lease.expires_at)
    assert not queue.heartbeat(wrong_owner, 30)
    assert not queue.heartbeat(wrong_fence, 30)
    assert queue.heartbeat(lease, 30)
    assert not queue.complete(wrong_owner, {"done": False})
    assert not queue.complete(wrong_fence, {"done": False})
    assert queue.complete(lease, {"done": True})
    assert queue.get("job-1")["status"] == "succeeded"


def test_expired_lease_is_reclaimed_and_cannot_complete_after_a_new_claim(
    queue: LocalMultiprocessQueue, clock: Callable[[], float]
) -> None:
    assert queue.enqueue("ctx-1", {"job_key": "job-1", "max_retries": 3}) == ("job-1", True)
    first = queue.claim("worker-a", 5)
    assert first is not None

    clock(6)
    assert queue.reclaim_expired() == 1
    assert queue.get("job-1")["status"] == "pending"
    second = queue.claim("worker-b", 5)
    assert second is not None
    assert second["lease"].fencing_token == first["lease"].fencing_token + 1
    assert not queue.complete(first["lease"], {"stale": True})
    assert queue.complete(second["lease"], {"done": True})


def test_cancel_rejects_a_wrong_lease_and_invalidates_the_current_lease(queue: LocalMultiprocessQueue) -> None:
    assert queue.enqueue("ctx-1", {"job_key": "job-1"}) == ("job-1", True)
    claimed = queue.claim("worker-a", 30)
    assert claimed is not None
    lease = claimed["lease"]

    assert not queue.cancel("job-1", lease=Lease("job-1", "worker-b", lease.fencing_token, lease.expires_at))
    assert queue.cancel("job-1", reason="operator stop")
    assert queue.is_cancelled("job-1")
    assert queue.get("job-1")["status"] == "cancelled"
    assert not queue.complete(lease, {"late": True})
    assert not queue.cancel("job-1")
