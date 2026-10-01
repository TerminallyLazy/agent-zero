from helpers.extension import Extension
from plugins._a0_connector.helpers.host_control import gate_agent


class HostControl(Extension):
    async def execute(self, data: dict, **kwargs):
        if self.agent:
            await gate_agent(self.agent)
