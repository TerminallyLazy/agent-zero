from helpers.extension import Extension
from usr.plugins.a0_swarm.helpers.registry import SwarmRegistry
from usr.plugins.a0_swarm.extensions.python.webui_ws_event._10_swarm_ws import _subs


class SwarmWsCleanup(Extension):
    async def execute(self, instance=None, sid: str = "", **kwargs):
        entry = _subs.pop(sid, None)
        if entry:
            SwarmRegistry.get().remove_subscriber(entry[2])
