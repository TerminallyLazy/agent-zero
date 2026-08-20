from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from . import trace


BUCKET_KEYWORDS: dict[str, list[str]] = {
    "shell": ["shell", "command", "bash", "sh", "terminal", "run", "exec", "python", "node", "curl", "rm", "cat", "ls", "cd"],
    "tool_retrieval": ["search", "query", "lookup", "get", "fetch", "read", "fetch", "file", "url", "document", "knowledge"],
    "decision_making": ["decide", "choose", "should", "policy", "priority", "tradeoff", "risk", "whether", "plan", "recommend", "strategy"],
}


def _short(value: Any, max_chars: int) -> str:
    text = str(value or "")
    text = text.strip()
    if len(text) <= max_chars:
        return text
    if max_chars <= 3:
        return text[:max_chars]
    return text[: max_chars - 3] + "..."


def _safe_ts(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except Exception:
            pass
    return 0.0


def _infer_output_type(objective: str) -> str:
    objective_lower = (objective or "").lower()
    if "json" in objective_lower:
        return "json"
    if "list" in objective_lower or "bullet" in objective_lower:
        return "list"
    if any(token in objective_lower for token in ("code", "python", "script", "snippet")):
        return "code"
    if any(token in objective_lower for token in ("compare", "analysis", "explain", "summary", "report")):
        return "text_explanation"
    return "text"


def _bucket_score(text: str, bucket: str) -> bool:
    text_lower = text.lower()
    if bucket not in BUCKET_KEYWORDS:
        return False
    return any(token in text_lower for token in BUCKET_KEYWORDS[bucket])


def infer_bucket(objective: str, tools: list[str]) -> str:
    objective_clean = (objective or "").strip().lower()
    tools = [tool.lower() for tool in tools]

    if any(_bucket_score(objective_clean, "shell") for _ in ("",)) or any(
        any(token in tool for token in ("shell", "terminal", "exec", "command")) for tool in tools
    ):
        return "shell"
    if any(_bucket_score(objective_clean, "tool_retrieval") for _ in ("",)) or any(
        any(token in tool for token in ("search", "lookup", "query", "read", "get")) for tool in tools
    ):
        return "tool_retrieval"
    if _bucket_score(objective_clean, "decision_making") or "decide" in objective_clean:
        return "decision_making"
    return "reasoning"


def _signature(*parts: Any) -> str:
    joined = "|".join(_short(p, 220) for p in parts)
    return hashlib.sha1(joined.encode("utf-8")).hexdigest()[:16]


def _objective_representation(event: dict[str, Any]) -> tuple[str, str]:
    """Return an approved objective preview or its opaque durable reference.

    Evidence policy deliberately permits collection when content capture is disabled:
    the SHA-256 reference identifies an observed objective without turning response
    text into a synthetic substitute.  Callers must only expose the first return
    value as user-facing intent.
    """
    preview = event.get("objective_preview")
    if isinstance(preview, str) and preview.strip():
        return preview.strip(), str(event.get("objective_ref") or "")
    reference = event.get("objective_ref")
    if isinstance(reference, str) and reference.startswith("sha256:"):
        return "", reference
    return "", ""


def _group_tool_events(
    events: list[dict[str, Any]], *, max_tool_contract: int = 8
) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for event in events:
        name = str(event.get("tool") or event.get("tool_name") or "unknown").strip()
        if not name:
            name = "unknown"
        bucket = grouped.setdefault(
            name,
            {
                "tool": name,
                "calls": 0,
                "success": 0,
                "failure": 0,
                "latest_preview": "",
            },
        )
        bucket["calls"] += 1
        if event.get("success", True):
            bucket["success"] += 1
        else:
            bucket["failure"] += 1
        if not bucket["latest_preview"]:
            bucket["latest_preview"] = str(event.get("response_preview", "") or "")

    contract_items = sorted(grouped.values(), key=lambda item: (item["calls"], item["tool"]), reverse=True)
    return contract_items[:max_tool_contract]


def collect_recent_objectives(context_id: str, cfg: dict[str, Any]) -> list[dict[str, Any]]:
    if not context_id:
        return []

    optimization = cfg.get("optimization", {}) if isinstance(cfg, dict) else {}
    lookback = int(optimization.get("objective_signature_lookback", 25) or 25)
    max_samples = int(optimization.get("max_samples_per_objective", 3) or 3)
    if max_samples <= 0:
        max_samples = 1

    events = trace.read_context_events(context_id, limit=None)
    if not events:
        return []

    loop_events = [
        event for event in events
        if str(event.get("event_type")) == "loop" and _objective_representation(event)[1]
    ]
    if not loop_events:
        # Do not derive an objective from response content.  That would both erase
        # the privacy boundary and manufacture a training target not supplied by
        # the user. Tool-only traces therefore remain non-objective evidence.
        return []

    sampled = loop_events[-lookback:]
    recent: list[dict[str, Any]] = []

    for idx, loop_event in enumerate(reversed(sampled[-max_samples:])):
        loop_iteration = int(loop_event.get("loop_iteration", -1) or -1)
        window_start = _safe_ts(loop_event.get("ts"))
        window_end = window_start

        tool_events = [
            event
            for event in events
            if str(event.get("event_type")) == "tool" and int(event.get("loop_iteration", -1) or -1) == loop_iteration
        ]
        if not tool_events:
            # fallback: gather nearby tool events around this loop iteration
            lo = loop_iteration - 1
            hi = loop_iteration + 1
            tool_events = [
                event
                for event in events
                if str(event.get("event_type")) == "tool"
                and int(event.get("loop_iteration", -1) or -1) in (lo, hi)
            ]
        if tool_events:
            window_start = min(window_start, min(_safe_ts(e.get("ts")) for e in tool_events))
            window_end = max(window_end, max(_safe_ts(e.get("ts")) for e in tool_events))

        objective, objective_ref = _objective_representation(loop_event)
        tool_names = [str(item.get("tool") or item.get("tool_name") or "") for item in tool_events]
        # With content capture disabled, classification relies only on tool and
        # event metadata.  The opaque reference remains a stable family key.
        bucket = infer_bucket(objective, tool_names)

        success = sum(1 for item in tool_events if bool(item.get("success", True)))
        failure = sum(1 for item in tool_events if not bool(item.get("success", True)))
        latest_tool = tool_names[0] if tool_names else ""

        contract = [str(item["tool"]) for item in _group_tool_events(tool_events)]
        response_candidates = [
            str(item.get("response_preview", "") or "")
            for item in tool_events
            if item.get("response_preview")
        ]

        latest_response = next((value for value in response_candidates if value), "")
        objective_signature = _signature(context_id, bucket, objective_ref, latest_tool, loop_iteration)
        objective_id = f"{context_id}|{bucket}|{objective_ref[-16:]}|{loop_iteration}|{idx}"

        recent.append(
            {
                "context_id": str(context_id),
                "objective_id": _short(objective_id, 80),
                "objective_bucket": bucket,
                "objective_signature": objective_signature,
                "objective_ref": objective_ref,
                "objective_content_approved": bool(objective),
                "user_intent": _short(objective, 420),
                "expected_output_type": _infer_output_type(objective) if objective else "unknown",
                "trace_window": {
                    "start_ts": window_start,
                    "end_ts": window_end,
                },
                "trace_window_events": len(tool_events) + 1,
                "success_events": int(success),
                "failure_events": int(failure),
                "objective_confidence": min(1.0, 1.0 / (1.0 + max(0, failure - success + 2))),
                "tool_contract": contract,
                "tool_error_classes": sorted({"tool_error" for item in tool_events if not item.get("success", True)}),
                "loop_iteration": loop_iteration,
                "latest_response": _short(latest_response, int(cfg.get("optimization", {}).get("max_sample_size_chars", 2000)),),
                "event_count": len(tool_events) + 1,
                "tool_count": len(tool_events),
                "preview_ts": trace_events_timestamp(tool_events),
            }
        )

    # Remove near-duplicates so matrix scoring has stable coverage.
    deduped: dict[str, dict[str, Any]] = {}
    for item in recent:
        sig = item["objective_signature"]
        if sig not in deduped:
            deduped[sig] = item
    ordered = list(reversed(deduped.values()))
    ordered.sort(key=lambda item: int(item.get("loop_iteration", -1)), reverse=True)
    return ordered[:max_samples]


def trace_events_timestamp(tool_events: list[dict[str, Any]]) -> str:
    if not tool_events:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    latest = max(_safe_ts(event.get("ts")) for event in tool_events)
    try:
        return datetime.fromtimestamp(latest, tz=timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    except Exception:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def objective_payload_key(sample: dict[str, Any]) -> str:
    return _signature(
        sample.get("context_id", ""),
        sample.get("objective_bucket", "reasoning"),
        sample.get("objective_signature", ""),
    )
