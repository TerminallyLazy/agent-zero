from __future__ import annotations

from helpers.extension import Extension

from usr.plugins.agent_harness.helpers import lifecycle
from usr.plugins.agent_harness.helpers import settings as harness_settings
from usr.plugins.agent_harness.helpers.cost_tracker import record_usage, check_budget
from usr.plugins.agent_harness.helpers.guardrails import request_checkpoint


class HarnessCost(Extension):
    async def execute(self, response: str = "", **kwargs):
        if not self.agent:
            return
        run = lifecycle.get_current_run(self.agent)
        if not run:
            return
        agent_settings = harness_settings.load_agent_settings(self.agent)
        if not agent_settings.get("cost_tracking_enabled", True):
            return

        try:
            from helpers.tokens import approximate_tokens
            completion_tokens = approximate_tokens(response) if response else 0
        except ImportError:
            completion_tokens = len(response) // 4 if response else 0

        if completion_tokens > 0:
            record_usage(run, prompt_tokens=0, completion_tokens=completion_tokens)
            lifecycle.save_current_run(self.agent.context, run)

            if check_budget(run, agent_settings):
                request_checkpoint(
                    run,
                    reason="Token budget exhausted. Approve to continue or stop the run.",
                    proposed_action="Continue execution beyond token budget",
                    tool_name="harness_cost",
                    tool_args={},
                    risk_level="high",
                )
                lifecycle.save_current_run(self.agent.context, run)
