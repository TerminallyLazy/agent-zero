import asyncio
import json
from types import SimpleNamespace
import uuid

import pytest

from plugins._a0_connector.helpers import host_targets as hosts, ws_runtime as ws
from plugins._a0_connector.api.v1.host_status import HostStatus
from plugins._a0_connector.api.v1.host_task import HostTask


class Context:
    def __init__(self, parent=None):
        self.id = uuid.uuid4().hex
        self.data = {}
        self.parent = parent
        self.agent0 = SimpleNamespace(context=self)
        self.running = False
        self.messages = []

    def get_data(self, key): return self.data.get(key)
    def set_data(self, key, value): self.data[key] = value
    def get_output_data(self, key): return self.parent if key == "parent_context_id" else None
    def is_running(self): return self.running
    def get_agent(self): return self.agent0
    def communicate(self, message): self.messages.append(message)


@pytest.mark.parametrize("route,expected", [("host_status","HostStatus"),("host_task","HostTask")])
def test_dynamic_api_loader_selects_protected_handler(route, expected):
    from helpers.api import ApiHandler
    from helpers.modules import load_classes_from_file
    handler = load_classes_from_file(f"plugins/_a0_connector/api/v1/{route}.py",ApiHandler)[0]
    assert handler.__name__ == expected
    assert handler.requires_auth() and handler.requires_csrf()


@pytest.fixture
def host(monkeypatch):
    context = Context()
    contexts = {context.id: context}
    sid = uuid.uuid4().hex
    ws.register_sid(sid)
    gateway = {"version":1,"kind":"launcher","id":uuid.uuid4().hex,"host_label":"Demo Mac",
               "master_enabled":True,"state":"connected",
               "scopes":dict.fromkeys(("browser","computer_use","files","file_write","code_execution"), True)}
    ws.store_sid_launcher_gateway_metadata(sid, gateway)
    browser = {"supported":True,"enabled":True,"status":"ready","profile_path":"/private/do-not-export",
               "cdp_endpoint":"ws://secret-endpoint"}
    ws.store_sid_host_browser_metadata(sid, browser)
    ws.store_sid_computer_use_metadata(sid, {"supported":True,"enabled":True,"status":"ready"})
    ws.store_sid_remote_file_metadata(sid, {"enabled":True,"write_enabled":True})
    ws.store_sid_remote_exec_metadata(sid, {"enabled":True})
    config = {"runtime_backend":"host_required"}
    monkeypatch.setattr(hosts, "context_for", contexts.get)
    monkeypatch.setattr(hosts, "all_contexts", lambda: list(contexts.values()))
    monkeypatch.setattr(hosts, "_browser_config", lambda _: config)
    from helpers import message_queue
    monkeypatch.setattr(message_queue, "get_queue", lambda _: [])
    yield SimpleNamespace(context=context, contexts=contexts, sid=sid, gateway=gateway, browser=browser, config=config)
    for sid in list(ws.connected_sids()):
        ws.unregister_sid(sid)


def bind(host, owner="session-a", capability="browser"):
    status = hosts.host_status(host.context, owner)
    return hosts.bind(host.context, owner, status["target_id"], status["generation"], capability)


def test_projection_is_bounded_and_contains_no_connector_internals(host):
    result = hosts.host_status(host.context, "session-a")
    encoded = json.dumps(result)
    assert result["capabilities"]["browser"]["ready"]
    assert result["host_label"] == "Demo Mac"
    assert all(secret not in encoded for secret in (host.sid, "private", "secret-endpoint", "session-a"))
    assert HostStatus.requires_auth() and HostStatus.requires_csrf()
    assert HostTask.requires_auth() and HostTask.requires_csrf()


def test_target_tokens_are_bound_to_session_and_context(host):
    status = hosts.host_status(host.context, "session-a")
    with pytest.raises(hosts.HostTargetError):
        hosts.bind(host.context, "session-b", status["target_id"], status["generation"], "browser")
    other = Context(); host.contexts[other.id] = other
    with pytest.raises(hosts.HostTargetError):
        hosts.bind(other, "session-a", status["target_id"], status["generation"], "browser")


@pytest.mark.parametrize("capability", ["browser","computer_use","files","file_write","code_execution"])
def test_binding_routes_all_host_tools_to_one_connection(host, capability):
    bind(host)
    hosts.assert_dispatch(host.context.id, host.sid, capability)
    assert ws.remote_tool_sids_for_context(host.context.id) == [host.sid]
    with pytest.raises(hosts.HostTargetError):
        hosts.assert_dispatch(host.context.id, "different-host", capability)


