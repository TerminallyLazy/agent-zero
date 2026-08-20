"""Privacy-bounded evidence projections, retention, and immutable sample manifests.

The module accepts untrusted loop/tool payloads but exposes only explicitly allowlisted,
redacted event fields.  Storage is supplied by the caller so capture can fail open for
Agent Zero's message loop while evidence retention remains fail closed.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
import json
import re
import time
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Protocol, Sequence

from .redaction import RedactionPolicy, content_hash, redact_text, safe_label, sanitize_mapping


EVENT_VERSION = "v2"
_EVENT_TYPES = frozenset({"tool", "loop", "turn"})
_HASH_REF_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_SAFE_EVENT_FIELDS = frozenset(
    {
        "context_id", "context_ref", "event_type", "agent_name", "tool", "success",
        "loop_iteration", "objective_bucket", "objective_ref", "objective_present",
        "objective_preview", "error_class", "ts", "timestamp", "content_preview",
        "content_ref", "payload_ref", "event_ref", "redacted",
        "projection_version",
    }
)


@dataclass(frozen=True)
class EvidencePolicy:
    """Hard capture limits. Zero cap values disable that scope rather than bypass it."""

    max_events_per_context: int = 1_800
    max_events_per_loop: int = 160
    event_ttl_seconds: int = 604_800
    max_event_payload_chars: int = 1_400
    max_sample_events: int = 200
    redaction: RedactionPolicy = field(default_factory=RedactionPolicy)

    def __post_init__(self) -> None:
        for name in (
            "max_events_per_context", "max_events_per_loop", "event_ttl_seconds",
            "max_event_payload_chars", "max_sample_events",
        ):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if not isinstance(self.redaction, RedactionPolicy):
            raise TypeError("redaction must be a RedactionPolicy")


class EvidencePersistence(Protocol):
    """Minimal safe persistence seam. Implementations must append only sanitized events."""

    def append(self, event: Mapping[str, Any]) -> None: ...


class MemoryEvidenceStore:
    """Small in-memory persistence implementation useful for callers and smoke checks."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def append(self, event: Mapping[str, Any]) -> None:
        self.events.append(dict(project_event(event)))


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _timestamp(value: Any) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except ValueError:
            pass
    return 0.0


def _iso_timestamp(value: Any) -> str:
    stamp = _timestamp(value)
    if stamp <= 0:
        return utc_now_iso()
    return datetime.fromtimestamp(stamp, timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _bounded_int(value: Any, *, fallback: int = -1, minimum: int = -1, maximum: int = 1_000_000) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError):
        return fallback
    return min(maximum, max(minimum, result))


def _context_id(value: Any) -> str:
    """Keep compatibility lookup IDs bounded; malformed values become opaque refs."""
    text = str(value or "").strip()
    if not text:
        return ""
    # Context IDs are runtime routing data, not evidence. Keep only simple compact IDs.
    if len(text) <= 128 and all(character.isalnum() or character in "_.:-" for character in text):
        return text
    return "ctx_" + content_hash(text).rsplit(":", 1)[-1][:24]


def _error_class(value: Any, *, success: bool) -> str:
    if success:
        return "none"
    candidate = safe_label(value, fallback="failure")
    return candidate if candidate != "unknown" else "failure"


def _content_value(event: Mapping[str, Any]) -> Any:
    for key in ("content", "response_text", "response_preview", "response", "message", "objective"):
        if key in event:
            return event[key]
    return ""


