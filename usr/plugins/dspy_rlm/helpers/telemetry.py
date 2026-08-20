from __future__ import annotations

from __future__ import annotations

import hashlib
import time
from typing import Any

EVENT_KEY = "_dspy_rlm_tool_events"


def _as_safe_text(value: Any, max_chars: int = 1200) -> str:
    if value is None:
        return ""
    text = str(value)
    text = text.replace("\x00", "")
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3] + "..."


def _safe_args(payload: Any, max_chars: int = 1400) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    output: dict[str, Any] = {}
    keys = ["command", "path", "query", "url", "input", "tool", "arguments", "model", "tool_name"]
    for key in keys:
        if key in payload:
            output[key] = _as_safe_text(payload[key], max_chars=max_chars // 4)
    if not output:
        return {
            k: _as_safe_text(v, max_chars=max_chars // 4)
            for k, v in list(payload.items())[:6]
            if isinstance(k, str)
        }
    return output


def append_tool_event(context, tool_name: str = "", args: Any = None, response: Any = None, status: str = "ok", error: str | None = None) -> dict[str, Any]:
    if not context or not isinstance(context, object):
        return {}

    context_data = getattr(context, "data", None)
    if not isinstance(context_data, dict):
        return {}

    now = time.time()
    event = {
        "event_id": hashlib.sha1(f"{tool_name}|{now}".encode("utf-8")).hexdigest()[:18],
        "tool_name": str(tool_name or "unknown")[:96],
        "status": "ok" if status == "ok" and not error else "error",
        "ts": now,
        "args": _safe_args(args),
        "response": _safe_args(
            response if isinstance(response, dict) else {}
            if response is None
            else getattr(response, "__dict__", response),
            max_chars=700,
        ),
    }
    if error:
        event["error"] = _as_safe_text(error, max_chars=500)

    events = context_data.get(EVENT_KEY)
    if not isinstance(events, list):
        events = []
    events.append(event)

    # bound by most recent 300 entries and keep only latest relevant state
    context_data[EVENT_KEY] = events[-300:]
    return event


def pop_tool_events(context, *, max_events: int | None = None) -> list[dict[str, Any]]:
    if not context or not isinstance(context, object):
        return []
    context_data = getattr(context, "data", None)
    if not isinstance(context_data, dict):
        return []

    events = context_data.get(EVENT_KEY)
    if not isinstance(events, list):
        return []

    if max_events is None or max_events <= 0:
        selected = list(events)
    else:
        selected = list(events)[-max_events:]

    context_data[EVENT_KEY] = []
    return selected


def collect_tool_events(context) -> list[dict[str, Any]]:
    if not context or not isinstance(context, object):
        return []
    context_data = getattr(context, "data", None)
    if not isinstance(context_data, dict):
        return []
    events = context_data.get(EVENT_KEY)
    if not isinstance(events, list):
        return []
    return list(events)
