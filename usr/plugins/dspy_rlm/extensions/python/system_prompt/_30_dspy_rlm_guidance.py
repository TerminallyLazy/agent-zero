"""Inject one validated, active DSPy RLM guidance artifact when explicitly enabled."""
from __future__ import annotations

from typing import Any

from helpers.extension import Extension

from usr.plugins.dspy_rlm.helpers import config as config_module
from usr.plugins.dspy_rlm.helpers import guidance, state
from usr.plugins.dspy_rlm.helpers.runtime_policy import RuntimePolicy


class DspyRlmGuidance(Extension):
    """System-prompt seam for fixed-rendered, SQLite-selected guidance only."""

    async def execute(
        self,
        system_prompt: list[str] = [],
        loop_data: Any = None,
        **kwargs: Any,
    ) -> None:
        if not self.agent:
            return

        # Injection has an independent explicit policy gate.  In particular it
        # does not depend on capture, auto-enqueue, or optimizer enablement.
        cfg = config_module.load_config(self.agent)
        if not RuntimePolicy.from_config(cfg).can_inject():
            return

        context_id = str(getattr(self.agent.context, "id", "") or "")
        if not context_id:
            return
        context_state = state.load_context_state(context_id)
        objective_bucket = str(context_state.get("last_objective_bucket") or "reasoning")
        artifact = guidance.select_active_guidance_artifact(context_id, objective_bucket)
        if artifact is None:
            return

        prompt_config = cfg.get("prompt") if isinstance(cfg, dict) else {}
        configured_limit = prompt_config.get("max_injected_chars", guidance.MAX_RENDERED_CHARS) if isinstance(prompt_config, dict) else guidance.MAX_RENDERED_CHARS
        try:
            max_chars = min(int(configured_limit), guidance.MAX_RENDERED_CHARS)
            block = guidance.render_guidance_artifact(artifact, max_chars=max_chars)
        except (TypeError, ValueError, guidance.GuidanceValidationError):
            # Prompt construction must fail closed without affecting the core loop.
            return
        if block:
            system_prompt.append(block)
