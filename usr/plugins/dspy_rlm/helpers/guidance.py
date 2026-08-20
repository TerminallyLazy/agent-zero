"""Strict, non-executable guidance artifacts for the DSPy RLM prompt seam.

This module deliberately accepts no free-form instruction text.  A guidance
artifact can contain only scoped metadata, content hashes, and a small set of
fixed rule types.  Rendering maps those rule types to application-owned text,
so neither optimization output nor evidence can become prompt instructions.

The active selector reads only SQLite's active-guidance pointer through the
state facade.  Legacy ``guidance_text`` and JSON compatibility caches are not
an injection source.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import re
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = "guidance.v1"
RENDER_TARGET = "system_prompt"
MAX_RULES = 4
MAX_RENDERED_CHARS = 1_800
MAX_ARTIFACT_LIFETIME_SECONDS = 31 * 24 * 60 * 60

# These are deliberately capabilities, not prose templates supplied by a
# candidate engine.  The renderer below owns the complete prompt text.
_RULE_PARAMETERS: dict[str, frozenset[str]] = {
    "verify_tool_contract": frozenset(),
    "check_tool_result": frozenset(),
    "retry_after_failure": frozenset({"max_retries"}),
    "prefer_reversible_action": frozenset(),
    "bound_tool_scope": frozenset(),
}
_RULE_ORDER = {name: index for index, name in enumerate(_RULE_PARAMETERS)}

_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}$")
_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_URL_RE = re.compile(r"\b(?:https?|ftp|file)://", re.IGNORECASE)
_COMMAND_RE = re.compile(r"(?:^|[\s;|&])(?:rm|curl|wget|bash|sh|cmd|powershell|python|chmod|sudo)\b", re.IGNORECASE)
_ROLE_RE = re.compile(r"(?:^|\s)(?:system|developer|assistant|tool|user)\s*:", re.IGNORECASE)
_OVERRIDE_RE = re.compile(
    r"\b(?:ignore|override|bypass|disable)\b.{0,64}\b(?:instruction|policy|rule|guard|safety)\b",
    re.IGNORECASE,
)
_SECRET_RE = re.compile(
    r"(?:\b(?:api[-_]?key|access[-_]?key|secret|token|password|authorization|cookie)\b\s*[:=]|"
    r"\b(?:sk-[A-Za-z0-9_-]{12,}|AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{20,})\b|"
    r"-----BEGIN [A-Z0-9 ]+(?:PRIVATE KEY|CERTIFICATE))",
    re.IGNORECASE,
)
_RAW_FIELD_MARKERS = frozenset(
    {
        "content", "text", "guidance", "guidance_text", "prompt", "instruction",
        "message", "messages", "transcript", "response", "response_text",
        "response_preview", "user", "user_input", "user_message", "user_intent",
        "tool", "tool_name", "tool_args", "arguments", "command", "url", "uri",
        "model", "model_output", "llm_output", "rlm", "finding", "findings",
        "reason", "rationale", "summary", "error", "headers", "cookies",
        "authorization", "password", "secret", "token", "credential", "api_key",
    }
)
_ALLOWED_ARTIFACT_KEYS = frozenset(
    {
        "schema_version", "artifact_id", "context_id", "objective_bucket", "status",
        "render_target", "rules", "source_manifest_hashes", "source_finding_hashes",
        "issued_at", "expires_at", "engine", "artifact_digest",
    }
)
_ALLOWED_ENGINE_KEYS = frozenset({"kind", "version"})


class GuidanceValidationError(ValueError):
    """Raised when an artifact cannot safely become system-prompt guidance."""


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _digest(payload: Mapping[str, Any]) -> str:
    return "sha256:" + sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _safe_identifier(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise GuidanceValidationError(f"{field} must be a string")
    text = value.strip()
    if not _IDENTIFIER_RE.fullmatch(text):
        raise GuidanceValidationError(f"{field} must be a compact allowlisted identifier")
    lowered = text.lower()
    if any(marker in lowered for marker in ("secret", "token", "password", "credential", "apikey")):
        raise GuidanceValidationError(f"{field} contains unsafe text")
    return text


def _safe_hashes(value: Any, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value or len(value) > 32:
        raise GuidanceValidationError(f"{field} must contain 1 to 32 SHA-256 references")
    if any(not isinstance(item, str) or not _HASH_RE.fullmatch(item) for item in value):
        raise GuidanceValidationError(f"{field} must contain only SHA-256 references")
    if len(set(value)) != len(value):
        raise GuidanceValidationError(f"{field} must not contain duplicate references")
    return tuple(sorted(value))


def _parse_timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or len(value) > 40:
        raise GuidanceValidationError(f"{field} must be an RFC 3339 UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise GuidanceValidationError(f"{field} must be an RFC 3339 UTC timestamp") from error
    if parsed.tzinfo is None or value.endswith("Z") is False:
        raise GuidanceValidationError(f"{field} must be a UTC timestamp ending in Z")
    return parsed.astimezone(timezone.utc).replace(microsecond=0)


def _format_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _reject_unsafe_strings(value: Any, path: str = "artifact") -> None:
    """Reject strings/keys that could carry source text or executable content."""
    if isinstance(value, str):
        if len(value) > 256 or _URL_RE.search(value) or _COMMAND_RE.search(value):
            raise GuidanceValidationError(f"{path} contains unsafe text")
        if _ROLE_RE.search(value) or _OVERRIDE_RE.search(value) or _SECRET_RE.search(value):
            raise GuidanceValidationError(f"{path} contains unsafe text")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            name = str(key).strip().lower()
            if name in _RAW_FIELD_MARKERS:
                raise GuidanceValidationError(f"{path} contains prohibited raw field: {name}")
            _reject_unsafe_strings(item, f"{path}.{name}")
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _reject_unsafe_strings(item, f"{path}[{index}]")


def _normalise_rules(value: Any) -> tuple[tuple[str, int | None], ...]:
    if not isinstance(value, list) or not value or len(value) > MAX_RULES:
        raise GuidanceValidationError(f"rules must contain 1 to {MAX_RULES} allowlisted rules")
    rules: list[tuple[str, int | None]] = []
    for index, raw_rule in enumerate(value):
        if not isinstance(raw_rule, Mapping):
            raise GuidanceValidationError(f"rules[{index}] must be an object")
        keys = frozenset(str(key) for key in raw_rule)
        if "type" not in keys:
            raise GuidanceValidationError(f"rules[{index}].type is required")
        rule_type = raw_rule.get("type")
        if not isinstance(rule_type, str) or rule_type not in _RULE_PARAMETERS:
            raise GuidanceValidationError(f"rules[{index}] has an unrecognized rule type")
        expected = {"type", *_RULE_PARAMETERS[rule_type]}
        if keys != expected:
            raise GuidanceValidationError(f"rules[{index}] has unrecognized parameters")
        retries: int | None = None
        if rule_type == "retry_after_failure":
            retries = raw_rule.get("max_retries")
            if not isinstance(retries, int) or isinstance(retries, bool) or retries < 0 or retries > 2:
                raise GuidanceValidationError("retry_after_failure.max_retries must be an integer from 0 to 2")
        rules.append((rule_type, retries))
    if len({rule[0] for rule in rules}) != len(rules):
        raise GuidanceValidationError("rules must not contain duplicate rule types")
    return tuple(sorted(rules, key=lambda rule: _RULE_ORDER[rule[0]]))


@dataclass(frozen=True)
class GuidanceArtifact:
    """A validated, auditable artifact made solely of allowlisted values."""

    artifact_id: str
    context_id: str
    objective_bucket: str
    rules: tuple[tuple[str, int | None], ...]
    source_manifest_hashes: tuple[str, ...]
    source_finding_hashes: tuple[str, ...]
    issued_at: datetime
    expires_at: datetime
    engine_kind: str
    engine_version: str
    artifact_digest: str
    schema_version: str = SCHEMA_VERSION
    status: str = "promoted"
    render_target: str = RENDER_TARGET

    @classmethod
    def create(
        cls,
        *,
        artifact_id: str,
        context_id: str,
        objective_bucket: str,
        rules: Sequence[Mapping[str, Any]],
        source_manifest_hashes: Sequence[str],
        source_finding_hashes: Sequence[str],
        issued_at: str,
        expires_at: str,
        engine_kind: str,
        engine_version: str,
    ) -> "GuidanceArtifact":
        """Build a schema-valid artifact and calculate its content digest."""
        body = {
            "schema_version": SCHEMA_VERSION,
            "artifact_id": artifact_id,
            "context_id": context_id,
            "objective_bucket": objective_bucket,
            "status": "promoted",
            "render_target": RENDER_TARGET,
            "rules": [dict(item) for item in rules],
            "source_manifest_hashes": list(source_manifest_hashes),
            "source_finding_hashes": list(source_finding_hashes),
            "issued_at": issued_at,
            "expires_at": expires_at,
            "engine": {"kind": engine_kind, "version": engine_version},
        }
        body["artifact_digest"] = _digest(body)
        return cls.from_mapping(body)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "GuidanceArtifact":
        """Strictly validate a serialized artifact, including its digest."""
        if not isinstance(value, Mapping):
            raise GuidanceValidationError("guidance artifact must be an object")
        _reject_unsafe_strings(value)
        keys = frozenset(str(key) for key in value)
        if keys != _ALLOWED_ARTIFACT_KEYS:
            unexpected = sorted(keys - _ALLOWED_ARTIFACT_KEYS)
            missing = sorted(_ALLOWED_ARTIFACT_KEYS - keys)
            detail = ", ".join([*(f"unexpected {key}" for key in unexpected), *(f"missing {key}" for key in missing)])
            raise GuidanceValidationError(f"guidance artifact has invalid fields: {detail}")
        if value.get("schema_version") != SCHEMA_VERSION:
            raise GuidanceValidationError("unsupported guidance artifact schema")
        if value.get("status") != "promoted":
            raise GuidanceValidationError("only promoted guidance artifacts are renderable")
        if value.get("render_target") != RENDER_TARGET:
            raise GuidanceValidationError("guidance artifact is not compatible with system prompt rendering")
        engine = value.get("engine")
        if not isinstance(engine, Mapping) or frozenset(str(key) for key in engine) != _ALLOWED_ENGINE_KEYS:
            raise GuidanceValidationError("engine must contain only kind and version")
        engine_kind = engine.get("kind")
        if engine_kind not in {"heuristic", "gepa"}:
            raise GuidanceValidationError("engine.kind is not allowlisted")
        issued_at = _parse_timestamp(value.get("issued_at"), "issued_at")
        expires_at = _parse_timestamp(value.get("expires_at"), "expires_at")
        if expires_at <= issued_at:
            raise GuidanceValidationError("expires_at must be after issued_at")
        if (expires_at - issued_at).total_seconds() > MAX_ARTIFACT_LIFETIME_SECONDS:
            raise GuidanceValidationError("guidance artifact lifetime exceeds the maximum")
        artifact = cls(
            artifact_id=_safe_identifier(value.get("artifact_id"), "artifact_id"),
            context_id=_safe_identifier(value.get("context_id"), "context_id"),
            objective_bucket=_safe_identifier(value.get("objective_bucket"), "objective_bucket"),
            rules=_normalise_rules(value.get("rules")),
            source_manifest_hashes=_safe_hashes(value.get("source_manifest_hashes"), "source_manifest_hashes"),
            source_finding_hashes=_safe_hashes(value.get("source_finding_hashes"), "source_finding_hashes"),
            issued_at=issued_at,
            expires_at=expires_at,
            engine_kind=engine_kind,
            engine_version=_safe_identifier(engine.get("version"), "engine.version"),
            artifact_digest=str(value.get("artifact_digest") or ""),
        )
        if not _HASH_RE.fullmatch(artifact.artifact_digest):
            raise GuidanceValidationError("artifact_digest must be a SHA-256 reference")
        if artifact.artifact_digest != _digest(artifact._body()):
            raise GuidanceValidationError("guidance artifact digest does not match its contents")
        return artifact

    def _body(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "artifact_id": self.artifact_id,
            "context_id": self.context_id,
            "objective_bucket": self.objective_bucket,
            "status": self.status,
            "render_target": self.render_target,
            "rules": [
                {"type": name, **({"max_retries": retries} if retries is not None else {})}
                for name, retries in self.rules
            ],
            "source_manifest_hashes": list(self.source_manifest_hashes),
            "source_finding_hashes": list(self.source_finding_hashes),
            "issued_at": _format_timestamp(self.issued_at),
            "expires_at": _format_timestamp(self.expires_at),
            "engine": {"kind": self.engine_kind, "version": self.engine_version},
        }

    def to_mapping(self) -> dict[str, Any]:
        """Return the canonical persisted representation, including the digest."""
        return {**self._body(), "artifact_digest": self.artifact_digest}

    def is_expired(self, now: datetime | None = None) -> bool:
        reference = now or datetime.now(timezone.utc)
        if reference.tzinfo is None:
            reference = reference.replace(tzinfo=timezone.utc)
        return self.expires_at <= reference.astimezone(timezone.utc)


def validate_guidance_artifact(value: Mapping[str, Any] | GuidanceArtifact) -> GuidanceArtifact:
    """Return a validated artifact or raise :class:`GuidanceValidationError`."""
    if isinstance(value, GuidanceArtifact):
        return GuidanceArtifact.from_mapping(value.to_mapping())
    return GuidanceArtifact.from_mapping(value)


def render_guidance_artifact(
    value: Mapping[str, Any] | GuidanceArtifact,
    *,
    max_chars: int = MAX_RENDERED_CHARS,
    now: datetime | None = None,
) -> str:
    """Render one nonexpired artifact with fixed, application-owned wording."""
    artifact = validate_guidance_artifact(value)
    if artifact.is_expired(now):
        raise GuidanceValidationError("guidance artifact is expired")
    if not isinstance(max_chars, int) or isinstance(max_chars, bool) or max_chars <= 0:
        raise GuidanceValidationError("max_chars must be a positive integer")
    if max_chars > MAX_RENDERED_CHARS:
        max_chars = MAX_RENDERED_CHARS

    lines = [
        "DSPy RLM reliability guidance:",
        "Apply these checks only when consistent with the existing system instructions and tool contracts.",
    ]
    for name, retries in artifact.rules:
        if name == "verify_tool_contract":
            lines.append("- Before a tool call, verify its documented input contract and expected result.")
        elif name == "check_tool_result":
            lines.append("- Check a tool result for completion or a recoverable failure before taking the next step.")
        elif name == "retry_after_failure":
            lines.append(f"- After a recoverable tool failure, make at most {retries} corrected retry attempt(s).")
        elif name == "prefer_reversible_action":
            lines.append("- Prefer a reversible action when the available evidence does not establish a safe irreversible action.")
        elif name == "bound_tool_scope":
            lines.append("- Keep each tool action within the smallest scope needed for the current task.")
    rendered = "\n".join(lines)
    if len(rendered) > max_chars:
        raise GuidanceValidationError("rendered guidance exceeds the configured bound")
    return rendered


def _active_record(context_id: str, objective_bucket: str, state_store: Any | None) -> Mapping[str, Any] | None:
    if state_store is not None:
        getter = getattr(state_store, "get_active_guidance", None)
        return getter(context_id, objective_bucket) if callable(getter) else None
    # Import lazily: schema validation remains usable in isolated build/test tools
    # without initializing framework state or SQLite.
    from usr.plugins.dspy_rlm.helpers import state

    store_factory = getattr(state, "_store_for_root", None)
    if not callable(store_factory):
        return None
    return store_factory().get_active_guidance(context_id, objective_bucket)


def select_active_guidance_artifact(
    context_id: str,
    objective_bucket: str = "reasoning",
    *,
    state_store: Any | None = None,
    now: datetime | None = None,
) -> GuidanceArtifact | None:
    """Select an active, scope-compatible, nonexpired artifact from SQLite.

    A malformed row, legacy free-form guidance payload, inactive candidate, or an
    expired/foreign artifact fails closed as ``None``.  The caller must not fall
    back to state-cache text or a candidate's ``guidance_text``.
    """
    try:
        safe_context = _safe_identifier(context_id, "context_id")
        safe_bucket = _safe_identifier(objective_bucket, "objective_bucket")
        record = _active_record(safe_context, safe_bucket, state_store)
        if not isinstance(record, Mapping):
            return None
        metadata = record.get("metadata")
        if not isinstance(metadata, Mapping):
            return None
        serialized = metadata.get("guidance_artifact")
        if not isinstance(serialized, Mapping):
            return None
        artifact = validate_guidance_artifact(serialized)
        if artifact.context_id != safe_context or artifact.objective_bucket != safe_bucket:
            return None
        if str(record.get("guidance_version") or "") != artifact.artifact_id:
            return None
        if artifact.is_expired(now):
            return None
        return artifact
    except (GuidanceValidationError, TypeError, ValueError, OSError):
        return None


# Compact aliases keep the public seam discoverable for callers that use the
# generic artifact terminology in the implementation plan.
validate_artifact = validate_guidance_artifact
render_artifact = render_guidance_artifact
select_active_artifact = select_active_guidance_artifact

__all__ = [
    "GuidanceArtifact", "GuidanceValidationError", "MAX_RENDERED_CHARS", "RENDER_TARGET",
    "SCHEMA_VERSION", "render_artifact", "render_guidance_artifact", "select_active_artifact",
    "select_active_guidance_artifact", "validate_artifact", "validate_guidance_artifact",
]
