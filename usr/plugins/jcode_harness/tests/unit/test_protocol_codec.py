"""Unit tests for the jcode_harness wire-protocol codec.

These tests pin the JSON shape of `Request` and `ServerEvent` against the
authoritative Rust source at `jcode/crates/jcode-protocol/src/lib.rs` and
verify forward-compat behaviour for unknown event types.
"""

from __future__ import annotations

import json

import pytest

from usr.plugins.jcode_harness.helpers.protocol import (
    BackgroundTool,
    Cancel,
    CancelSoftInterrupts,
    CommMessage,
    CommRead,
    CommShare,
    Compaction,
    Done,
    GetHistory,
    History,
    MemoryInjected,
    Message,
    MessageEnd,
    Ping,
    Pong,
    ResumeSession,
    Reloading,
    SessionId,
    SoftInterrupt,
    StdinResponse,
    Subscribe,
    TextDelta,
    TokenUsage,
    ToolDone,
    ToolStart,
    UnknownEvent,
    decode_event,
    encode_request,
)


# ---------- Request encoding ----------


def test_subscribe_round_trip():
    req = Subscribe(
        id=1,
        working_dir="/tmp/x",
        target_session_id=None,
        client_instance_id="abc",
        allow_session_takeover=False,
    )
    line = encode_request(req)
    assert b'"type":"subscribe"' in line
    assert b'"working_dir":"/tmp/x"' in line
    assert b'"client_instance_id":"abc"' in line
    assert b'"allow_session_takeover":false' in line
    assert line.endswith(b"\n")


def test_message_round_trip():
    req = Message(id=1, content="hello", images=[])
    line = encode_request(req)
    assert b'"type":"message"' in line
    assert b'"content":"hello"' in line
    assert b'"id":1' in line


def test_soft_interrupt_round_trip():
    req = SoftInterrupt(id=2, content="redirect", urgent=False)
    line = encode_request(req)
    assert b'"type":"soft_interrupt"' in line
    assert b'"content":"redirect"' in line
    assert b'"urgent":false' in line


def test_cancel_round_trip():
    req = Cancel(id=7)
    line = encode_request(req)
    obj = json.loads(line)
    assert obj == {"type": "cancel", "id": 7}


def test_cancel_soft_interrupts_round_trip():
    req = CancelSoftInterrupts(id=8)
    obj = json.loads(encode_request(req))
    assert obj == {"type": "cancel_soft_interrupts", "id": 8}


def test_background_tool_round_trip():
    # Per Rust source: BackgroundTool { id: u64 }.
    req = BackgroundTool(id=9)
    obj = json.loads(encode_request(req))
    assert obj == {"type": "background_tool", "id": 9}


def test_resume_session_round_trip():
    req = ResumeSession(
        id=3,
        session_id="fox",
        client_instance_id="abc",
        client_has_local_history=True,
        allow_session_takeover=False,
    )
    line = encode_request(req)
    assert b'"type":"resume_session"' in line
    assert b'"session_id":"fox"' in line
    assert b'"client_instance_id":"abc"' in line
    assert b'"client_has_local_history":true' in line


def test_get_history_round_trip():
    obj = json.loads(encode_request(GetHistory(id=4)))
    assert obj == {"type": "get_history", "id": 4}


def test_ping_round_trip():
    obj = json.loads(encode_request(Ping(id=5)))
    assert obj == {"type": "ping", "id": 5}


def test_stdin_response_round_trip():
    req = StdinResponse(id=6, request_id="r-1", input="secret")
    obj = json.loads(encode_request(req))
    assert obj == {
        "type": "stdin_response",
        "id": 6,
        "request_id": "r-1",
        "input": "secret",
    }


def test_comm_message_round_trip():
    # Per Rust: comm_message has from_session/message, optional to_session/channel.
    req = CommMessage(
        id=10,
        from_session="fox",
        message="ack",
        to_session="bear",
        channel=None,
    )
    line = encode_request(req)
    assert b'"type":"comm_message"' in line
    assert b'"from_session":"fox"' in line
    assert b'"message":"ack"' in line
    assert b'"to_session":"bear"' in line


def test_comm_share_round_trip():
    req = CommShare(id=11, session_id="fox", key="ctx", value="hi", append=False)
    obj = json.loads(encode_request(req))
    assert obj["type"] == "comm_share"
    assert obj["session_id"] == "fox"
    assert obj["key"] == "ctx"
    assert obj["value"] == "hi"


def test_comm_read_round_trip():
    req = CommRead(id=12, session_id="fox", key="ctx")
    obj = json.loads(encode_request(req))
    assert obj["type"] == "comm_read"
    assert obj["session_id"] == "fox"
    assert obj["key"] == "ctx"


def test_encode_appends_newline():
    line = encode_request(Ping(id=1))
    assert line.endswith(b"\n")
    # exactly one trailing newline
    assert not line.endswith(b"\n\n")