def test_repeated_hello_and_ready_to_active_do_not_break_binding(host):
    bind(host)
    ws.store_sid_host_browser_metadata(host.sid, {**host.browser,"status":"active"})
    ws.store_sid_launcher_gateway_metadata(host.sid, host.gateway)
    assert hosts.pinned_candidate(host.context.id) == [host.sid]


def test_browser_inventory_refresh_does_not_change_selected_target(host):
    bind(host)
    ws.store_sid_host_browser_metadata(host.sid, {**host.browser,"status":"active",
        "available_browsers":[{"id":"new-debug-endpoint","label":"Chrome","status":"ready"}]})
    assert hosts.pinned_candidate(host.context.id) == [host.sid]


def test_browser_helper_initialization_does_not_change_selected_target(host):
    bind(host)
    original = hosts.host_status(host.context, "session-a")["generation"]
    ws.store_sid_host_browser_metadata(host.sid, {
        **host.browser, "content_helper_sha256": "a" * 64,
    })
    assert hosts.host_status(host.context, "session-a")["generation"] == original
    hosts.assert_dispatch(host.context.id, host.sid, "browser")


def test_revocation_and_regrant_require_explicit_review(host):
    bind(host)
    ws.store_sid_host_browser_metadata(host.sid, {**host.browser,"enabled":False})
    ws.store_sid_host_browser_metadata(host.sid, host.browser)
    assert hosts.pinned_candidate(host.context.id) == []
    with pytest.raises(hosts.HostTargetError): hosts.assert_dispatch(host.context.id,host.sid,"browser")
    bind(host)
    assert hosts.pinned_candidate(host.context.id) == [host.sid]


def test_reconnect_even_with_same_gateway_id_does_not_resume(host):
    bind(host)
    ws.unregister_sid(host.sid)
    ws.register_sid(host.sid)
    ws.store_sid_launcher_gateway_metadata(host.sid, host.gateway)
    ws.store_sid_host_browser_metadata(host.sid, host.browser)
    assert ws.select_host_browser_target_sid(host.context.id) is None


def test_process_restart_preserves_restriction_but_invalidates_generation(host, monkeypatch):
    bind(host)
    monkeypatch.setattr(hosts,"_secret",b"a different server boot")
    assert hosts.pinned_candidate(host.context.id) == []
    assert hosts.host_status(host.context,"session-a")["bound"]


def test_competing_cli_cannot_steal_a_bound_chat(host):
    bind(host)
    cli = uuid.uuid4().hex
    ws.register_sid(cli); ws.subscribe_sid_to_context(cli,host.context.id)
    ws.store_sid_host_browser_metadata(cli,host.browser)
    assert hosts.host_status(host.context,"session-a")["state"] == "ambiguous"
    assert ws.select_host_browser_target_sid(host.context.id) is None


def test_chat_observer_reconnect_does_not_change_host_target(host):
    bind(host)
    original = hosts.host_status(host.context, "session-a")["generation"]
    observer = uuid.uuid4().hex
    ws.register_sid(observer)
    ws.subscribe_sid_to_context(observer, host.context.id)
    assert hosts.host_status(host.context, "session-a")["generation"] == original
    hosts.assert_dispatch(host.context.id, host.sid, "browser")
    ws.unregister_sid(observer)
    assert hosts.host_status(host.context, "session-a")["generation"] == original
    hosts.assert_dispatch(host.context.id, host.sid, "browser")


def test_chat_observer_advertising_host_tools_invalidates_target(host):
    observer = uuid.uuid4().hex
    ws.register_sid(observer)
    ws.subscribe_sid_to_context(observer, host.context.id)
    bind(host)
    ws.store_sid_host_browser_metadata(observer, host.browser)
    assert hosts.host_status(host.context, "session-a")["state"] == "ambiguous"
    assert hosts.pinned_candidate(host.context.id) == []


def test_distinct_gateways_disable_targeting(host):
    other = uuid.uuid4().hex
    ws.register_sid(other)
    ws.store_sid_launcher_gateway_metadata(other,{**host.gateway,"id":other})
    result = hosts.host_status(host.context,"session-a")
    assert result["state"] == "ambiguous" and result["generation"] is None


def test_subordinate_inherits_root_binding_and_revocation(host):
    bind(host)
    child = Context(parent=host.context.id); host.contexts[child.id] = child
    assert ws.select_computer_use_target_sid(child.id) == host.sid
    host.config["runtime_backend"] = "container"
    assert ws.select_computer_use_target_sid(child.id) is None
    with pytest.raises(hosts.HostTargetError): hosts.assert_dispatch(child.id,host.sid,"browser")


