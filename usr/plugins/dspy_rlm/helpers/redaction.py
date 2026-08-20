"""Fail-closed redaction and bounded projections for DSPy RLM evidence.

This module is deliberately dependency-free.  It never serializes an arbitrary object
with ``repr`` and treats unknown values as opaque, because error messages and custom
object representations frequently contain credentials.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import re
from collections.abc import Mapping, Sequence
from typing import Any


REDACTED = "<redacted>"
BLOCKED = "<blocked>"
TRUNCATED = "..."
APPROVED_REDACTED_CONTENT_MODE = "approved_redacted_content"

# Key matching is intentionally based on complete key segments.  A bare ``key`` is
# sensitive, but words such as ``monkey`` are not.
_SECRET_KEY_RE = re.compile(
    r"(?:^|[-_.])(?:password|passwd|pwd|secret|token|authorization|auth|cookie|"
    r"credential|api[-_]?key|access[-_]?key|private[-_]?key|key|apikey)(?:$|[-_.])",
    re.IGNORECASE,
)
_PEM_RE = re.compile(r"-----BEGIN [A-Z0-9 ]*(?:PRIVATE KEY|CERTIFICATE|OPENSSH PRIVATE KEY)[A-Z0-9 ]*-----.*?-----END [A-Z0-9 ].*?-----", re.IGNORECASE | re.DOTALL)
_JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}\b")
_URL_CREDENTIAL_RE = re.compile(r"\b([a-z][a-z0-9+.-]*://)([^\s/@:]+):([^\s/@]+)@", re.IGNORECASE)
_BEARER_RE = re.compile(r"\b(?:bearer|basic|token)\s+[A-Za-z0-9._~+/=-]{8,}", re.IGNORECASE)
_ASSIGNMENT_SECRET_RE = re.compile(
    r"\b(?:api[-_]?key|access[-_]?key|secret|token|password|passwd|authorization|cookie)"
    r"\s*[:=]\s*([^\s,;]{4,})",
    re.IGNORECASE,
)
_PROVIDER_TOKEN_RE = re.compile(r"\b(?:sk-[A-Za-z0-9_-]{12,}|AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{20,})\b")
_INJECTION_RE = re.compile(
    r"(?:\bignore\s+(?:all\s+)?(?:previous|prior)\s+(?:instructions|rules)\b|"
    r"\b(?:system|developer|assistant)\s*:\s*|"
    r"<\s*/?(?:system|developer|assistant|tool)\b|"
    r"\b(?:reveal|print|show)\s+(?:the\s+)?(?:system\s+)?prompt\b)",
    re.IGNORECASE,
)
_SAFE_LABEL_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,63}$")


@dataclass(frozen=True)
class RedactionPolicy:
    """Limits and privacy controls used for recursive sanitization.

    ``allow_content`` is only meaningful with ``privacy_mode`` set to
    :data:`APPROVED_REDACTED_CONTENT_MODE`.  This two-part opt-in prevents a caller
    from accidentally retaining message text by enabling a single loose boolean.
    """

    max_depth: int = 6
    max_items: int = 64
    max_string_chars: int = 512
    max_total_chars: int = 1_400
    allow_content: bool = False
    privacy_mode: str = ""

    def __post_init__(self) -> None:
        for name in ("max_depth", "max_items", "max_string_chars", "max_total_chars"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")

    @property
    def content_allowed(self) -> bool:
        return bool(self.allow_content and self.privacy_mode == APPROVED_REDACTED_CONTENT_MODE)


def content_hash(value: Any, *, prefix: str = "sha256") -> str:
    """Return a stable non-reversible reference without retaining the input value."""
    if isinstance(value, bytes):
        payload = value
    elif isinstance(value, str):
        payload = value.encode("utf-8", errors="replace")
    else:
        try:
            payload = json.dumps(value, sort_keys=True, ensure_ascii=False, default=_opaque_json).encode("utf-8")
        except (TypeError, ValueError):
            payload = type(value).__name__.encode("utf-8")
    return f"{prefix}:{sha256(payload).hexdigest()}"


def _opaque_json(value: Any) -> str:
    """JSON fallback that cannot expose a custom object's representation."""
    return f"<{type(value).__module__}.{type(value).__qualname__}>"


def is_sensitive_key(key: Any) -> bool:
    return bool(_SECRET_KEY_RE.search(str(key).strip()))


def contains_secret(value: Any) -> bool:
    """Conservatively identify common credential-bearing values without logging them."""
    if isinstance(value, Mapping):
        return any(is_sensitive_key(key) or contains_secret(item) for key, item in value.items())
    if isinstance(value, (list, tuple, set, frozenset)):
        return any(contains_secret(item) for item in value)
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    if not isinstance(value, str):
        return False
    return bool(
        _PEM_RE.search(value)
        or _JWT_RE.search(value)
        or _URL_CREDENTIAL_RE.search(value)
        or _BEARER_RE.search(value)
        or _ASSIGNMENT_SECRET_RE.search(value)
        or _PROVIDER_TOKEN_RE.search(value)
    )


