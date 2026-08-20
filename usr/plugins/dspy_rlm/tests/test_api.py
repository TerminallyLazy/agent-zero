"""Task 10 API contract tests; all collaborators are local stubs."""
from __future__ import annotations

import sqlite3
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

# ``helpers.api`` imports helpers.network, whose optional HTTP client is absent
# in this development interpreter. These tests exercise handlers directly and
# never make a request, so provide only the import-time protocol surface.
if "requests" not in sys.modules:
    requests_stub = types.ModuleType("requests")
    requests_stub.RequestException = Exception
    requests_stub.Session = object
    sys.modules["requests"] = requests_stub

if "agent" not in sys.modules:
    agent_stub = types.ModuleType("agent")

    class AgentContext:  # pragma: no cover - direct handler tests replace lookup.
        @staticmethod
        def get(_context_id):
            return None

    agent_stub.AgentContext = AgentContext
    sys.modules["agent"] = agent_stub

from usr.plugins.dspy_rlm.api import candidates_list, status


def test_trace_summary_has_fixed_allowlisted_ui_rows() -> None:
    result = status.public_trace_summary(
        {
            "event_count": "12",
            "loop_count": 2,
            "tool_count": 9,
            "success_rate": "nan",
            "top_tools": [
                {"tool": "shell", "count": "4"},
                {"tool": "shell", "count": 2},
                {"tool": "secret_tool_name", "count": 99},
                {"tool": "search", "count": -2},
                "not-a-row",
            ],
            "latest_ts": "2026-08-19T00:00:00Z",
        }
    )

    assert result == {
        "event_count": 12,
        "loop_count": 2,
        "tool_count": 9,
        "success_rate": 0.0,
        "top_tools": [{"tool": "shell", "count": 6}],
        "latest_ts": "2026-08-19T00:00:00Z",
    }
    assert "latest_objective" not in result
    assert "latest_response" not in result


def test_scheduler_public_contract_calls_sqlite_workers_local_multiprocess() -> None:
    result = status.public_scheduler(
        {
            "mode": "distributed",
            "target_workers": 2,
            "running_workers": 1,
            "jobs": {"running": "1", "leak": 4},
            "samples": {"reasoning": "2", "other": 100},
        }
    )

    assert result["mode"] == "local_multiprocess"
    assert result["jobs"] == {"running": 1}
    assert result["samples"] == {"reasoning": 2}


def test_candidate_reader_missing_database_does_not_create_anything(tmp_path: Path) -> None:
    database = tmp_path / "new-state" / "runtime.sqlite"

    assert candidates_list._read_candidates(database, "ctx", None, 20) == []
    assert not database.exists()
    assert not database.parent.exists()


def test_candidate_reader_is_read_only_and_sanitizes_payload(tmp_path: Path) -> None:
    database = tmp_path / "runtime.sqlite"
    with sqlite3.connect(database) as conn:
        conn.execute(
            "CREATE TABLE candidates (candidate_id TEXT, context_id TEXT, objective_bucket TEXT, "
            "guidance_version TEXT, candidate_json TEXT, created_at REAL)"
        )
        conn.execute(
            "INSERT INTO candidates VALUES (?, ?, ?, ?, ?, ?)",
            (
                "candidate-1",
                "ctx-1",
                "reasoning",
                "guidance-1",
                '{"engine":"gepa","status":"candidate","promotion_decision":"review_only",'
                '"guidance":"must not leave the database"}',
                123.0,
            ),
        )

    before = database.stat().st_mtime_ns
    rows = candidates_list._read_candidates(database, "ctx-1", None, 20)
    after = database.stat().st_mtime_ns
    result = candidates_list._candidate_view({**dict(rows[0]), "candidate": __import__("json").loads(rows[0]["candidate_json"])})

    assert before == after
    assert result == {
        "candidate_id": "candidate-1",
        "guidance_version": "guidance-1",
        "objective_bucket": "reasoning",
        "created_at": 123.0,
        "engine": "gepa",
        "status": "candidate",
        "promotion_decision": "review_only",
    }


@pytest.mark.asyncio
async def test_candidates_endpoint_uses_read_only_reader_and_stable_response(monkeypatch: pytest.MonkeyPatch) -> None:
    context = SimpleNamespace(id="ctx-1")
    monkeypatch.setattr(candidates_list, "resolve_context_config", lambda _input: (context, {}, None))
    monkeypatch.setattr(candidates_list, "_read_candidates", lambda *_args: [])

    result = await candidates_list.CandidatesList(None, None).process({"context_id": "ctx-1"}, None)

    assert result == {"plugin": "dspy_rlm", "context_id": "ctx-1", "candidates": []}
