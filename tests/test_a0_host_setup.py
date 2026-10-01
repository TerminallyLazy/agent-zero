import json
import uuid

import pytest

from plugins._a0_connector.helpers import host_setup as setup
from plugins._a0_connector.api.v1.host_setup import HostSetup


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(setup, "DATABASE", tmp_path / "setup.sqlite3")


def create(owner="owner", capabilities=None):
    return setup.continuation(owner, "create", {"request_id": str(uuid.uuid4()), "capabilities": capabilities or ["browser"]})


def claim(request, owner="owner", **overrides):
    return setup.continuation(owner, "claim", dict(code=request["code"], host_id="test-host",
        host_label="Demo Mac", claim_id="a" * 32, **overrides))


def test_api_is_authenticated_and_csrf_protected():
    assert HostSetup.requires_auth() and HostSetup.requires_csrf()


def test_recent_verification_requires_current_permission_and_has_expiry(monkeypatch):
    import time
    gateway = {"id":"host", "master_enabled":True, "scopes":{"browser":True}, "status":{
        "browser":{"status":"ready","enabled":True,"supported":True},
        "setup_verifications":{"browser":{"verified":True,"checked_at":time.time(),"evidence":["test_page_input","fresh_capture"]}}}}
    monkeypatch.setattr(setup.ws,"launcher_gateway_status",lambda:{"connected":True,"gateway":gateway})
    from plugins._browser.helpers import config
    monkeypatch.setattr(config,"get_browser_config",lambda:{})
    assert setup.snapshot()["steps"][1]["reason"] == "verified"
    gateway["status"]["setup_verifications"]["browser"]["checked_at"] -= 301
    assert setup.snapshot()["steps"][1]["reason"] == "ready_to_test"
    gateway["scopes"]["browser"] = False
    assert setup.snapshot()["steps"][1]["reason"] == "access_off"


def test_server_identity_survives_new_database_connections():
    assert setup.identity() == setup.identity()


def test_continuation_lifecycle_never_changes_host_scopes(monkeypatch):
    monkeypatch.setattr(setup.ws, "launcher_gateway_status", lambda: pytest.fail("Continuation touched host state"))
    request = create()
    assert request["state"] == "waiting"
    result = claim(request)
    assert result["state"] == "claimed" and result["capabilities"] == ["browser"]
    result = setup.continuation("owner", "confirm", {"request_id":request["request_id"]})
    assert result["state"] == "confirmed" and result["host_label"] == "Demo Mac"


def test_create_idempotence_and_intent_binding():
    request = create()
    retry = setup.continuation("owner", "create", {"request_id":request["request_id"], "capabilities":["browser"]})
    assert retry == request
    with pytest.raises(ValueError):
        setup.continuation("owner", "create", {"request_id":request["request_id"], "capabilities":["computer_use"]})


def test_code_cannot_cross_owner_or_be_stolen_after_claim():
    request = create()
    with pytest.raises(ValueError): claim(request, owner="other")
    claim(request)
    with pytest.raises(ValueError):
        setup.continuation("owner", "claim", {"code":request["code"], "host_id":"other-host", "claim_id":"b"*32})
    with pytest.raises(ValueError): setup.continuation("other", "read", {"request_id":request["request_id"]})


def test_expiry_and_cancellation(monkeypatch):
    request = create()
    setup.continuation("owner", "cancel", {"request_id":request["request_id"]})
    with pytest.raises(ValueError): claim(request)
    with pytest.raises(ValueError): setup.continuation("owner", "confirm", {"request_id":request["request_id"]})
    monkeypatch.setattr(setup.time, "time", lambda:request["expires_at"]+1)
    with pytest.raises(ValueError): setup.continuation("owner", "read", {"request_id":request["request_id"]})


def test_rejected_codes_are_rate_limited():
    for _ in range(10):
        with pytest.raises(ValueError): claim({"code":"INVALID"})
    with pytest.raises(ValueError, match="Too many"):
        claim({"code":"INVALID"})


@pytest.mark.parametrize("owner,capabilities", [("",["browser"]),("owner",["files"]),("owner",[])])
def test_invalid_creation(owner, capabilities):
    with pytest.raises(ValueError): setup.continuation(owner,"create",{"request_id":str(uuid.uuid4()),"capabilities":capabilities})


def test_projection_has_specific_permission_steps_and_no_private_fields(monkeypatch):
    gateway = {"id":"test-host", "host_label":"Demo Mac", "master_enabled":True,
        "scopes":{"browser":True,"computer_use":True}, "status":{
            "browser":{"status":"ready","supported":True,"profile_path":"secret-path","cdp_endpoint":"secret-endpoint"},
            "computer_use":{"backend_family":"macos","setup":{"state":"screen_recording_required"}}}}
    monkeypatch.setattr(setup.ws,"launcher_gateway_status",lambda:{"connected":True,"gateway":gateway})
    from plugins._browser.helpers import config
    monkeypatch.setattr(config,"get_browser_config",lambda:{"runtime_backend":"container"})
    result = setup.snapshot()
    assert result["steps"][2]["reason"] == "screen_recording_required"
    assert result["steps"][3]["state"] == "action_here"
    assert "secret" not in json.dumps(result)
    gateway["scopes"]["computer_use"] = False
    assert setup.snapshot()["steps"][2]["reason"] == "access_off"


def test_multiple_hosts_fail_closed_and_unknown_is_not_ready(monkeypatch):
    from plugins._browser.helpers import config
    monkeypatch.setattr(config,"get_browser_config",lambda:{})
    monkeypatch.setattr(setup.ws,"launcher_gateway_status",lambda:{"multiple_hosts":True})
    result = setup.snapshot()
    assert not result["connected"]
    assert result["steps"][0]["reason"] == "multiple_hosts"
    assert result["steps"][1]["state"] == "unavailable"
