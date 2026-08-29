from __future__ import annotations

import asyncio

from agent import LoopData
from helpers.extension import Extension

from usr.plugins.dspy_rlm.helpers import config as config_module
from usr.plugins.dspy_rlm.helpers import state, trace as trace_helper
from usr.plugins.dspy_rlm.helpers.runtime_policy import RuntimePolicy
from usr.plugins.dspy_rlm.helpers import _scheduler_coordinator as scheduler
from usr.plugins.dspy_rlm.helpers import prompt_artifacts


class DspyRlmOptimizationScheduler(Extension):
    async def execute(self, loop_data: LoopData = LoopData(), **kwargs):
        if not self.agent:
            return

        cfg = config_module.load_config(self.agent)
        policy = RuntimePolicy.from_config(cfg)

        context_id = self.agent.context.id
        user_message = getattr(loop_data, "user_message", None)
        objective = ""
        if user_message is not None and hasattr(user_message, "content"):
            objective = str(user_message.content)
        response_text = str(getattr(loop_data, "last_response", "") or "")
        iteration = int(getattr(loop_data, "iteration", -1))

        # Observation and automatic scheduling are distinct capabilities.  Do
        # not let a disabled telemetry gate silently disable an explicitly
        # enabled enqueue path.
        if policy.can_capture():
            state.record_loop_attempt(
                context_id=context_id,
                objective=objective,
                response_preview=response_text,
                iteration=iteration,
            )
            trace_helper.record_loop_event(
                context_id=context_id,
                agent_name=self.agent.agent_name,
                objective=objective,
                loop_iteration=iteration,
                response_text=response_text,
            )
            applied_prompt_artifact = str(state.load_context_state(context_id).get("prompt_artifact_applied") or "")
            if applied_prompt_artifact:
                prompt_artifacts.record_observation(
                    context_id, applied_prompt_artifact, success=bool(response_text.strip()), cfg=cfg
                )

        if not policy.can_enqueue():
            return

        if not state.should_auto_optimize(context_id, cfg.get("optimization_interval_messages", 12)):
            return

        context_state = state.load_context_state(context_id)
        if context_state.get("optimization_running"):
            return

        # Queue optimization in the coordinator to avoid blocking message flow.
        queued = scheduler.schedule_optimization_job(context_id=context_id, cfg=cfg, force=False)
        if queued.get("dispatched", False):
            from usr.plugins.dspy_rlm.helpers.worker_supervisor import reconcile
            await asyncio.to_thread(reconcile, cfg)
