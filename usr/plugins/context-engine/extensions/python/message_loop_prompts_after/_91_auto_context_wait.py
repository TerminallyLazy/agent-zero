"""Wait for the auto-context search task to complete before LLM call."""

from python.helpers.extension import Extension
from python.helpers import plugins
from agent import LoopData

# Must match the constant in _55_auto_context.py
DATA_NAME_TASK = "_ce_auto_context_task"


class AutoContextWait(Extension):

    async def execute(self, loop_data: LoopData = LoopData(), **kwargs):
        config = plugins.get_plugin_config("context-engine", self.agent)
        if not config:
            return

        task = self.agent.get_data(DATA_NAME_TASK)
        if task and not task.done():
            await task
