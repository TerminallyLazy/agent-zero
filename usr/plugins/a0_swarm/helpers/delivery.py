from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agent import AgentContext, UserMessage
from usr.plugins.a0_swarm.helpers.registry import SwarmMessage, SwarmRegistry
from usr.plugins.a0_swarm.helpers.remotes import RemoteEndpoint
from usr.plugins.a0_swarm.helpers import a2a_runner


PENDING_REPLY_KEY = "_a0_swarm_pending_reply_messages"


@dataclass
class DeliveryResult:
    ok: bool
    state: str
    reason: str = ""
    message_id: str = ""


def _format_payload(sender: str, content: str) -> str:
    if sender == "orchestrator":
        return (
            "[Orchestrator message]\n"
            f"{content}\n\n"
            "If this asks a question, changes your task, or needs acknowledgement, "
            "reply immediately with the swarm_message tool using recipient=\"orchestrator\". "
            "Do not use the final response tool just to answer this message; after the "
            "swarm_message reply, continue your assigned work."
        )
    return f"[Message from {sender}]: {content}"


def _pending_replies(agent: Any) -> list[dict]:
    try:
        value = agent.get_data(PENDING_REPLY_KEY)
    except Exception:
        value = None
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _set_pending_replies(agent: Any, pending: list[dict]) -> None:
    try:
        agent.set_data(PENDING_REPLY_KEY, pending)
    except Exception:
        try:
            agent.data[PENDING_REPLY_KEY] = pending
        except Exception:
            pass


def _queue_reply_capture(agent: Any, msg: SwarmMessage, target_agent_name: str) -> None:
    if msg.sender != "orchestrator":
        return
    pending = _pending_replies(agent)
    pending.append({
        "message_id": msg.message_id,
        "run_id": msg.run_id,
        "agent_name": target_agent_name,
    })
    _set_pending_replies(agent, pending)


def capture_pending_reply(agent: Any, content: str) -> SwarmMessage | None:
    """Record a normal agent response as a swarm reply when it answers a panel message."""
    content = (content or "").strip()
    if not agent or not content:
        return None

    reg = SwarmRegistry.get()
    entry = reg.get_agent_by_context(agent.context.id)
    if entry is None:
        return None

    pending = _pending_replies(agent)
    if not pending:
        return None

    selected_index = -1
    selected = None
    for idx, item in enumerate(pending):
        if item.get("agent_name") == entry.agent_name:
            selected_index = idx
            selected = item
            break
    if selected is None:
        return None

    source_id = str(selected.get("message_id") or "")
    source = reg.get_message(source_id) if source_id else None
    if source is None or source.delivery_state != "delivered":
        return None

    pending.pop(selected_index)
    _set_pending_replies(agent, pending)

    reply = reg.create_message(entry.run_id, entry.agent_name, "orchestrator", content)
    reg.mark_message_delivered(reply.message_id)
    return reg.get_message(reply.message_id) or reply


async def deliver_message(message_id: str) -> DeliveryResult:
    reg = SwarmRegistry.get()
    msg = reg.get_message(message_id)
    if msg is None:
        return DeliveryResult(False, "failed", "message not found", message_id)
    if msg.delivery_state == "delivered":
        return DeliveryResult(True, "delivered", "", message_id)
    if msg.recipient == "orchestrator":
        reg.mark_message_delivered(message_id)
        return DeliveryResult(True, "delivered", "", message_id)

    target = reg.get_agent(msg.recipient)
    if target is None:
        reason = f"target agent {msg.recipient} not found"
        reg.mark_message_failed(message_id, reason)
        return DeliveryResult(False, "failed", reason, message_id)

    if target.delivery_mode == "remote_a2a" or target.is_remote:
        return await _deliver_remote(reg, msg, target)
    return await _deliver_local(reg, msg, target)


async def _deliver_local(reg: SwarmRegistry, msg, target) -> DeliveryResult:
    ctx = AgentContext.get(target.context_id)
    if ctx is None:
        reason = f"context not found for {target.agent_name}"
        reg.mark_message_failed(msg.message_id, reason)
        return DeliveryResult(False, "failed", reason, msg.message_id)

    runtime_agent = ctx.get_agent()
    reg.mark_message_delivered(msg.message_id)
    _queue_reply_capture(runtime_agent, msg, target.agent_name)
    ctx.communicate(UserMessage(message=_format_payload(msg.sender, msg.content)))
    return DeliveryResult(True, "delivered", "", msg.message_id)


async def _deliver_remote(reg: SwarmRegistry, msg, target) -> DeliveryResult:
    if not target.remote_base_url:
        reason = f"remote base URL missing for {target.agent_name}"
        reg.mark_message_failed(msg.message_id, reason)
        return DeliveryResult(False, "failed", reason, msg.message_id)
    if not target.context_id:
        reason = f"remote context id missing for {target.agent_name}"
        reg.mark_message_failed(msg.message_id, reason)
        return DeliveryResult(False, "failed", reason, msg.message_id)

    remote = RemoteEndpoint(
        label=target.remote_label or target.agent_name,
        base_url=target.remote_base_url,
        auth_token=getattr(target, "remote_auth_token", ""),
    )
    ok = await a2a_runner.send_intervention(
        remote,
        _format_payload(msg.sender, msg.content),
        context_id=target.context_id,
    )
    if ok:
        reg.mark_message_delivered(msg.message_id)
        return DeliveryResult(True, "delivered", "", msg.message_id)

    reason = f"remote intervention failed for {target.remote_label or target.remote_base_url}"
    reg.mark_message_failed(msg.message_id, reason)
    return DeliveryResult(False, "failed", reason, msg.message_id)


async def deliver_queued_for_agent(agent_name: str) -> list[DeliveryResult]:
    reg = SwarmRegistry.get()
    results: list[DeliveryResult] = []
    for msg in reg.queued_messages_for_agent(agent_name):
        results.append(await deliver_message(msg.message_id))
    return results
