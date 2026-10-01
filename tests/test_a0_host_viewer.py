import asyncio
import json
import sys
from types import SimpleNamespace

import pytest
from plugins._a0_connector.helpers import host_control as control


class Context:
    def __init__(self, identity="chat", parent=None):
        self.id = identity
        self.parent = parent
        self.paused = True
    def get_output_data(self, key):
        return self.parent if key == "parent_context_id" else None


@pytest.fixture
def host(tmp_path, monkeypatch):
    context = Context()
    gateway = {"gateway_id": "host", "master_enabled": True, "host_label": "Fixture Mac",
               "scopes": {"browser": True, "computer_use": True}}
    monkeypatch.setattr(control, "_directory", tmp_path)
    monkeypatch.setattr(control, "_records", {})
    monkeypatch.setattr(control, "_remote", {"sid": {"version": 1, "phase": "watching", "epoch": "a" * 32}})
    monkeypatch.setattr(control, "_watchers", {})
    monkeypatch.setattr(control.ws, "host_routing_snapshot", lambda _: {"sid": "sid", "gateway": gateway, "ambiguous": False})
    monkeypatch.setattr(control.ws, "launcher_gateway_metadata_for_sid", lambda _: gateway)
    monkeypatch.setattr(control.host_targets, "assert_dispatch", lambda *args: None)
    monkeypatch.setattr(control.host_targets, "inherited_binding", lambda _: {"context_id": context.id})
    calls = []
    async def send(sid, payload):
        calls.append(dict(payload))
        if payload["command"] in {"acquire", "heartbeat"}:
            return {"phase": "human", "epoch": "b" * 32}
        if payload["command"] == "release":
            return {"phase": "watching", "epoch": "c" * 32}
        return {}
    monkeypatch.setattr(control, "_send", send)
    return context, calls


def request(command, **extra):
    return {"command": command, "viewer": "v" * 32, "source": "browser", "request_id": "r" * 32, **extra}


def test_final_fence_closes_before_host_acknowledges(host, monkeypatch):
    context, calls = host
    async def send(sid, payload):
        with pytest.raises(ValueError, match="holds"):
            control.fence("competing-chat", sid, {})
        assert control.agent_state(context)[0]
        return {"phase": "human"}
    monkeypatch.setattr(control, "_send", send)
    result = asyncio.run(control.command(context, "owner", request("acquire")))
    assert result["phase"] == "human" and result["mine"]
    assert context.paused  # pre-existing Pause is untouched


def test_internal_release_commands_cannot_bypass_handoff(host):
    context, calls = host
    for command in ("release", "prepare_return", "evaluate", "close"):
        with pytest.raises(ValueError, match="Unknown"):
            asyncio.run(control.command(context, "owner", request(command)))
    assert not calls


def test_receipts_deduplicate_and_never_persist_text(host):
    context, calls = host
    asyncio.run(control.command(context, "owner", request("acquire")))
    with pytest.raises(ValueError, match="already submitted"):
        asyncio.run(control.command(context, "owner", request("acquire")))
    asyncio.run(control.command(context, "owner", request("input",request_id="s"*32,sequence=1,input={"kind":"text","text":"SENSITIVE_FIXTURE"})))
    saved = next(control._directory.glob("*.json")).read_text()
    assert "SENSITIVE_FIXTURE" not in saved and '"acknowledged"' in saved
    assert len(calls) == 2


def test_uncertain_acquisition_and_restart_keep_agent_held(host, monkeypatch):
    context, _ = host
    async def lost(*args):
        raise TimeoutError()
    monkeypatch.setattr(control, "_send", lost)
    with pytest.raises(TimeoutError):
        asyncio.run(control.command(context, "owner", request("acquire")))
    monkeypatch.setattr(control, "_records", {})
    assert control.agent_state(context)[0]
    assert control.projection(context,"owner","v"*32)["recoverable"]
    with pytest.raises(ValueError):
        control.fence("other", "sid", {})


def test_descendants_hold_and_handback_requires_observation(host, monkeypatch):
    context, calls = host
    child = Context("child", parent=context.id)
    monkeypatch.setattr(control.host_targets,"context_for",lambda id: context if id == context.id else None)
    asyncio.run(control.command(context,"owner",request("acquire")))
    assert control.agent_state(child)[0]
    asyncio.run(control.command(context,"owner",request("return",request_id="t"*32)))
    assert [c["command"] for c in calls] == ["acquire","prepare_return","release"]
    assert not control.agent_state(child)[0] and context.paused


def test_another_viewer_cannot_send_input(host):
    context, calls = host
    asyncio.run(control.command(context,"owner",request("acquire")))
    with pytest.raises(ValueError,match="Another viewer"):
        asyncio.run(control.command(context,"owner",request("input",viewer="other"*6+"xx")))
    assert len(calls) == 1


def test_agent_replanning_discards_prepared_actions(host, monkeypatch):
    context, _ = host
    class Intervention(Exception): pass
    monkeypatch.setitem(sys.modules,"agent",SimpleNamespace(UserMessage=lambda **kw: kw))
    monkeypatch.setitem(sys.modules,"helpers.errors",SimpleNamespace(InterventionException=Intervention))
    data, messages = {}, []
    agent = SimpleNamespace(context=context,get_data=data.get,set_data=lambda k,v:data.update({k:v}),
                            _clear_responses_pending_state=lambda:messages.append("cleared"),
                            hist_add_user_message=lambda *a,**kw:messages.append("fresh-observation"))
    asyncio.run(control.gate_agent(agent))
    asyncio.run(control.command(context,"owner",request("acquire")))
    asyncio.run(control.command(context,"owner",request("return",request_id="t"*32)))
    with pytest.raises(Intervention):
        asyncio.run(control.gate_agent(agent))
    asyncio.run(control.gate_agent(agent))
    assert messages == ["cleared", "fresh-observation"]


def test_operation_prepared_before_takeover_cannot_adopt_new_epoch(host):
    payload = {"host_epoch":"old"}
    with pytest.raises(ValueError, match="prepared before"):
        control.fence("chat","sid",payload)
    assert payload["host_epoch"] == "old"
