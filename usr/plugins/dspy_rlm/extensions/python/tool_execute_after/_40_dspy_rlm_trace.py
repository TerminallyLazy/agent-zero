from __future__ import annotations

from typing import Any

from helpers.extension import Extension
from helpers.tool import Response

from usr.plugins.dspy_rlm.helpers import config as config_module
from usr.plugins.dspy_rlm.helpers import state
from usr.plugins.dspy_rlm.helpers.runtime_policy import RuntimePolicy
from usr.plugins.dspy_rlm.helpers import trace as trace_helper


class DspyRlmToolTrace(Extension):
    async def execute(
        self,
        tool_name: str = "",
        response: Response | None = None,
        **kwargs: Any,
    ):
        if not self.agent:
            return

        cfg = config_module.load_config(self.agent)
        policy = RuntimePolicy.from_config(cfg)
        if not policy.can_capture():
            return

        context_id = self.agent.context.id
        loop_data = getattr(self.agent, "loop_data", None)
        iteration = int(loop_data.iteration if loop_data else -1)

        response_text = response.message if response is not None else ""
        success = not bool(response is None or not str(response_text).strip())
        tool_args = {}
        current_tool = getattr(loop_data, "current_tool", None)
        if current_tool and hasattr(current_tool, "args"):
            if isinstance(current_tool.args, dict):
                tool_args = current_tool.args

        trace_event = trace_helper.record_tool_event(
            context_id=context_id,
            agent_name=self.agent.agent_name,
            tool_name=tool_name,
            response_text=response_text,
            loop_iteration=iteration,
            tool_args=tool_args,
            success=success,
        )
        state.record_tool_result(
            context_id=context_id,
            tool_name=tool_name,
            success=success,
            response_preview=trace_event.get("response_preview", ""),
        )
