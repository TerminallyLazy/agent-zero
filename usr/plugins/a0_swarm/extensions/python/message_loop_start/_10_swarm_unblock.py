from helpers.extension import Extension
from usr.plugins.a0_swarm.helpers.registry import (
    SwarmRegistry, SwarmAgentStatus, utc_iso_now,
)
from usr.plugins.a0_swarm.helpers import delivery


class SwarmUnblockOnResume(Extension):
    async def execute(self, loop_data=None, **kwargs):
        reg = SwarmRegistry.get()
        entry = reg.get_agent_by_context(self.agent.context.id)
        if entry:
            if entry.status == SwarmAgentStatus.BLOCKED:
                reg.update_status(entry.agent_name, SwarmAgentStatus.WORKING, blocker="", last_seen_at=utc_iso_now())
            else:
                reg.update_status(entry.agent_name, entry.status, last_seen_at=utc_iso_now())
            await delivery.deliver_queued_for_agent(entry.agent_name)
