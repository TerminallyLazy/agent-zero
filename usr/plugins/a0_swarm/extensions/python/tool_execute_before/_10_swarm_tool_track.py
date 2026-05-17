from helpers.extension import Extension
from usr.plugins.a0_swarm.helpers.registry import SwarmRegistry


class SwarmToolTrack(Extension):
    async def execute(self, tool_name: str = "", tool_args: dict | None = None, **kwargs):
        reg = SwarmRegistry.get()
        entry = reg.get_agent_by_context(self.agent.context.id)
        if entry:
            text = f"Using tool: {tool_name}"
            reg.increment_tool_call(entry.agent_name, tool_name)
            reg.update_activity(entry.agent_name, text)
            if entry.run_id:
                reg.add_event(entry.run_id, entry.agent_name, "activity", text)
