from agent import AgentContext
from helpers.api import ApiHandler, Request
from usr.plugins.a0_swarm.helpers.registry import (
    SwarmRegistry, SwarmAgentStatus,
)
from usr.plugins.a0_swarm.helpers import a2a_runner
from usr.plugins.a0_swarm.helpers.remotes import RemoteEndpoint


class SwarmCancel(ApiHandler):
    async def process(self, input: dict, request: Request):
        agent_name = (input or {}).get("agent_name", "")
        if not agent_name:
            return {"ok": False, "error": "agent_name is required"}

        reg = SwarmRegistry.get()
        entry = reg.get_agent(agent_name)
        if not entry:
            return {"ok": False, "error": f"Agent {agent_name} not found"}

        # Order matters: terminal status FIRST so the subagent's later
        # DONE/FAILED write is absorbed by terminal-state in update_status.
        reg.update_status(agent_name, SwarmAgentStatus.CANCELLED, current_activity="")

        if entry.is_remote:
            remote = RemoteEndpoint(label=entry.remote_label, base_url=entry.remote_base_url)
            await a2a_runner.cancel_task(remote, entry.remote_task_id)
        else:
            ctx = AgentContext.get(entry.context_id)
            if ctx:
                ctx.kill_process()
        return {"ok": True}
