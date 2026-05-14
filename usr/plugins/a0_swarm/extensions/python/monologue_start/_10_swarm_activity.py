from helpers.extension import Extension
from usr.plugins.a0_swarm.helpers.registry import SwarmRegistry


class SwarmActivityOnMonologueStart(Extension):
    async def execute(self, loop_data=None, **kwargs):
        reg = SwarmRegistry.get()
        entry = reg.get_agent_by_context(self.agent.context.id)
        if entry:
            reg.update_activity(entry.agent_name, "Thinking...")
