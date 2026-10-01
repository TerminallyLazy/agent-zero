from helpers.extension import Extension
from plugins._a0_connector.helpers import host_control


class HostControl(Extension):
    async def execute(self, **kwargs):
        if self.agent:
            await host_control.gate_agent(self.agent)
            with host_control._lock:
                self.agent.set_data("host_viewer_dispatch_epochs", {
                    sid: state["epoch"] for sid, state in host_control._remote.items()
                })
