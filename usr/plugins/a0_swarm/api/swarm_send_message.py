from agent import AgentContext, UserMessage
from helpers.api import ApiHandler, Request
from usr.plugins.a0_swarm.helpers.registry import (
    SwarmRegistry, SwarmMessage, SwarmAgentStatus, utc_iso_now,
)


class SwarmSendMessage(ApiHandler):
    async def process(self, input: dict, request: Request):
        data = input or {}
        agent_name = data.get("agent_name", "")
        content    = data.get("content", "")
        unblock    = bool(data.get("unblock", False))

        if not agent_name or not content:
            return {"ok": False, "error": "agent_name and content are required"}

        reg = SwarmRegistry.get()
        entry = reg.get_agent(agent_name)
        if not entry:
            return {"ok": False, "error": f"Agent {agent_name} not found"}

        reg.add_message(SwarmMessage(
            sender="orchestrator", recipient=agent_name,
            content=content, timestamp=utc_iso_now(),
        ))
        if unblock and entry.status == SwarmAgentStatus.BLOCKED:
            reg.update_status(agent_name, SwarmAgentStatus.WORKING, blocker="")

        ctx = AgentContext.get(entry.context_id)
        if ctx:
            ctx.communicate(UserMessage(message=f"[Orchestrator]: {content}"))
        return {"ok": True}
