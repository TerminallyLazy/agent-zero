from __future__ import annotations

from dataclasses import dataclass

from agent import AgentContext, UserMessage
from usr.plugins.a0_swarm.helpers.registry import SwarmRegistry
from usr.plugins.a0_swarm.helpers.remotes import RemoteEndpoint
from usr.plugins.a0_swarm.helpers import a2a_runner


@dataclass
class DeliveryResult:
    ok: bool
    state: str
    reason: str = ""
    message_id: str = ""


def _format_payload(sender: str, content: str) -> str:
    if sender == "orchestrator":
        return f"[Orchestrator]: {content}"
    return f"[Message from {sender}]: {content}"


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

    ctx.communicate(UserMessage(message=_format_payload(msg.sender, msg.content)))
    reg.mark_message_delivered(msg.message_id)
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

    remote = RemoteEndpoint(label=target.remote_label or target.agent_name, base_url=target.remote_base_url)
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
