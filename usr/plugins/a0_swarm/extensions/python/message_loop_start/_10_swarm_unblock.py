from helpers.extension import Extension
from usr.plugins.a0_swarm.helpers.registry import (
    SwarmRegistry, SwarmAgentStatus,
)


class SwarmUnblockOnResume(Extension):
    async def execute(self, loop_data=None, **kwargs):
        reg = SwarmRegistry.get()
        entry = reg.get_agent_by_context(self.agent.context.id)
        if entry and entry.status == SwarmAgentStatus.BLOCKED:
            reg.update_status(entry.agent_name, SwarmAgentStatus.WORKING, blocker="")
