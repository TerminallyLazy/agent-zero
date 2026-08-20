"""List sanitized staged guidance candidates for one live context.

This handler deliberately opens the existing SQLite database in ``mode=ro``. It
never instantiates ``StateStore``/``Store``, because their migration and directory
initialization paths are writes and would violate an observation-only endpoint.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import quote

from helpers.api import ApiHandler, Request, Response

from usr.plugins.dspy_rlm.api.status import objective_bucket, resolve_context_config
from usr.plugins.dspy_rlm.helpers.paths import STORE_FILE

_MAX_LIMIT = 100
_PUBLIC_ENGINES = frozenset({"heuristic", "gepa"})
_PUBLIC_CANDIDATE_STATUSES = frozenset({"candidate", "rejected", "failed", "succeeded"})
_PUBLIC_PROMOTION_DECISIONS = frozenset({"candidate_ready", "promote", "reject", "review_only"})


def _limit(value: Any) -> int | None:
    if value is None:
        return 20
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if 1 <= parsed <= _MAX_LIMIT else None


def _candidate_view(row: Mapping[str, Any]) -> dict[str, Any]:
    payload = row.get("candidate") if isinstance(row.get("candidate"), Mapping) else {}
    engine = str(payload.get("engine") or "")
    status = str(payload.get("status") or "candidate")
    decision = str(payload.get("promotion_decision") or "")
    return {
        "candidate_id": str(row.get("candidate_id") or "")[:128],
        "guidance_version": str(row.get("guidance_version") or "")[:128],
        "objective_bucket": objective_bucket(row.get("objective_bucket")) or "",
        "created_at": row.get("created_at") if isinstance(row.get("created_at"), (str, int, float)) else None,
        "engine": engine if engine in _PUBLIC_ENGINES else "unknown",
        "status": status if status in _PUBLIC_CANDIDATE_STATUSES else "candidate",
        "promotion_decision": decision if decision in _PUBLIC_PROMOTION_DECISIONS else "",
    }


def _read_candidates(database: Path, context_id: str, bucket: str | None, limit: int) -> list[Mapping[str, Any]]:
    """Read candidates through a SQLite read-only URI, with no schema mutation.

    The file must already exist. ``mode=ro`` prevents creation, WAL/checkpoint
    writes, migrations, and directory setup even if this endpoint is called for a
    context whose plugin state has never been initialized.
    """
    if not database.is_file():
        return []
    uri = f"file:{quote(str(database.resolve()))}?mode=ro"
    sql = (
        "SELECT candidate_id,objective_bucket,guidance_version,candidate_json,created_at "
        "FROM candidates WHERE context_id=?"
    )
    args: list[Any] = [context_id]
    if bucket:
        sql += " AND objective_bucket=?"
        args.append(bucket)
    sql += " ORDER BY created_at DESC LIMIT ?"
    args.append(limit)
    # query_only supplies a second guard in case a future query is changed.
    with sqlite3.connect(uri, uri=True) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        return conn.execute(sql, args).fetchall()


class CandidatesList(ApiHandler):
    async def process(self, input: dict, request: Request) -> dict | Response:
        context, _cfg, error = resolve_context_config(input)
        if error:
            return error
        assert context is not None
        bucket = objective_bucket(input.get("objective_bucket", ""))
        if input.get("objective_bucket") not in (None, "") and bucket is None:
            return Response(status=400, response="unknown objective_bucket", mimetype="text/plain")
        limit = _limit(input.get("limit"))
        if limit is None:
            return Response(status=400, response="limit must be between 1 and 100", mimetype="text/plain")

        try:
            rows = _read_candidates(STORE_FILE, str(context.id), bucket, limit)
        except (OSError, sqlite3.DatabaseError):
            # A first-use, unavailable, or pre-migration store is observationally
            # equivalent to no candidates. Do not expose local database details.
            rows = []

        candidates = []
        for row in rows:
            try:
                payload = json.loads(row["candidate_json"] or "{}")
            except (TypeError, ValueError):
                payload = {}
            candidates.append(_candidate_view({**dict(row), "candidate": payload if isinstance(payload, Mapping) else {}}))
        return {"plugin": "dspy_rlm", "context_id": str(context.id), "candidates": candidates}
