from __future__ import annotations

from helpers.api import ApiHandler, Request, Response

from usr.plugins.agent_harness.helpers import runtime


class Run(ApiHandler):
    async def process(self, input: dict, request: Request) -> dict | Response:
        action = str(input.get("action", "status")).strip().lower()
        context_id = str(input.get("context_id", "")).strip()
        context = self.use_context(context_id, create_if_not_exists=action == "start")

        if action == "start":
            settings = runtime.load_context_settings(context)
            run = runtime.create_run_record(
                context_id=context.id,
                mode=str(input.get("mode", runtime.get_default_mode(settings))).strip().lower(),  # type: ignore[arg-type]
                objective=str(input.get("objective", "")).strip(),
                constraints=runtime.coerce_constraints(input.get("constraints", [])),
                settings=settings,
                allow_broad_edits=bool(input.get("allow_broad_edits", False)),
            )
            runtime.save_current_run(context, run)
            return {"success": True, "context_id": context.id, "run": run.model_dump()}

        run = runtime.get_current_run(context)
        if not run:
            return {"success": False, "context_id": context.id, "run": None, "error": "No active harness run"}

        if action == "status":
            return {"success": True, "context_id": context.id, "run": run.model_dump()}

        if action == "checkpoint_decide":
            checkpoint = runtime.decide_checkpoint(
                run,
                checkpoint_id=str(input.get("checkpoint_id", "")).strip(),
                decision=str(input.get("decision", "")).strip().lower(),  # type: ignore[arg-type]
                comment=str(input.get("comment", "")).strip(),
            )
            runtime.save_current_run(context, run)
            return {
                "success": True,
                "context_id": context.id,
                "checkpoint": checkpoint.model_dump(),
                "run": run.model_dump(),
            }

        if action == "stop":
            runtime.stop_run(context)
            return {"success": True, "context_id": context.id, "run": None}

        return {"success": False, "context_id": context.id, "run": run.model_dump(), "error": f"Unknown action: {action}"}