def test_encode_compact_no_extra_whitespace():
    line = encode_request(Ping(id=1)).rstrip(b"\n")
    # no spaces between separators
    assert b": " not in line
    assert b", " not in line


# ---------- ServerEvent decoding ----------


def test_text_delta_decode():
    line = b'{"type":"text_delta","text":"hello"}\n'
    ev = decode_event(line)
    assert isinstance(ev, TextDelta)
    assert ev.type == "text_delta"
    assert ev.text == "hello"


def test_session_id_decode():
    # Rust discriminator is "session", not "session_id".
    line = b'{"type":"session","session_id":"fox"}\n'
    ev = decode_event(line)
    assert isinstance(ev, SessionId)
    assert ev.session_id == "fox"


def test_tool_start_decode():
    line = b'{"type":"tool_start","id":"t1","name":"shell"}\n'
    ev = decode_event(line)
    assert isinstance(ev, ToolStart)
    assert ev.id == "t1"
    assert ev.name == "shell"


def test_tool_done_with_error_decode():
    line = (
        b'{"type":"tool_done","id":"t1","name":"shell",'
        b'"output":"","error":"boom"}\n'
    )
    ev = decode_event(line)
    assert isinstance(ev, ToolDone)
    assert ev.error == "boom"
    assert ev.output == ""


def test_tool_done_without_error_decode():
    line = (
        b'{"type":"tool_done","id":"t1","name":"shell","output":"ok"}\n'
    )
    ev = decode_event(line)
    assert isinstance(ev, ToolDone)
    assert ev.error is None
    assert ev.output == "ok"


def test_message_end_decode():
    ev = decode_event(b'{"type":"message_end"}\n')
    assert isinstance(ev, MessageEnd)


def test_done_decode():
    ev = decode_event(b'{"type":"done","id":42}\n')
    assert isinstance(ev, Done)
    assert ev.id == 42


def test_pong_decode():
    ev = decode_event(b'{"type":"pong","id":7}\n')
    assert isinstance(ev, Pong)
    assert ev.id == 7


def test_token_usage_decode():
    # Rust discriminator is "tokens".
    line = (
        b'{"type":"tokens","input":12,"output":34,'
        b'"cache_read_input":5,"cache_creation_input":1}\n'
    )
    ev = decode_event(line)
    assert isinstance(ev, TokenUsage)
    assert ev.input == 12
    assert ev.output == 34
    assert ev.cache_read_input == 5
    assert ev.cache_creation_input == 1


def test_memory_injected_decode():
    line = (
        b'{"type":"memory_injected","count":2,"prompt":"x",'
        b'"prompt_chars":1,"computed_age_ms":5}\n'
    )
    ev = decode_event(line)
    assert isinstance(ev, MemoryInjected)
    assert ev.count == 2
    assert ev.prompt == "x"


def test_compaction_with_partial_fields_decode():
    # Rust marks all numeric fields as optional, only `trigger` is required.
    line = (
        b'{"type":"compaction","trigger":"background",'
        b'"pre_tokens":1000,"post_tokens":200,"messages_compacted":4}\n'
    )
    ev = decode_event(line)
    assert isinstance(ev, Compaction)
    assert ev.trigger == "background"
    assert ev.pre_tokens == 1000
    assert ev.post_tokens == 200
    assert ev.messages_dropped is None


def test_reloading_decode_with_socket():
    line = b'{"type":"reloading","new_socket":"/tmp/jcode-new.sock"}\n'
    ev = decode_event(line)
    assert isinstance(ev, Reloading)
    assert ev.new_socket == "/tmp/jcode-new.sock"


def test_reloading_decode_without_socket():
    # Rust skip_serializing_if drops new_socket when None.
    ev = decode_event(b'{"type":"reloading"}\n')
    assert isinstance(ev, Reloading)
    assert ev.new_socket is None


def test_history_decode_minimal():
    line = (
        b'{"type":"history","id":1,"session_id":"fox","messages":[]}\n'
    )
    ev = decode_event(line)
    assert isinstance(ev, History)
    assert ev.id == 1
    assert ev.session_id == "fox"
    assert ev.messages == []


def test_unknown_event_passes_through():
    line = b'{"type":"future_variant","x":42,"y":"z"}\n'
    ev = decode_event(line)
    assert isinstance(ev, UnknownEvent)
    assert ev.raw["type"] == "future_variant"
    assert ev.raw["x"] == 42
    assert ev.raw["y"] == "z"


def test_decode_extra_fields_ignored():
    # Forward-compat: jcode adds a new field to text_delta. Codec must not crash.
    line = b'{"type":"text_delta","text":"hi","new_field":123}\n'
    ev = decode_event(line)
    assert isinstance(ev, TextDelta)
    assert ev.text == "hi"


def test_decode_malformed_json_raises():
    with pytest.raises(json.JSONDecodeError):
        decode_event(b"{not valid json}\n")