def sanitize_event(event: Mapping[str, Any] | None, *, policy: EvidencePolicy | None = None) -> dict[str, Any] | None:
    """Convert an untrusted tool/loop payload into one redacted bounded event.

    Raw content is omitted by default.  An explicit approved redaction mode may retain
    a recursively-redacted preview, but prompt-injection-shaped content remains blocked.
    """
    if not isinstance(event, Mapping):
        return None
    policy = policy or EvidencePolicy()
    context_id = _context_id(event.get("context_id"))
    if not context_id:
        return None
    event_type = str(event.get("event_type") or "").lower()
    if event_type not in _EVENT_TYPES:
        return None
    success = bool(event.get("success", True))
    content = _content_value(event)
    objective = event.get("objective")
    safe: dict[str, Any] = {
        "context_id": context_id,
        "context_ref": content_hash(context_id),
        "event_type": event_type,
        "agent_name": safe_label(event.get("agent_name"), fallback="unknown"),
        "tool": safe_label(event.get("tool", event.get("tool_name")), fallback="none"),
        "success": success,
        "loop_iteration": _bounded_int(event.get("loop_iteration")),
        "objective_bucket": safe_label(event.get("objective_bucket"), fallback="unknown"),
        "error_class": _error_class(event.get("error_class"), success=success),
        "ts": _iso_timestamp(event.get("ts", event.get("timestamp"))),
        "redacted": True,
        "projection_version": EVENT_VERSION,
    }
    # A loop objective must survive as either an explicitly approved, redacted
    # representation or opaque metadata.  The latter is enough to construct a
    # sample without silently treating response text as the user's objective.
    if objective not in (None, ""):
        safe["objective_present"] = True
        safe["objective_ref"] = content_hash(redact_text(objective, limit=policy.redaction.max_string_chars))
        if policy.redaction.content_allowed:
            preview = redact_text(objective, limit=min(policy.max_event_payload_chars, policy.redaction.max_string_chars))
            if preview:
                safe["objective_preview"] = preview
    # Hash raw content regardless of retention mode. It supports duplicate detection
    # and audit linkage without making content visible to RLM or persistence readers.
    if content not in (None, ""):
        safe["content_ref"] = content_hash(redact_text(content, limit=policy.redaction.max_string_chars))
    # Recursively sanitize first, then hash the sanitized representation. This avoids
    # preserving raw secret-derived hashes that could enable equality/correlation of a
    # credential across captures, while still yielding deterministic payload identity.
    safe_payload = sanitize_mapping(event, policy=policy.redaction, allow_text=False)
    safe["payload_ref"] = content_hash(safe_payload)
    if policy.redaction.content_allowed and content not in (None, ""):
        preview = redact_text(content, limit=min(policy.max_event_payload_chars, policy.redaction.max_string_chars))
        if preview:
            safe["content_preview"] = preview
    safe["event_ref"] = content_hash({key: value for key, value in safe.items() if key != "event_ref"})
    return project_event(safe, policy=policy)


def project_event(event: Mapping[str, Any], *, policy: EvidencePolicy | None = None) -> dict[str, Any]:
    """Re-project an event to the durable allowlist and recursively sanitize preview text."""
    if not isinstance(event, Mapping):
        return {}
    policy = policy or EvidencePolicy()
    projected = {key: event[key] for key in _SAFE_EVENT_FIELDS if key in event}
    # Never allow unknown fields to tunnel through an allegedly sanitized event.
    context_id = _context_id(projected.get("context_id"))
    event_type = str(projected.get("event_type") or "").lower()
    if not context_id or event_type not in _EVENT_TYPES or projected.get("redacted") is not True:
        return {}
    result: dict[str, Any] = {
        "context_id": context_id,
        "context_ref": str(projected.get("context_ref") or content_hash(context_id)),
        "event_type": event_type,
        "agent_name": safe_label(projected.get("agent_name"), fallback="unknown"),
        "tool": safe_label(projected.get("tool"), fallback="none"),
        "success": bool(projected.get("success", True)),
        "loop_iteration": _bounded_int(projected.get("loop_iteration")),
        "objective_bucket": safe_label(projected.get("objective_bucket"), fallback="unknown"),
        "error_class": _error_class(projected.get("error_class"), success=bool(projected.get("success", True))),
        "ts": _iso_timestamp(projected.get("ts")),
        "redacted": True,
        "projection_version": EVENT_VERSION,
    }
    for key in ("content_ref", "payload_ref", "event_ref", "objective_ref"):
        value = projected.get(key)
        if isinstance(value, str) and _HASH_REF_RE.fullmatch(value):
            result[key] = value
    # A boolean avoids interpreting an empty/malformed opaque ref as objective
    # evidence while still permitting approved content-free collection.
    if projected.get("objective_present") is True and "objective_ref" in result:
        result["objective_present"] = True
    if policy.redaction.content_allowed and isinstance(projected.get("content_preview"), str):
        result["content_preview"] = redact_text(
            projected["content_preview"], limit=min(policy.max_event_payload_chars, policy.redaction.max_string_chars)
        )
    if policy.redaction.content_allowed and isinstance(projected.get("objective_preview"), str) and result.get("objective_present"):
        result["objective_preview"] = redact_text(
            projected["objective_preview"], limit=min(policy.max_event_payload_chars, policy.redaction.max_string_chars)
        )
    result.setdefault("event_ref", content_hash({key: value for key, value in result.items() if key != "event_ref"}))
    return result


def retain_events(events: Iterable[Mapping[str, Any]], *, policy: EvidencePolicy | None = None, now: float | None = None) -> list[dict[str, Any]]:
    """TTL-sweep and cap events by context and loop, returning oldest-to-newest events."""
    policy = policy or EvidencePolicy()
    current = time.time() if now is None else float(now)
    minimum_ts = current - policy.event_ttl_seconds
    clean: list[dict[str, Any]] = []
    for candidate in events:
        projected = project_event(candidate, policy=policy)
        if not projected:
            continue
        if _timestamp(projected["ts"]) < minimum_ts:
            continue
        clean.append(projected)
    clean.sort(key=lambda item: (_timestamp(item["ts"]), str(item.get("event_ref", ""))))
    # Keep newest items within each cap. A reverse pass makes cap behavior stable.
    by_context: defaultdict[str, int] = defaultdict(int)
    by_loop: defaultdict[tuple[str, int], int] = defaultdict(int)
    retained_reverse: list[dict[str, Any]] = []
    for event in reversed(clean):
        context = event["context_id"]
        loop_key = (context, int(event["loop_iteration"]))
        if policy.max_events_per_context <= 0 or policy.max_events_per_loop <= 0:
            continue
        if by_context[context] >= policy.max_events_per_context or by_loop[loop_key] >= policy.max_events_per_loop:
            continue
        by_context[context] += 1
        by_loop[loop_key] += 1
        retained_reverse.append(event)
    return list(reversed(retained_reverse))


