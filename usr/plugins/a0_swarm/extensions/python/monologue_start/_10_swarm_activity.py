from helpers.extension import Extension
from usr.plugins.a0_swarm.helpers.registry import SwarmRegistry, utc_iso_now


class SwarmActivityOnMonologueStart(Extension):
    async def execute(self, loop_data=None, **kwargs):
        reg = SwarmRegistry.get()
        entry = reg.get_agent_by_context(self.agent.context.id)
        if entry:
            reg.update_status(entry.agent_name, entry.status, current_activity="Thinking...", last_seen_at=utc_iso_now())
            if entry.run_id:
                reg.add_event(entry.run_id, entry.agent_name, "activity", "Thinking...")
