"""Public-contract coverage for Task 3's durable SQLite repositories."""
from __future__ import annotations

import sqlite3

import pytest

from usr.plugins.dspy_rlm.helpers.store import Store
import usr.plugins.dspy_rlm.helpers.store as store_module


def _store(tmp_path) -> Store:
    return Store(tmp_path / "dspy-rlm.sqlite3")


def _status(store: Store, job_key: str) -> str:
    with store._connect() as conn:  # The public repository deliberately has no job-read API.
        return str(conn.execute("SELECT status FROM jobs WHERE job_key=?", (job_key,)).fetchone()[0])


def test_migrate_imports_legacy_rows_once_and_exposes_current_schema(tmp_path):
    db = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(db) as conn:
        conn.executescript(
            """
            CREATE TABLE objective_samples (
              sample_id TEXT PRIMARY KEY, objective_payload TEXT, created_at REAL
            );
            CREATE TABLE optimization_jobs (
              job_key TEXT PRIMARY KEY, context_id TEXT, status TEXT, attempts INTEGER,
              max_retries INTEGER, payload_json TEXT, result_json TEXT, last_error TEXT,
              created_at REAL, updated_at REAL
            );
            CREATE TABLE guidance_versions (
              context_id TEXT, objective_bucket TEXT, objective_signature TEXT,
              guidance_version TEXT PRIMARY KEY, guidance_text TEXT, metadata_json TEXT,
              created_at REAL
            );
            INSERT INTO objective_samples VALUES ('sample-1', '{"context_id":"ctx","objective_bucket":"reasoning"}', 11);
            INSERT INTO optimization_jobs VALUES ('job-1','ctx','pending',0,2,'{"work":1}',NULL,NULL,12,12);
            INSERT INTO guidance_versions VALUES ('ctx','reasoning','sig','guide-1','be concise','{"source":"legacy"}',13);
            """
        )

    store = Store(db)
    assert store.schema_version == 2
    assert store.get_sample("sample-1") == {"context_id": "ctx", "objective_bucket": "reasoning"}
    assert store.get_active_guidance("ctx", "reasoning")["guidance_version"] == "guide-1"

    # A second open must not re-import and advance the migrated active revision.
    assert Store(db).get_active_guidance("ctx", "reasoning")["revision"] == 1
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == 2
        assert conn.execute("SELECT COUNT(*) FROM jobs WHERE job_key='job-1'").fetchone()[0] == 1


def test_append_only_artifacts_preserve_first_payload(tmp_path):
    store = _store(tmp_path)

    assert store.append_sample("sample", {"context_id": "ctx", "objective_bucket": "a", "value": "first"}) == "sample"
    store.append_sample("sample", {"context_id": "other", "objective_bucket": "b", "value": "replacement"})
    assert store.get_sample("sample") == {"context_id": "ctx", "objective_bucket": "a", "value": "first"}

    store.append_guidance_version("guide", "ctx", "a", "sig", "first", {"rank": 1})
    store.append_guidance_version("guide", "ctx", "a", "other", "replacement", {"rank": 2})
    version = store.get_guidance_version("guide")
    assert version["guidance_text"] == "first"
    assert version["metadata"] == {"rank": 1}

    store.append_evidence("event", "ctx", "tool", {"safe": "first"}, created_at=1)
    store.append_evidence("event", "ctx", "turn", {"safe": "replacement"}, created_at=2)
    with store._connect() as conn:
        row = conn.execute("SELECT context_id,event_type,event_json FROM evidence_events WHERE event_id='event'").fetchone()
    assert tuple(row) == ("ctx", "tool", '{"safe":"first"}')


def test_active_guidance_cas_rejects_stale_writes_and_rolls_back(tmp_path):
    store = _store(tmp_path)
    store.append_guidance_version("v1", "ctx", "reasoning", "sig", "first")
    store.append_guidance_version("v2", "ctx", "reasoning", "sig", "second")

    assert store.compare_and_swap_active_guidance("ctx", "reasoning", "v1", expected_revision=0, actor_id="worker") == (True, 1)
    assert store.compare_and_swap_active_guidance("ctx", "reasoning", "v2", expected_revision=0) == (False, 1)
    assert store.compare_and_swap_active_guidance("ctx", "reasoning", "v2", expected_revision=1) == (True, 2)
    assert store.rollback_active_guidance("ctx", "reasoning", "v1", expected_revision=2, detail={"why": "regression"}) == (True, 3)
    assert store.get_active_guidance("ctx", "reasoning")["guidance_version"] == "v1"

    with store._connect() as conn:
        actions = [row[0] for row in conn.execute("SELECT action FROM promotion_audits ORDER BY created_at")]
    assert actions == ["promote", "promote", "rollback"]
    with pytest.raises(ValueError, match="does not belong"):
        store.compare_and_swap_active_guidance("other", "reasoning", "v1", expected_revision=0)


def test_jobs_use_leases_fencing_reclaim_and_worker_heartbeats(tmp_path, monkeypatch):
    now = [100.0]
    monkeypatch.setattr(store_module, "_now", lambda: now[0])
    store = _store(tmp_path)

    assert store.enqueue_job("job", "ctx", {"work": 1}, max_retries=2) == ("job", True)
    first = store.claim_job("worker-a", 5)
    assert first["fencing_token"] == 1
    assert first["payload"] == {"work": 1}
    assert not store.heartbeat_job("job", "worker-a", 99, 5)
    assert store.heartbeat_job("job", "worker-a", 1, 5)

    now[0] = 106.0
    assert store.reclaim_expired_jobs() == 1
    assert _status(store, "job") == "pending"
    second = store.claim_job("worker-b", 5)
    assert second["fencing_token"] == 2
    assert not store.complete_job("job", "worker-a", 1, {"stale": True})
    assert store.complete_job("job", "worker-b", 2, {"done": True})
    assert _status(store, "job") == "succeeded"

    store.heartbeat_worker("worker-b", {"queues": 1}, ttl_seconds=5)
    assert store.active_workers()[0]["heartbeat"] == {"queues": 1}
    now[0] = 112.0
    assert store.active_workers() == []
