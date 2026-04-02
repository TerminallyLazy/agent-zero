from __future__ import annotations

from helpers.api import ApiHandler, Request, Response

from usr.plugins.agent_harness.helpers import runtime


class MemoryQueue(ApiHandler):
    async def process(self, input: dict, request: Request) -> dict | Response:
        action = str(input.get("action", "status")).strip().lower()
        context_id = str(input.get("context_id", "")).strip()
        context = self.use_context(context_id, create_if_not_exists=False)
        run = runtime.get_current_run(context)

        if not run:
            return {"success": False, "candidate": None, "error": "No active harness run"}

        if action == "accept":
            candidate = await runtime.accept_memory_candidate(
                context=context,
                candidate_id=str(input.get("candidate_id", "")).strip(),
                scope=str(input.get("scope", "project")).strip().lower(),  # type: ignore[arg-type]
                project_name=str(input.get("project_name", "")).strip(),
                agent_profile=str(input.get("agent_profile", "")).strip(),
            )
            refreshed_run = runtime.get_current_run(context)
            return {
                "success": True,
                "candidate": candidate.model_dump(),
                "run": refreshed_run.model_dump() if refreshed_run else None,
            }

        if action == "reject":
            candidate = runtime.reject_memory_candidate(
                run=run,
                candidate_id=str(input.get("candidate_id", "")).strip(),
            )
            runtime.save_current_run(context, run)
            return {"success": True, "candidate": candidate.model_dump(), "run": run.model_dump()}

        return {
            "success": True,
            "candidate": None,
            "run": run.model_dump(),
            "pending_candidates": [candidate.model_dump() for candidate in runtime.proposed_memory_candidates(run)],
        }
