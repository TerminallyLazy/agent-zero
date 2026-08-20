"""Compatibility trace facade backed by authoritative SQLite evidence.

The public trace functions retain their legacy names, but every operational read and
write goes through the plugin SQLite store.  The retired JSONL path is not consulted
for optimization decisions and is never a source of durable evidence truth.
"""
from __future__ import annotations

import json
import threading
from collections import Counter
from datetime import datetime
from typing import Any, Iterable, Mapping

from .evidence import EvidencePolicy, project_event, retain_events, sanitize_event, utc_now_iso
from .paths import COMPILED_STATE_FILE
from .redaction import APPROVED_REDACTED_CONTENT_MODE, RedactionPolicy


_TRACE_LOCK = threading.RLock()


def _utc_now_iso() -> str:
    """Backward-compatible timestamp helper."""
    return utc_now_iso()


def _truncate(value: Any, limit: int) -> str:
    """Deprecated compatibility helper. New persistence uses content refs instead."""
    text = str(value or "")
    return text if len(text) <= limit else text[: max(0, limit - 3)] + "..."


def policy_from_config(config: Mapping[str, Any] | None = None) -> EvidencePolicy:
    """Build bounded evidence limits from normalized or sparse plugin config."""
    config = config if isinstance(config, Mapping) else {}
    capture = config.get("trace_capture", {})
    capture = capture if isinstance(capture, Mapping) else {}
    privacy = capture.get("privacy", {})
    privacy = privacy if isinstance(privacy, Mapping) else {}

    def integer(name: str, default: int) -> int:
        try:
            value = int(capture.get(name, default))
        except (TypeError, ValueError):
            return default
        return max(0, min(value, 2_000_000))

    mode = str(privacy.get("mode") or "")
    redaction = RedactionPolicy(
        max_total_chars=integer("max_event_payload_chars", 1_400),
        max_string_chars=min(integer("max_event_payload_chars", 1_400), 2_000),
        allow_content=bool(privacy.get("allow_redacted_content", False)),
        privacy_mode=mode,
    )
    return EvidencePolicy(
        max_events_per_context=integer("max_events_per_context", 1_800),
        max_events_per_loop=integer("max_events_per_loop", 160),
        event_ttl_seconds=integer("event_ttl_seconds", 604_800),
        max_event_payload_chars=integer("max_event_payload_chars", 1_400),
        redaction=redaction,
    )


def _event_created_at(event: Mapping[str, Any]) -> float | None:
    value = event.get("ts")
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _store():
    # Import lazily to keep the compatibility facade free of initialization cycles.
    from . import state
    return state._store_for_root().store


def _read_event_rows_unlocked(policy: EvidencePolicy) -> list[tuple[str, dict[str, Any]]]:
    """Read only verified projections from authoritative SQLite storage."""
    try:
        with _store()._connect() as conn:
            rows = conn.execute(
                "SELECT event_id,event_json FROM evidence_events ORDER BY created_at ASC,event_id ASC"
            ).fetchall()
    except Exception:
        return []
    projected: list[tuple[str, dict[str, Any]]] = []
    for row in rows:
        try:
            payload = json.loads(row["event_json"])
        except (TypeError, ValueError):
            continue
        event = project_event(payload, policy=policy) if isinstance(payload, Mapping) else {}
        if event:
            projected.append((str(row["event_id"]), event))
    return projected


def _retained_rows_unlocked(policy: EvidencePolicy) -> list[tuple[str, dict[str, Any]]]:
    rows = _read_event_rows_unlocked(policy)
    retained = retain_events((event for _, event in rows), policy=policy)
    retained_ids = {str(event.get("event_ref") or "") for event in retained}
    # Store event IDs are event refs.  A failed or malformed legacy row cannot be
    # returned as evidence, and is removed on the next retention sweep.
    return [(event_id, event) for event_id, event in rows if event_id in retained_ids]


def _prune_store_unlocked(policy: EvidencePolicy) -> list[tuple[str, dict[str, Any]]]:
    rows = _read_event_rows_unlocked(policy)
    retained = retain_events((event for _, event in rows), policy=policy)
    retained_ids = {str(event.get("event_ref") or "") for event in retained}
    stale_ids = [event_id for event_id, _ in rows if event_id not in retained_ids]
    if stale_ids:
        try:
            with _store()._connect() as conn:
                conn.executemany("DELETE FROM evidence_events WHERE event_id=?", ((event_id,) for event_id in stale_ids))
        except Exception:
            # Reads remain fail-closed even when a retention delete cannot run.
            pass
    return [(event_id, event) for event_id, event in rows if event_id in retained_ids]


def _read_events(*, policy: EvidencePolicy | None = None) -> list[dict[str, Any]]:
    policy = policy or EvidencePolicy()
    with _TRACE_LOCK:
        return [event for _, event in _retained_rows_unlocked(policy)]


