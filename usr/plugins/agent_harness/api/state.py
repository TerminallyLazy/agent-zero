from __future__ import annotations

from helpers.api import ApiHandler, Request, Response

from usr.plugins.agent_harness.helpers import runtime


class State(ApiHandler):
    async def process(self, input: dict, request: Request) -> dict | Response:
        context_id = str(input.get("context_id", "")).strip()
        context = self.use_context(context_id, create_if_not_exists=False)
        settings = runtime.load_context_settings(context)
        run = runtime.get_current_run(context)

        recent_rules = list(reversed(settings.get("accepted_rules", [])))[:5]
        latest_verification = runtime.latest_verification_record(run) if run else None

        return {
            "success": True,
            "context_id": context.id,
            "dashboard": runtime.dashboard_settings(settings),
            "run": run.model_dump() if run else None,
            "pending_checkpoints": [
                checkpoint.model_dump() for checkpoint in runtime.pending_checkpoints(run)
            ] if run else [],
            "pending_memory_candidates": [
                candidate.model_dump() for candidate in runtime.proposed_memory_candidates(run)
            ] if run else [],
            "recent_rules": recent_rules,
            "latest_verification": latest_verification.model_dump() if latest_verification else None,
        }