def looks_like_prompt_injection(value: Any) -> bool:
    return isinstance(value, str) and bool(_INJECTION_RE.search(value))


def redact_text(value: Any, *, limit: int = 512, block_injection: bool = True) -> str:
    """Redact secret substrings, block prompt-role content, and bound retained text."""
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    if not isinstance(value, str):
        return f"<{type(value).__name__}>"
    if block_injection and looks_like_prompt_injection(value):
        return BLOCKED
    text = _PEM_RE.sub(REDACTED, value)
    text = _JWT_RE.sub(REDACTED, text)
    text = _URL_CREDENTIAL_RE.sub(r"\1" + REDACTED + ":" + REDACTED + "@", text)
    text = _BEARER_RE.sub(REDACTED, text)
    text = _ASSIGNMENT_SECRET_RE.sub(lambda match: match.group(0).split(match.group(1))[0] + REDACTED, text)
    text = _PROVIDER_TOKEN_RE.sub(REDACTED, text)
    text = " ".join(text.split())
    if limit <= 0:
        return ""
    return text if len(text) <= limit else text[: max(0, limit - len(TRUNCATED))] + TRUNCATED


def safe_label(value: Any, *, fallback: str = "unknown") -> str:
    """Return a compact metadata label, never arbitrary content."""
    text = str(value or "").strip()
    if not _SAFE_LABEL_RE.fullmatch(text) or is_sensitive_key(text) or looks_like_prompt_injection(text):
        return fallback
    return text


def _take_text(value: str, remaining: list[int]) -> str:
    """Apply the one shared retained-text budget for a recursive projection."""
    if remaining[0] <= 0:
        return ""
    kept = value[: remaining[0]]
    remaining[0] -= len(kept)
    return kept


def sanitize_value(
    value: Any,
    *,
    policy: RedactionPolicy | None = None,
    _depth: int = 0,
    _allow_text: bool = True,
    _remaining: list[int] | None = None,
) -> Any:
    """Recursively sanitize a value without retaining arbitrary object data.

    Mapping keys with secret semantics redact their entire value.  Sequence and mapping
    traversal is bounded at every level.  Sets are represented in deterministic order.
    """
    policy = policy or RedactionPolicy()
    remaining = _remaining if _remaining is not None else [policy.max_total_chars]
    if _depth > policy.max_depth:
        return "<max-depth>"
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        return value if value == value and abs(value) != float("inf") else "<non-finite>"
    if isinstance(value, str):
        if not _allow_text:
            return content_hash(value)
        return _take_text(redact_text(value, limit=policy.max_string_chars), remaining)
    if isinstance(value, bytes):
        return {"type": "bytes", "length": len(value), "ref": content_hash(value)}
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= policy.max_items:
                result["<truncated>"] = len(value) - index
                break
            safe_key = redact_text(str(key), limit=64, block_injection=False)
            if is_sensitive_key(key):
                result[safe_key] = REDACTED
            else:
                result[safe_key] = sanitize_value(
                    item, policy=policy, _depth=_depth + 1, _allow_text=_allow_text, _remaining=remaining
                )
        return result
    if isinstance(value, (list, tuple, set, frozenset)):
        items: Sequence[Any]
        if isinstance(value, (set, frozenset)):
            items = sorted(value, key=lambda item: content_hash(item))
        else:
            items = value
        result = [
            sanitize_value(item, policy=policy, _depth=_depth + 1, _allow_text=_allow_text, _remaining=remaining)
            for item in items[: policy.max_items]
        ]
        if len(items) > policy.max_items:
            result.append({"<truncated>": len(items) - policy.max_items})
        return result
    # Do not inspect __dict__, call properties, or use repr: either can leak secrets.
    return {"type": f"{type(value).__module__}.{type(value).__qualname__}", "ref": content_hash(type(value).__qualname__)}


def sanitize_mapping(
    value: Mapping[str, Any] | None,
    *,
    policy: RedactionPolicy | None = None,
    allowed_keys: set[str] | frozenset[str] | tuple[str, ...] | None = None,
    allow_text: bool = True,
) -> dict[str, Any]:
    """Sanitize a mapping and optionally project it onto an explicit field allowlist."""
    if not isinstance(value, Mapping):
        return {}
    permitted = set(allowed_keys) if allowed_keys is not None else None
    selected = {str(key): item for key, item in value.items() if permitted is None or str(key) in permitted}
    return sanitize_value(selected, policy=policy, _allow_text=allow_text)  # type: ignore[return-value]


__all__ = [
    "APPROVED_REDACTED_CONTENT_MODE",
    "BLOCKED",
    "REDACTED",
    "RedactionPolicy",
    "contains_secret",
    "content_hash",
    "is_sensitive_key",
    "looks_like_prompt_injection",
    "redact_text",
    "safe_label",
    "sanitize_mapping",
    "sanitize_value",
]