def append_event(event: dict[str, Any], *, policy: EvidencePolicy | None = None) -> dict[str, Any] | None:
    """Sanitize and append one event to SQLite; capture failures never disturb a loop."""
    policy = policy or EvidencePolicy()
    safe_event = sanitize_event(event, policy=policy)
    if not safe_event:
        return None
    event_id = str(safe_event.get("event_ref") or "")
    if not event_id:
        return None
    try:
        with _TRACE_LOCK:
            _store().append_evidence(
                event_id, str(safe_event["context_id"]), str(safe_event["event_type"]), safe_event,
                created_at=_event_created_at(safe_event),
            )
            _prune_store_unlocked(policy)
    except Exception:
        return None
    return safe_event


def read_context_events(context_id: str, limit: int | None = None, *, policy: EvidencePolicy | None = None) -> list[dict[str, Any]]:
    """Return bounded SQLite evidence for a context, never the retired JSONL cache."""
    if not context_id:
        return []
    events = [event for event in _read_events(policy=policy) if event.get("context_id") == str(context_id)]
    return events[-limit:] if limit is not None and limit > 0 else events


def record_tool_event(
    context_id: str, agent_name: str, tool_name: str, response_text: str,
    loop_iteration: int, tool_args: dict[str, Any] | None, success: bool = True,
    *, policy: EvidencePolicy | None = None,
) -> dict[str, Any]:
    """Capture tool metadata only; text and arguments are opaque by default."""
    return append_event({
        "context_id": context_id, "event_type": "tool", "agent_name": agent_name,
        "tool": tool_name, "loop_iteration": loop_iteration, "success": success,
        "response_text": response_text, "tool_args": tool_args or {},
    }, policy=policy) or {}


def record_loop_event(
    context_id: str, agent_name: str, objective: str, loop_iteration: int,
    response_text: str, *, policy: EvidencePolicy | None = None,
) -> dict[str, Any]:
    """Capture a loop projection with approved objective text or opaque objective metadata."""
    return append_event({
        "context_id": context_id, "event_type": "loop", "agent_name": agent_name,
        "loop_iteration": loop_iteration, "success": bool(str(response_text or "").strip()),
        "objective": objective, "response_text": response_text,
    }, policy=policy) or {}


def _sanitize_tool_args(args: dict[str, Any]) -> dict[str, Any]:
    """Compatibility helper returning a recursively redacted, non-persisted mapping."""
    from .redaction import sanitize_mapping
    return sanitize_mapping(args, policy=RedactionPolicy(max_total_chars=1_400))


def summarize_context(context_id: str, limit: int = 200) -> dict[str, Any]:
    """Aggregate safe metadata without reflecting objective or response text."""
    events = read_context_events(context_id, limit=limit)
    if not events:
        return {"event_count": 0, "loop_count": 0, "tool_count": 0, "success_rate": 0.0,
                "top_tools": [], "latest_objective": "", "latest_response": "", "latest_ts": ""}
    loop_events = [event for event in events if event.get("event_type") == "loop"]
    tool_events = [event for event in events if event.get("event_type") == "tool"]
    counter = Counter(event.get("tool") for event in tool_events if event.get("tool") not in {"", "none", None})
    success_count = sum(1 for event in tool_events if event.get("success", True))
    return {"event_count": len(events), "loop_count": len(loop_events), "tool_count": len(tool_events),
            "success_rate": float(success_count) / max(1, len(tool_events)),
            "top_tools": [{"tool": tool, "count": count} for tool, count in counter.most_common(5)],
            "latest_objective": "", "latest_response": "", "latest_ts": events[-1].get("ts", "")}


def prune(*, policy: EvidencePolicy | None = None) -> int:
    """Apply TTL and caps to the authoritative SQLite evidence table."""
    policy = policy or EvidencePolicy()
    with _TRACE_LOCK:
        return len(_prune_store_unlocked(policy))


def truncate_file(limit: int) -> int:
    """Legacy count cap applied to SQLite evidence; no JSONL file is written."""
    if limit <= 0:
        return 0
    with _TRACE_LOCK:
        rows = _read_event_rows_unlocked(EvidencePolicy())
        stale = rows[:-limit]
        if stale:
            try:
                with _store()._connect() as conn:
                    conn.executemany("DELETE FROM evidence_events WHERE event_id=?", ((event_id,) for event_id, _ in stale))
            except Exception:
                return 0
        return min(limit, len(rows))


def load_last_compiled_guidance(context_id: str) -> str:
    """Load existing guidance cache without changing its legacy public behavior."""
    if not COMPILED_STATE_FILE.exists():
        return ""
    try:
        payload = json.loads(COMPILED_STATE_FILE.read_text(encoding="utf-8") or "{}")
    except (OSError, TypeError, ValueError):
        return ""
    if not isinstance(payload, dict):
        return ""
    if context_id:
        by_context = payload.get("contexts", {})
        context_payload = by_context.get(context_id, {}) if isinstance(by_context, dict) else {}
        if isinstance(context_payload, dict):
            return str(context_payload.get("guidance", ""))
    global_payload = payload.get("global", {})
    return str(global_payload.get("guidance", "")) if isinstance(global_payload, dict) else ""


__all__ = [
    "APPROVED_REDACTED_CONTENT_MODE", "EvidencePolicy", "append_event", "load_last_compiled_guidance",
    "policy_from_config", "prune", "read_context_events", "record_loop_event", "record_tool_event",
    "summarize_context", "truncate_file",
]
