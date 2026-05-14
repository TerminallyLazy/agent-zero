from agent import AgentContext
from helpers.api import ApiHandler, Request
from usr.plugins.a0_swarm.helpers.registry import (
    SwarmRegistry, SwarmAgentStatus,
)


class SwarmCancel(ApiHandler):
    async def process(self, input: dict, request: Request):
        agent_name = (input or {}).get("agent_name", "")
        if not agent_name:
            return {"ok": False, "error": "agent_name is required"}

        reg = SwarmRegistry.get()
        entry = reg.get_agent(agent_name)
        if not entry:
            return {"ok": False, "error": f"Agent {agent_name} not found"}

        # Order matters: terminal status FIRST so the subagent's later DONE/FAILED write
        # is absorbed by terminal-state in update_status.
        reg.update_status(agent_name, SwarmAgentStatus.CANCELLED, current_activity="")
        ctx = AgentContext.get(entry.context_id)
        if ctx:
            ctx.kill_process()
        return {"ok": True}
