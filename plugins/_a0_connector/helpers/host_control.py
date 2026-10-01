"""Durable host takeover broker and agent dispatch fence.

Only small ownership/receipt records persist. Viewer frames and text stay in the
authenticated request path. Connector acknowledgement is required for control.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import threading
import time
import uuid
from pathlib import Path

from plugins._a0_connector.helpers import ws_runtime as ws, host_targets

FEATURE = "host_viewer_v1"
_lock = threading.RLock()
_remote = {}
_records = {}
_watchers = {}
_directory = Path("usr/host-control")


def observe(sid, gateway):
    control = (gateway.get("status") or {}).get("host_control") if isinstance(gateway, dict) else None
    if isinstance(control, dict) and control.get("version") == 1 and len(str(control.get("epoch", ""))) == 32:
        with _lock:
            _remote[sid] = dict(control)


def forget(sid):
    with _lock:
        _remote.pop(sid, None)


def _key(gateway):
    return hashlib.sha256(str(gateway.get("gateway_id") or gateway.get("id") or "").encode()).hexdigest()


def _record(key):
    if key not in _records:
        path = _directory / (key + ".json")
        if path.exists():
            try:
                value = json.loads(path.read_text())
                if not isinstance(value, dict) or value.get("phase") not in {"watching", "human", "held", "requesting", "returning"}:
                    raise ValueError()
                if value["phase"] != "watching":
                    value["phase"] = "held"
                if value.get("busy"):
                    value.setdefault("receipts", {})[value.pop("busy")] = "uncertain"
                _records[key] = value
            except (ValueError, OSError):
                _records[key] = {"phase": "held", "context": "", "revision": uuid.uuid4().hex}
        else:
            _records[key] = {"phase": "watching", "revision": uuid.uuid4().hex, "receipts": {}}
    return _records[key]


def _save(key, value):
    _directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = _directory / (key + ".json")
    temp = path.with_suffix(".pending")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(value, stream)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)
    fd = os.open(_directory, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _target(context):
    snapshot = ws.host_routing_snapshot(context.id)
    sid, gateway = snapshot.get("sid"), snapshot.get("gateway")
    if snapshot.get("ambiguous") or not sid or not gateway:
        raise ValueError("Choose one connected Launcher host")
    return sid, gateway, _key(gateway)


def fence(context_id, sid, payload, agent=None):
    """Final synchronous check before emit, shared by every host tool family."""
    gateway = ws.launcher_gateway_metadata_for_sid(sid)
    if gateway:
        with _lock:
            record = _record(_key(gateway))
            if record["phase"] != "watching":
                raise ValueError("Human takeover holds this host. Return to A0 before automation can continue.")
            remote = _remote.get(sid)
            if remote:
                if remote.get("phase") != "watching":
                    raise ValueError("The host is held for human control. Review the live viewer.")
                observations = agent.get_data("host_viewer_dispatch_epochs") if agent and hasattr(agent, "get_data") else None
                expected = (observations or {}).get(sid, remote["epoch"])
                expected = payload.get("host_epoch", expected)
                if expected != remote["epoch"]:
                    raise ValueError("This action was prepared before human takeover. Observe the host again.")
                payload["host_epoch"] = expected
    else:
        with _lock:
            if any(r["phase"] != "watching" for r in _records.values()):
                raise ValueError("A host is held; this connection cannot prove it targets a different computer")


def agent_state(context):
    """Root and descendants wait; other chats encounter the final host fence."""
    with _lock:
        # Include persisted holds even if the connector is disconnected.
        if _directory.exists():
            for path in _directory.glob("*.json"):
                _record(path.stem)
        ancestors, cursor = set(), context
        while cursor is not None and cursor.id not in ancestors:
            ancestors.add(cursor.id)
            parent = cursor.get_output_data("parent_context_id")
            cursor = host_targets.context_for(parent) if parent else None
        relevant = [r for r in _records.values() if r.get("context") in ancestors]
        return any(r["phase"] != "watching" for r in relevant), tuple(r["revision"] for r in relevant)


async def gate_agent(agent):
    held, revision = agent_state(agent.context)
    previous = agent.get_data("host_viewer_observation_revision")
    if previous is None:
        previous = revision
    while held:
        await asyncio.sleep(0.1)
        held, revision = agent_state(agent.context)
    agent.set_data("host_viewer_observation_revision", revision)
    if previous != revision:
        from agent import UserMessage
        from helpers.errors import InterventionException
        with _lock:
            observations = [r["observation"] for r in _records.values() if r.get("observation") and r["revision"] in revision]
        message = UserMessage(message="Human control has returned to A0. The host state changed. Discard prepared actions, coordinates and element references. Observe the current browser or computer before continuing the existing task. Do not repeat completed work.", attachments=observations)
        agent._clear_responses_pending_state()
        agent.hist_add_user_message(message, intervention=True)
        raise InterventionException(message)


async def _send(sid, payload):
    from helpers.ws_manager import get_shared_ws_manager
    op_id = uuid.uuid4().hex
    loop = asyncio.get_running_loop()
    future = loop.create_future()
    ws.store_pending_browser_op(op_id, sid=sid, future=future, loop=loop, context_id=payload["context"])
    try:
        await get_shared_ws_manager().emit_to("/ws", sid, "connector_browser_op",
            {**payload, "op_id": op_id, "action": "_host_viewer", "context_id": payload["context"]},
            handler_id=__name__)
        result = await asyncio.wait_for(future, timeout=22)
        if not result.get("ok"):
            raise ValueError(str(result.get("error") or "The host rejected the viewer request")[:300])
        value = result.get("result")
        if not isinstance(value, dict):
            raise ValueError("Invalid host acknowledgement")
        if "epoch" in value:
            with _lock:
                _remote[sid] = dict(value)
        return value
    finally:
        ws.clear_pending_browser_op(op_id)


def _owner(owner):
    return hashlib.sha256(owner.encode()).hexdigest()


def projection(context, owner, viewer):
    sid, gateway, key = _target(context)
    with _lock:
        remote = _remote.get(sid)
        value = _record(key)
        mine = value.get("owner") == _owner(owner) and value.get("viewer") == viewer and value.get("context") == context.id
        phase = value["phase"]
        if remote and remote.get("phase") != "watching" and phase == "watching":
            phase = "held"
        return {"version": 1, "context": context.id, "supported": bool(remote),
                "phase": phase, "mine": mine, "sequence": value.get("sequence", 0) if mine else 0,
                "host_label": gateway.get("host_label", "Computer"),
                "recoverable": phase == "held" and value.get("context") == context.id,
                "revision": value["revision"]}


async def command(context, owner, data):
    action = data.get("command")
    if action not in {"status", "acquire", "frame", "input", "return", "hold", "heartbeat"}:
        raise ValueError("Unknown viewer command")
    viewer = data.get("viewer")
    if not isinstance(viewer, str) or len(viewer) != 32:
        raise ValueError("Invalid viewer identity")
    if action == "status":
        result = projection(context, owner, viewer)
        sid, _, key = _target(context)
        if result["supported"]:
            remote = await _send(sid, {"command": "status", "context": context.id})
            with _lock:
                value = _record(key)
                if remote["phase"] == "held" and value["phase"] == "human":
                    value["phase"] = "held"
                    _save(key, value)
            result = projection(context, owner, viewer)
        return result
    sid, gateway, key = _target(context)
    with _lock:
        if sid not in _remote:
            raise ValueError("This connector does not support acknowledged takeover")
        value = _record(key)
        mine = value.get("owner") == _owner(owner) and value.get("viewer") == viewer and value.get("context") == context.id
        source = data.get("source")
        if source not in {"browser", "computer_use"}:
            raise ValueError("Invalid capture source")
        if not gateway.get("master_enabled") or not gateway.get("scopes", {}).get(source):
            raise ValueError("Host access was disabled in Launcher")
        if action in {"acquire", "frame"} and value["phase"] == "watching":
            host_targets.assert_dispatch(context.id, sid, source)
            binding = host_targets.inherited_binding(context)
            if not binding or binding.get("context_id") != context.id:
                raise ValueError("Start a host task in this chat before opening its live session")
        elif not mine and not (action == "acquire" and value["phase"] == "held" and value.get("context") == context.id):
            raise ValueError("Another viewer owns this host. Wait for an explicit recovery.")
        if action in {"input", "heartbeat"} and value["phase"] != "human":
            raise ValueError("Human input is not enabled")
        if action in {"return", "hold"} and value["phase"] not in {"human", "held"}:
            raise ValueError("This host is not awaiting handback")
        if action == "frame":
            now = time.monotonic()
            watcher = _watchers.get(key)
            if watcher and now - watcher[1] < 5 and watcher[0] != (context.id, viewer):
                raise ValueError("The live surface is open in another viewer")
            if watcher and now - watcher[1] < 0.3:
                raise ValueError("Wait for the next capture")
            _watchers[key] = ((context.id, viewer), now)
        mutating = action in {"acquire", "input", "return", "hold"}
        request_id = data.get("request_id")
        if mutating:
            if not isinstance(request_id, str) or len(request_id) != 32:
                raise ValueError("Invalid command receipt")
            receipts = value.setdefault("receipts", {})
            if request_id in receipts:
                raise ValueError("This command was already submitted. It will not be replayed.")
            if value.get("busy"):
                raise ValueError("A previous control command has an unresolved outcome")
            if len(receipts) >= 128:
                del receipts[next(iter(receipts))]
            receipts[request_id] = "pending"
            value["busy"] = request_id
        if action == "acquire":
            if context.get_output_data("parent_context_id"):
                raise ValueError("Take over from the parent chat")
            value.update(phase="requesting", context=context.id, owner=_owner(owner), viewer=viewer,
                         lease=value.get("lease") or uuid.uuid4().hex, revision=uuid.uuid4().hex)
        if action == "return":
            value["phase"] = "returning"
        if mutating:
            _save(key, value)
        payload = {"command": action, "source": source, "context": context.id,
                   "lease": value.get("lease"), "epoch": _remote[sid]["epoch"]}
        if action == "input":
            payload.update(sequence=data.get("sequence"), frame=data.get("frame"), input=data.get("input"))
    try:
        if action == "return":
            # Acknowledged drain and fresh observation precede release. The agent
            # extension invalidates old model output before its next action.
            observation = await _send(sid, {**payload, "command": "prepare_return"})
            if observation.get("data") and observation.get("mime") == "image/jpeg":
                from helpers import media_artifacts
                saved = media_artifacts.save_base64_artifact(observation["data"], mime_type="image/jpeg",
                    directory_parts=("usr", "chats", context.id, "screenshots"),
                    preferred_name="human-handback.jpg", max_bytes=1_500_000)
                with _lock:
                    value["observation"] = saved.path
                    _save(key, value)
            response = await _send(sid, {**payload, "command": "release"})
        else:
            response = await _send(sid, payload)
        with _lock:
            if action == "acquire":
                value.update(phase="human", sequence=0)
            elif action == "return":
                value.update(phase="watching", revision=uuid.uuid4().hex, lease="")
            elif action == "hold":
                value["phase"] = "held"
            elif action == "input":
                value["sequence"] = data["sequence"]
            if mutating:
                value["receipts"][request_id] = "acknowledged"
                value.pop("busy", None)
                _save(key, value)
        if action == "frame":
            return {"version": 1, "context": context.id, "frame": response}
        return {**projection(context, owner, viewer), "request_id": request_id}
    except BaseException:
        if mutating:
            with _lock:
                value["phase"] = "held"
                value["receipts"][request_id] = "uncertain"
                value.pop("busy", None)
                _save(key, value)
        raise