def test_unbound_chat_keeps_existing_routing(host):
    cli = uuid.uuid4().hex
    ws.register_sid(cli); ws.subscribe_sid_to_context(cli,host.context.id)
    ws.store_sid_host_browser_metadata(cli,host.browser)
    assert ws.select_host_browser_target_sid(host.context.id) == cli


def test_configuration_and_permission_states_do_not_claim_readiness(host):
    host.config["runtime_backend"] = "container"
    ws.store_sid_computer_use_metadata(host.sid,{"supported":True,"enabled":True,"status":"approval required"})
    caps = hosts.host_status(host.context,"session-a")["capabilities"]
    assert caps["browser"] == {"ready":False,"state":"container"}
    assert caps["computer_use"] == {"ready":False,"state":"needs_attention"}


@pytest.mark.parametrize("status", ["interactive", "persistent", "allow"])
def test_computer_use_advertised_trust_modes_are_eligible(host, status):
    ws.store_sid_computer_use_metadata(host.sid,{"supported":True,"enabled":True,"status":status})
    assert hosts.host_status(host.context,"session-a")["capabilities"]["computer_use"]["ready"]
    bind(host, capability="computer_use")
    hosts.assert_dispatch(host.context.id,host.sid,"computer_use")


def test_computer_session_start_stop_does_not_invalidate_permission(host):
    metadata={"supported":True,"enabled":True,"trust_mode":"persistent","status":"persistent"}
    ws.store_sid_computer_use_metadata(host.sid,metadata)
    bind(host,capability="computer_use")
    for status in ("active","persistent"):
        ws.store_sid_computer_use_metadata(host.sid,{**metadata,"status":status})
        hosts.assert_dispatch(host.context.id,host.sid,"computer_use")
    ws.store_sid_computer_use_metadata(host.sid,{**metadata,"trust_mode":"interactive"})
    assert hosts.pinned_candidate(host.context.id) == []


def test_cannot_replace_binding_under_active_work(host):
    bind(host)
    host.context.running = True
    ws.store_sid_host_browser_metadata(host.sid,{**host.browser,"browser_id":"new-browser"})
    with pytest.raises(hosts.HostTargetError): bind(host)


def test_active_descendant_prevents_root_retargeting(host):
    bind(host)
    child = Context(parent=host.context.id); host.contexts[child.id] = child
    child.running = True
    ws.store_sid_host_browser_metadata(host.sid,{**host.browser,"browser_id":"new-browser"})
    with pytest.raises(hosts.HostTargetError): bind(host)
    child.running = False
    bind(host)
    assert ws.select_computer_use_target_sid(child.id) == host.sid


def test_queued_descendant_prevents_root_retargeting(host, monkeypatch):
    from helpers import message_queue
    child = Context(parent=host.context.id); host.contexts[child.id] = child
    monkeypatch.setattr(message_queue,"get_queue",lambda context: ["pending"] if context == child else [])
    with pytest.raises(hosts.HostTargetError): bind(host)


def test_orphan_cannot_bypass_inherited_restriction(host):
    child = Context(parent="missing-parent"); host.contexts[child.id] = child
    assert ws.select_computer_use_target_sid(child.id) is None


def test_host_task_persists_before_submission_and_returns_matching_receipt(host, monkeypatch):
    from plugins._a0_connector.api.v1 import host_task
    events = []
    async def extensions(*args, **kwargs): pass
    monkeypatch.setattr(host_task.host_status,"session_owner",lambda:"session-a")
    monkeypatch.setattr(host_task.extension,"call_extensions_async",extensions)
    monkeypatch.setattr(host_task.persist_chat,"save_tmp_chat",lambda context: events.append("persist"))
    monkeypatch.setattr(host_task.message_queue,"log_user_message",lambda *args: events.append("log"))
    status = hosts.host_status(host.context,"session-a")
    payload = {"context":host.context.id,"text":"Inspect demo page","message_id":"demo-message",
               "target_id":status["target_id"],"generation":status["generation"],"capability":"browser","queued":"false"}
    result = asyncio.run(HostTask.__new__(HostTask).process(payload,None))
    assert result == {"ok":True,"context":host.context.id,"message_id":"demo-message","queued":False}
    assert events == ["persist","log"] and len(host.context.messages) == 1
    monkeypatch.setattr(host_task.persist_chat,"save_tmp_chat",lambda _: (_ for _ in ()).throw(OSError()))
    failed = asyncio.run(HostTask.__new__(HostTask).process(payload,None))
    assert failed.status_code == 500 and len(host.context.messages) == 1
