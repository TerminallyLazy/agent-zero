"""Context Engine initialization at monologue start.

Performs a lightweight health check against the Context Engine services
on the first iteration so the agent knows early whether code search
is available. Stores the status on the agent for other extensions.
"""

import importlib.util
import os

from python.helpers.extension import Extension
from python.helpers import plugins, errors
from agent import LoopData

DATA_NAME_CE_STATUS = "_ce_status"


def _load_client():
    """Import ContextEngineClient via file path (bypasses hyphen in dir name)."""
    client_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "..", "helpers", "client.py"
    )
    client_path = os.path.normpath(client_path)
    spec = importlib.util.spec_from_file_location("context_engine_client", client_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.ContextEngineClient


class ContextEngineInit(Extension):

    async def execute(self, loop_data: LoopData = LoopData(), **kwargs):
        # Only run on the very first iteration of a monologue
        if loop_data.iteration != 0:
            return

        config = plugins.get_plugin_config("context-engine", self.agent)
        if not config:
            return

        try:
            ContextEngineClient = _load_client()
            client = ContextEngineClient(config)
            status = await client.status()

            if status.get("ok", False) or "error" not in status:
                self.agent.set_data(DATA_NAME_CE_STATUS, "connected")
            else:
                self.agent.set_data(DATA_NAME_CE_STATUS, "error")
                self.agent.context.log.log(
                    type="warning",
                    heading="Context Engine not available",
                    content=status.get("error", "Service unreachable"),
                )
        except Exception as exc:
            self.agent.set_data(DATA_NAME_CE_STATUS, "error")
            err = errors.format_error(exc)
            self.agent.context.log.log(
                type="warning",
                heading="Context Engine init failed",
                content=err,
            )
