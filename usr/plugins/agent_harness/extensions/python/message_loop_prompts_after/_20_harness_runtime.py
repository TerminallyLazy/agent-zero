from __future__ import annotations

from agent import LoopData
from helpers.extension import Extension

from usr.plugins.agent_harness.helpers import runtime


class HarnessRuntimePrompt(Extension):
    async def execute(self, loop_data: LoopData = LoopData(), **kwargs):
        if not self.agent:
            return
        run = runtime.get_current_run(self.agent)
        if not run:
            return

        # Auto-update objective from first user message if still default
        if run.objective == runtime.DEFAULT_RUN_OBJECTIVE and self.agent.last_user_message:
            msg_text = ""
            if hasattr(self.agent.last_user_message, "message"):
                msg_text = str(self.agent.last_user_message.message)
            elif hasattr(self.agent.last_user_message, "content"):
                content = self.agent.last_user_message.content
                if isinstance(content, dict):
                    msg_text = str(content.get("user_message", ""))
                else:
                    msg_text = str(content)
            if msg_text and len(msg_text.strip()) > 10:
                run.objective = msg_text.strip()[:200]
                runtime.save_current_run(self.agent.context, run)

        summary = runtime.render_runtime_summary(run)
        if summary:
            loop_data.extras_persistent["agent_harness_runtime"] = summary
