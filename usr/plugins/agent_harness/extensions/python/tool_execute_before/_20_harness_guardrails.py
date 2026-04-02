from __future__ import annotations

from helpers.errors import RepairableException
from helpers.extension import Extension

from usr.plugins.agent_harness.helpers import runtime


class HarnessGuardrails(Extension):
    async def execute(self, tool_name: str = "", tool_args: dict | None = None, **kwargs):
        if not self.agent:
            return

        run = runtime.get_current_run(self.agent)
        if not run:
            return

        settings = runtime.load_agent_settings(self.agent)
        checkpoint = runtime.assess_tool_guardrail(
            run=run,
            tool_name=tool_name,
            tool_args=tool_args or {},
            settings=settings,
        )
        if not checkpoint:
            return

        runtime.save_current_run(self.agent.context, run)
        raise RepairableException(
            "Agent Harness blocked a risky action before execution. "
            f"Pending checkpoint: {checkpoint.reason} "
            f"Proposed action: {checkpoint.proposed_action}. "
            "Do not retry the risky tool until the user approves the checkpoint."
        )