def safe_persist_event(store: EvidencePersistence | None, event: Mapping[str, Any], *, policy: EvidencePolicy | None = None) -> bool:
    """Append one verified projection and suppress storage errors from the live loop."""
    if store is None:
        return False
    projected = project_event(event, policy=policy)
    if not projected:
        return False
    try:
        store.append(MappingProxyType(projected))
    except Exception:
        return False
    return True


def objective_sample(
    context_id: str,
    events: Iterable[Mapping[str, Any]],
    *,
    objective_id: str = "",
    objective_bucket: str = "unknown",
    policy: EvidencePolicy | None = None,
) -> Mapping[str, Any]:
    """Build an immutable aggregate-only sample that contains no event content.

    ``objective_family`` is a stable opaque reference and is the split grouping key,
    preventing objective near-duplicates from leaking across train/dev/holdout sets.
    """
    policy = policy or EvidencePolicy()
    context = _context_id(context_id)
    selected = [event for event in retain_events(events, policy=policy) if event.get("context_id") == context]
    selected = selected[-policy.max_sample_events :] if policy.max_sample_events else []
    bucket = safe_label(objective_bucket, fallback="unknown")
    family_input = objective_id or bucket
    family_ref = content_hash({"objective": str(family_input).strip().lower(), "bucket": bucket})
    successful = sum(bool(event["success"]) for event in selected)
    tool_calls = sum(event["event_type"] == "tool" for event in selected)
    tool_refs = tuple(sorted({str(event.get("event_ref")) for event in selected if event.get("event_ref")}))
    sample = {
        "sample_id": content_hash({"context_ref": content_hash(context), "family": family_ref, "events": tool_refs}),
        "context_ref": content_hash(context),
        "objective_id_ref": content_hash(objective_id) if objective_id else "",
        "objective_bucket": bucket,
        "objective_family": family_ref,
        "event_refs": tool_refs,
        "event_count": len(selected),
        "tool_call_count": tool_calls,
        "success_count": successful,
        "failure_count": len(selected) - successful,
        "success_rate": round(successful / len(selected), 6) if selected else 0.0,
        "trace_window": MappingProxyType({
            "start_ts": _timestamp(selected[0]["ts"]) if selected else 0.0,
            "end_ts": _timestamp(selected[-1]["ts"]) if selected else 0.0,
        }),
        "redacted": True,
        "projection_version": EVENT_VERSION,
    }
    return MappingProxyType(sample)


def deterministic_splits(
    samples: Iterable[Mapping[str, Any]],
    *,
    seed: str = "v1",
    train_ratio: float = 0.70,
    dev_ratio: float = 0.15,
) -> Mapping[str, tuple[Mapping[str, Any], ...]]:
    """Create deterministic grouped train/dev/holdout partitions from safe samples."""
    if not (0.0 <= train_ratio <= 1.0 and 0.0 <= dev_ratio <= 1.0 and train_ratio + dev_ratio <= 1.0):
        raise ValueError("split ratios must be within [0, 1] and sum to at most 1")
    groups: defaultdict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for sample in samples:
        if not isinstance(sample, Mapping) or sample.get("redacted") is not True:
            continue
        family = str(sample.get("objective_family") or "")
        if not family.startswith("sha256:"):
            continue
        groups[family].append(MappingProxyType(dict(sample)))
    partitions: dict[str, list[Mapping[str, Any]]] = {"train": [], "dev": [], "holdout": []}
    train_limit = int(train_ratio * 10_000)
    dev_limit = int((train_ratio + dev_ratio) * 10_000)
    for family in sorted(groups):
        slot = int(sha256(f"{seed}|{family}".encode("utf-8")).hexdigest()[:8], 16) % 10_000
        partition = "train" if slot < train_limit else "dev" if slot < dev_limit else "holdout"
        partitions[partition].extend(sorted(groups[family], key=lambda item: str(item.get("sample_id", ""))))
    return MappingProxyType({name: tuple(values) for name, values in partitions.items()})


__all__ = [
    "EVENT_VERSION", "EvidencePersistence", "EvidencePolicy", "MemoryEvidenceStore",
    "deterministic_splits", "objective_sample", "project_event", "retain_events",
    "safe_persist_event", "sanitize_event", "utc_now_iso",
]
