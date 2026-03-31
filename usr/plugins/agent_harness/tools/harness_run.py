from __future__ import annotations

from helpers.tool import Response, Tool

from usr.plugins.agent_harness.helpers import runtime


def _response(message: str) -> Response:
    return Response(message=message, break_loop=False)


class HarnessRun(Tool):
    async def execute(self, action: str = "status", **kwargs) -> Response:
        settings = runtime.load_agent_settings(self.agent)
        action = str(action or "status").strip().lower()
        run = runtime.get_current_run(self.agent)

        if action == "start":
            mode = str(kwargs.get("mode", settings.get("default_deep_mode", "build"))).strip().lower()
            run = runtime.create_run_record(
                context_id=self.agent.context.id,
                mode=mode,  # type: ignore[arg-type]
                objective=str(kwargs.get("objective", "")).strip(),
                constraints=runtime.coerce_constraints(kwargs.get("constraints", [])),
                settings=settings,
                allow_broad_edits=bool(kwargs.get("allow_broad_edits", False)),
            )
            runtime.save_current_run(self.agent.context, run)
            return _response(f"Harness run started in {run.mode} mode for: {run.objective}")

        if not run:
            return _response("No active harness run is available.")

        if action == "phase":
            phase = str(kwargs.get("phase", "")).strip().lower()
            if phase:
                run.phase = phase  # type: ignore[assignment]
                if run.status != "blocked":
                    run.status = "active"
            runtime.save_current_run(self.agent.context, run)
            return _response(f"Harness phase updated to {run.phase}.")

        if action == "plan":
            from usr.plugins.agent_harness.helpers.planner import submit_plan
            sub_tasks = kwargs.get("sub_tasks", [])
            if not isinstance(sub_tasks, list):
                return _response("plan action requires a 'sub_tasks' list.")
            try:
                graph = submit_plan(run, sub_tasks)
            except ValueError as exc:
                return _response(f"Plan rejected: {exc}")
            run.phase = "implement"
            runtime.save_current_run(self.agent.context, run)
            titles = [t.title for t in graph.sub_tasks]
            return _response(f"Plan accepted with {len(titles)} tasks: {', '.join(titles)}")

        if action == "dispatch":
            from usr.plugins.agent_harness.helpers.orchestrator import (
                dispatch_ready_tasks, build_scoped_context,
            )
            dispatched = dispatch_ready_tasks(run, settings)
            runtime.save_current_run(self.agent.context, run)
            if not dispatched:
                if run.task_graph and run.task_graph.is_complete():
                    run.phase = "verify"
                    runtime.save_current_run(self.agent.context, run)
                    return _response("All sub-tasks complete. Moving to verification phase.")
                return _response("No tasks ready to dispatch.")
            instructions = []
            for task in dispatched:
                ctx = build_scoped_context(task, run)
                instructions.append(
                    f"Dispatch '{task.title}' (id={task.id}) via call_subordinate with message:\n{ctx}"
                )
            return _response("\n\n".join(instructions))

        if action == "task":
            title = str(kwargs.get("task_title", "")).strip() or "Harness task"
            status = str(kwargs.get("task_status", "active")).strip() or "active"
            details = str(kwargs.get("task_details", "")).strip()
            runtime.upsert_task(run, title=title, status=status, details=details)
            runtime.save_current_run(self.agent.context, run)
            return _response(f"Tracked harness task: {title} ({status}).")

        if action == "verification":
            name = str(kwargs.get("verification_name", "")).strip() or "Verification"
            status = str(kwargs.get("verification_status", "unknown")).strip().lower()
            summary = str(kwargs.get("verification_summary", "")).strip() or name
            runtime.record_verification(
                run,
                name=name,
                status=status,  # type: ignore[arg-type]
                summary=summary,
            )
            runtime.save_current_run(self.agent.context, run)
            return _response(f"Recorded harness verification: {name} ({status}).")

        if action == "failure":
            summary = str(kwargs.get("failure_summary", "")).strip() or "Harness failure noted."
            runtime.record_failure(
                run,
                summary=summary,
                settings=settings,
            )
            runtime.save_current_run(self.agent.context, run)
            return _response(summary)

        if action == "complete":
            runtime.complete_run(run)
            runtime.save_current_run(self.agent.context, run)
            return _response(f"Harness run completed for: {run.objective}")

        if action == "status":
            summary = runtime.summarize_run(run)
            return _response(
                f"Harness status: mode={summary['mode']} "
                f"phase={summary['phase']} status={summary['status']}"
            )

        return _response(f"Unknown harness_run action '{action}'.")
