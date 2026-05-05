"""Pure-Python codec for the jcode wire protocol.

Mirrors the Rust enums declared in `jcode/crates/jcode-protocol/src/lib.rs`
(`Request` and `ServerEvent`). NDJSON over Unix socket: every line is one
JSON object whose ``type`` field is the variant discriminator.

Discrepancies between the high-level plan stub and the Rust source are
resolved in favour of the Rust source: every Request variant carries the
required ``id`` field, ServerEvent discriminators ``session`` and ``tokens``
match Rust (not the plan's ``session_id`` / ``token_usage``), the various
``Comm*`` variants follow the real Rust shape, and forward-compat unknown
events fall through to :class:`UnknownEvent`.

This module is import-only; it does not touch the Unix socket or A0 runtime.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, fields
from typing import Any, Literal, Union


# ---------------------------------------------------------------------------
# Request variants
#
# Each Request variant carries an `id: int` (Rust `u64`). Optional fields use
# `None` defaults; the encoder simply asdict's the whole dataclass — the jcode
# server uses `#[serde(default)]` on optional fields, so transmitting JSON null
# for fields the Rust enum marks `Option<T>` is safe and gets normalised to
# None on decode.
# ---------------------------------------------------------------------------


@dataclass
class Subscribe:
    id: int
    working_dir: str | None = None
    target_session_id: str | None = None
    client_instance_id: str | None = None
    client_has_local_history: bool = False
    allow_session_takeover: bool = False
    selfdev: bool | None = None
    type: Literal["subscribe"] = "subscribe"


@dataclass
class Message:
    id: int
    content: str
    images: list[tuple[str, str]] = field(default_factory=list)
    system_reminder: str | None = None
    type: Literal["message"] = "message"


@dataclass
class Cancel:
    id: int
    type: Literal["cancel"] = "cancel"


@dataclass
class BackgroundTool:
    id: int
    type: Literal["background_tool"] = "background_tool"


@dataclass
class SoftInterrupt:
    id: int
    content: str
    urgent: bool = False
    type: Literal["soft_interrupt"] = "soft_interrupt"


@dataclass
class CancelSoftInterrupts:
    id: int
    type: Literal["cancel_soft_interrupts"] = "cancel_soft_interrupts"


@dataclass
class Ping:
    id: int
    type: Literal["ping"] = "ping"


@dataclass
class GetHistory:
    id: int
    type: Literal["get_history"] = "get_history"


@dataclass
class ResumeSession:
    id: int
    session_id: str
    client_instance_id: str | None = None
    client_has_local_history: bool = False
    allow_session_takeover: bool = False
    type: Literal["resume_session"] = "resume_session"


@dataclass
class StdinResponse:
    id: int
    request_id: str
    input: str
    type: Literal["stdin_response"] = "stdin_response"


# --- Comm* (swarm) requests, shapes from Rust source ---


@dataclass
class CommMessage:
    id: int
    from_session: str
    message: str
    to_session: str | None = None
    channel: str | None = None
    delivery: str | None = None  # "notify" | "interrupt" | "wake"
    wake: bool | None = None
    type: Literal["comm_message"] = "comm_message"


@dataclass
class CommShare:
    id: int
    session_id: str
    key: str
    value: str
    append: bool = False
    type: Literal["comm_share"] = "comm_share"


@dataclass
class CommRead:
    id: int
    session_id: str
    key: str | None = None
    type: Literal["comm_read"] = "comm_read"


# Discriminated union of every Request variant we generate from the harness.
# Other Request variants exist in Rust (Reload, Split, Compact, agent_*, …) but
# are not emitted by the harness in MVP scope, so we keep the surface small.
Request = Union[
    Subscribe,
    Message,
    Cancel,
    BackgroundTool,
    SoftInterrupt,
    CancelSoftInterrupts,
    Ping,
    GetHistory,
    ResumeSession,
    StdinResponse,
    CommMessage,
    CommShare,
    CommRead,
]


def _request_to_dict(req: Any) -> dict[str, Any]:
    """Serialize a Request dataclass to a plain dict.

    We don't use ``dataclasses.asdict`` because it recursively converts tuples
    in ``Message.images`` into lists in a way that's already what JSON needs —
    but the explicit form documents intent and is trivially auditable.
    """
    out: dict[str, Any] = {}
    for f in fields(req):
        out[f.name] = getattr(req, f.name)
    return out


def encode_request(req: Any) -> bytes:
    """Encode a Request dataclass as a single NDJSON line (with trailing ``\\n``)."""
    obj = _request_to_dict(req)
    return (json.dumps(obj, separators=(",", ":")) + "\n").encode("utf-8")


# ---------------------------------------------------------------------------
# ServerEvent variants
# ---------------------------------------------------------------------------


@dataclass
class TextDelta:
    text: str
    type: Literal["text_delta"] = "text_delta"


@dataclass
class ToolStart:
    id: str
    name: str
    type: Literal["tool_start"] = "tool_start"


@dataclass
class ToolInput:
    delta: str
    type: Literal["tool_input"] = "tool_input"


@dataclass
class ToolExec:
    id: str
    name: str
    type: Literal["tool_exec"] = "tool_exec"


@dataclass
class ToolDone:
    id: str
    name: str
    output: str = ""
    error: str | None = None
    type: Literal["tool_done"] = "tool_done"


@dataclass
class MessageEnd:
    type: Literal["message_end"] = "message_end"


@dataclass
class Done:
    id: int
    type: Literal["done"] = "done"


@dataclass
class SessionId:
    """Rust discriminator is ``"session"`` (not ``"session_id"``)."""

    session_id: str
    type: Literal["session"] = "session"


@dataclass
class History:
    id: int
    session_id: str
    messages: list[dict] = field(default_factory=list)
    images: list[dict] = field(default_factory=list)
    provider_name: str | None = None
    provider_model: str | None = None
    available_models: list[str] = field(default_factory=list)
    mcp_servers: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    total_tokens: tuple[int, int] | list[int] | None = None
    all_sessions: list[str] = field(default_factory=list)
    server_version: str | None = None
    server_name: str | None = None
    server_icon: str | None = None
    activity: dict | None = None
    side_panel: dict | None = None
    type: Literal["history"] = "history"


@dataclass
class TokenUsage:
    """Rust discriminator is ``"tokens"`` (not ``"token_usage"``)."""

    input: int
    output: int
    cache_read_input: int | None = None
    cache_creation_input: int | None = None
    type: Literal["tokens"] = "tokens"


@dataclass
class MemoryInjected:
    count: int = 0
    prompt: str = ""
    display_prompt: str | None = None
    prompt_chars: int = 0
    computed_age_ms: int = 0
    type: Literal["memory_injected"] = "memory_injected"


@dataclass
class Compaction:
    trigger: str
    pre_tokens: int | None = None
    post_tokens: int | None = None
    tokens_saved: int | None = None
    duration_ms: int | None = None
    messages_dropped: int | None = None
    messages_compacted: int | None = None
    summary_chars: int | None = None
    active_messages: int | None = None
    type: Literal["compaction"] = "compaction"


@dataclass
class Reloading:
    new_socket: str | None = None
    type: Literal["reloading"] = "reloading"


@dataclass
class Interrupted:
    type: Literal["interrupted"] = "interrupted"


@dataclass
class StdinRequest:
    request_id: str
    prompt: str
    tool_call_id: str
    is_password: bool = False
    type: Literal["stdin_request"] = "stdin_request"


@dataclass
class SoftInterruptInjected:
    content: str
    point: str  # "A" | "B" | "C" | "D"
    display_role: str | None = None
    tools_skipped: int | None = None
    type: Literal["soft_interrupt_injected"] = "soft_interrupt_injected"


@dataclass
class SwarmStatus:
    members: list[dict]
    type: Literal["swarm_status"] = "swarm_status"


@dataclass
class CommReceived:
    """Incoming comm_message event delivered to the subscriber."""

    # We keep the full Rust shape so consumers can dispatch by from_session,
    # channel, etc. without rummaging through `raw`.
    id: int = 0
    from_session: str = ""
    message: str = ""
    to_session: str | None = None
    channel: str | None = None
    delivery: str | None = None
    wake: bool | None = None
    type: Literal["comm_message"] = "comm_message"


@dataclass
class GeneratedImage:
    id: str
    path: str
    output_format: str = ""
    metadata_path: str | None = None
    revised_prompt: str | None = None
    type: Literal["generated_image"] = "generated_image"


@dataclass
class SidePanelUpdate:
    """Rust discriminator is ``"side_panel_state"`` and the payload key is
    ``snapshot``. We keep the type literal aligned with Rust."""

    snapshot: dict
    type: Literal["side_panel_state"] = "side_panel_state"


@dataclass
class Pong:
    id: int
    type: Literal["pong"] = "pong"


@dataclass
class UnknownEvent:
    """Forward-compat fallback for any event type the codec does not recognize."""

    raw: dict
    type: Literal["unknown"] = "unknown"


# Server events that the harness consumes during MVP. Other Rust variants
# (e.g. ack, error, batch_progress, mcp_status, comm_*_response, …) fall
# through to UnknownEvent until a tool/handler explicitly needs them.
ServerEvent = Union[
    TextDelta,
    ToolStart,
    ToolInput,
    ToolExec,
    ToolDone,
    MessageEnd,
    Done,
    SessionId,
    History,
    TokenUsage,
    MemoryInjected,
    Compaction,
    Reloading,
    Interrupted,
    StdinRequest,
    SoftInterruptInjected,
    SwarmStatus,
    CommReceived,
    GeneratedImage,
    SidePanelUpdate,
    Pong,
    UnknownEvent,
]


_EVENT_REGISTRY: dict[str, type] = {
    "text_delta": TextDelta,
    "tool_start": ToolStart,
    "tool_input": ToolInput,
    "tool_exec": ToolExec,
    "tool_done": ToolDone,
    "message_end": MessageEnd,
    "done": Done,
    "session": SessionId,
    "history": History,
    "tokens": TokenUsage,
    "memory_injected": MemoryInjected,
    "compaction": Compaction,
    "reloading": Reloading,
    "interrupted": Interrupted,
    "stdin_request": StdinRequest,
    "soft_interrupt_injected": SoftInterruptInjected,
    "swarm_status": SwarmStatus,
    "comm_message": CommReceived,
    "generated_image": GeneratedImage,
    "side_panel_state": SidePanelUpdate,
    "pong": Pong,
}


def decode_event(line: bytes | str) -> ServerEvent:
    """Decode a single NDJSON line into a typed ServerEvent dataclass.

    Unknown discriminators or malformed-shape events surface as
    :class:`UnknownEvent` so a future jcode release can add fields/variants
    without breaking the harness.
    """
    obj = json.loads(line)
    if not isinstance(obj, dict):
        return UnknownEvent(raw={"_raw": obj})
    cls = _EVENT_REGISTRY.get(obj.get("type"))
    if cls is None:
        return UnknownEvent(raw=obj)
    field_names = {f.name for f in fields(cls)}
    kwargs = {k: v for k, v in obj.items() if k in field_names and k != "type"}
    try:
        return cls(**kwargs)
    except TypeError:
        # Required field missing or type mismatch: fall back so we don't crash
        # the event loop on a malformed/extended event.
        return UnknownEvent(raw=obj)
