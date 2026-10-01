"""Context-bound host routing. Tokens are session-bound; bindings fail closed on restart."""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
from typing import Any

from plugins._a0_connector.helpers import ws_runtime as ws

FEATURE = "host_tasks_v1"
KEY = "connector_host_target_v1"  # Persist with the context, including stale bindings.
_secret = secrets.token_bytes(32)


class HostTargetError(ValueError):
    pass


def _digest(value: Any) -> str:
    return hmac.new(_secret, json.dumps(value, sort_keys=True).encode(), hashlib.sha256).hexdigest()


def context_for(context_id: str):
    from agent import AgentContext
    return AgentContext.get(context_id)


def all_contexts():
    from agent import AgentContext
    return AgentContext.all()


def _has_active_work(context) -> bool:
    from helpers import message_queue
    for candidate in all_contexts():
        cursor, seen = candidate, set()
        while cursor is not None and cursor.id not in seen:
            if cursor.id == context.id:
                if candidate.is_running() or message_queue.get_queue(candidate):
                    return True
                break
            seen.add(cursor.id)
            cursor = context_for(cursor.get_output_data("parent_context_id") or "")
    return context.is_running() or bool(message_queue.get_queue(context))


def inherited_binding(context):
    """Follow Core's explicit subordinate ancestry, never names or agent numbers."""
    seen = set()
    while context is not None:
        if context.id in seen:
            return {"invalid": True}
        seen.add(context.id)
        value = context.get_data(KEY)
        if value is not None:
            return value if isinstance(value, dict) else {"invalid": True}
        parent = context.get_output_data("parent_context_id")
        if not parent:
            return None
        context = context_for(parent)
        if context is None:
            # An orphan cannot prove that it is free of an inherited restriction.
            return {"invalid": True}
    return None


def _browser_config(context) -> dict:
    from plugins._browser.helpers.config import get_browser_config
    config = get_browser_config(agent=context.agent0)
    return {key: config.get(key) for key in (
        "runtime_backend", "host_browser_selection", "host_browser_profile_mode",
    )}


def _snapshot(context) -> dict:
    snapshot = ws.host_routing_snapshot(context.id)
    snapshot["browser_config"] = _browser_config(context)
    return snapshot


def _revision(context, snapshot: dict) -> str:
    # Inventory and diagnostic text are observations, not target identity. Keep
    # connection epochs, selected browser/profile, scopes and effective config.
    stable = {key: ({k: v for k, v in value.items() if k not in {
        "available_browsers", "content_helper_sha256", "last_error", "updated_at",
    }} if isinstance(value, dict) else value) for key, value in snapshot.items()}
    return _digest([context.id, stable])


def _capabilities(snapshot: dict) -> dict:
    gateway = snapshot.get("gateway") or {}
    scopes = gateway.get("scopes", {})
    active = gateway.get("master_enabled") and gateway.get("state") not in {"error", "disconnected", "connecting"}
    result = {}
    for name in ("browser", "computer_use", "files", "file_write", "code_execution"):
        metadata = snapshot.get(name) or {}
        reason = "off"
        if active and scopes.get(name):
            if name in {"browser", "computer_use"}:
                status = str(metadata.get("status", "")).lower().replace("_", " ")
                if not metadata.get("supported"):
                    reason = "unsupported"
                elif not metadata.get("enabled"):
                    reason = "off"
                elif status in {"ready", "active"} or (
                    name == "computer_use" and status in {"interactive", "persistent", "allow"}
                ):
                    reason = "ready"
                else:
                    reason = "needs_attention"
                if name == "browser" and snapshot["browser_config"].get("runtime_backend") != "host_required":
                    reason = "container"
            else:
                reason = "ready" if metadata.get("enabled") else "off"
        result[name] = {"ready": reason == "ready", "state": reason}
    return result


def host_status(context, owner: str) -> dict:
    snapshot = _snapshot(context)
    gateway = snapshot.get("gateway")
    ambiguous = snapshot["ambiguous"]
    capabilities = _capabilities(snapshot)
    binding = inherited_binding(context)
    revision = _revision(context, snapshot)
    target = _digest(["target", snapshot.get("sid")]) if gateway else None
    state = "ambiguous" if ambiguous else (gateway.get("state", "unavailable") if gateway else "disconnected")
    return {
        "version": 1, "context_id": context.id, "state": state,
        "host_label": gateway.get("host_label", "Computer") if gateway else None,
        "target_id": target, "generation": _digest([owner, revision, target]) if gateway and not ambiguous else None,
        "observed_at": time.time(), "capabilities": capabilities,
        "bound": binding is not None,
        "binding_current": bool(binding and binding.get("revision") == revision),
    }


def bind(context, owner: str, target: str, generation: str, capability: str) -> dict:
    """Caller serializes submission; no await between validation and installation."""
    with ws._state_lock:
        return _bind_locked(context, owner, target, generation, capability)


def _bind_locked(context, owner: str, target: str, generation: str, capability: str) -> dict:
    status = host_status(context, owner)
    if capability not in {"browser", "computer_use"} or not status["capabilities"][capability]["ready"]:
        raise HostTargetError("The requested host capability is not ready. Check Launcher on the computer.")
    if not target or not generation or target != status["target_id"] or generation != status["generation"]:
        raise HostTargetError("The computer target changed. Refresh Computer and review it before sending again.")
    if context.get_output_data("parent_context_id"):
        raise HostTargetError("Choose the parent chat to start a host task.")
    previous = inherited_binding(context)
    snapshot = _snapshot(context)
    revision = _revision(context, snapshot)
    if _has_active_work(context):
        if not previous or previous.get("revision") != revision or previous.get("owner") != _digest(owner):
            raise HostTargetError("Stop active work and clear its queue before changing the host target.")
    binding = {"context_id": context.id, "sid": snapshot["sid"], "revision": revision,
               "host_label": status["host_label"], "owner": _digest(owner)}
    context.set_data(KEY, binding)
    return binding


def pinned_candidate(context_id: str) -> list[str] | None:
    context = context_for(context_id)
    if context is None:
        return None
    binding = inherited_binding(context)
    if binding is None:
        return None
    root = context_for(binding.get("context_id", ""))
    if root is None or binding.get("revision") != _revision(root, _snapshot(root)):
        return []
    return [binding["sid"]]


def assert_dispatch(context_id: str, sid: str, capability: str) -> None:
    pinned = pinned_candidate(context_id)
    if pinned is None:
        return
    if pinned != [sid]:
        raise HostTargetError("Host target is stale or unavailable. No action was dispatched; review Computer again.")
    context = context_for(context_id)
    binding = inherited_binding(context)
    root = context_for(binding["context_id"])
    if not _capabilities(_snapshot(root)).get(capability, {}).get("ready"):
        raise HostTargetError("Host capability is unavailable. Enable it locally and review the target again.")


def capture_identity(context_id: str) -> dict:
    context = context_for(context_id)
    binding = inherited_binding(context) if context else None
    if binding and "sid" in binding:
        return {"host_label": binding["host_label"], "target_id": _digest(["target", binding["sid"]])}
    return {}
