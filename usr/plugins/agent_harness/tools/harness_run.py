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
            from usr.plugins.agent_harness.helpers.orchestrator import dispatch_ready_tasks
            from usr.plugins.agent_harness.helpers.parallel import spawn_parallel, active_count

            dispatched = dispatch_ready_tasks(run, settings)
            if not dispatched:
                if run.task_graph and run.task_graph.is_complete():
                    run.phase = "verify"
                    runtime.save_current_run(self.agent.context, run)
                    return _response("All sub-tasks complete. Moving to verification phase.")
                in_flight = active_count(run.run_id)
                if in_flight > 0:
                    runtime.save_current_run(self.agent.context, run)
                    return _response(
                        f"No new tasks ready to dispatch. {in_flight} sub-agent(s) still running. "
                        f'Use harness_run action="collect" to check progress.'
                    )
                return _response("No tasks ready to dispatch.")

            spawned = spawn_parallel(run, dispatched, settings, parent_context=self.agent.context)
            runtime.save_current_run(self.agent.context, run)
            titles = [t.title for t in dispatched]
            return _response(
                f"{len(spawned)} sub-agent(s) spawned in parallel: {', '.join(titles)}. "
                f'Use harness_run action="collect" to check progress and harvest results.'
            )

        if action == "collect":
            from usr.plugins.agent_harness.helpers.parallel import (
                poll_status, collect_completed, active_count,
            )
            from usr.plugins.agent_harness.helpers.planner import (
                mark_sub_task_completed, mark_sub_task_failed,
            )

            results = collect_completed(run)
            for task_id, summary, error in results:
                if error:
                    mark_sub_task_failed(run, task_id, error=error)
                else:
                    mark_sub_task_completed(run, task_id, summary=summary or "")

            in_flight = active_count(run.run_id)
            status_map = poll_status(run.run_id)
            runtime.save_current_run(self.agent.context, run)

            if run.task_graph and run.task_graph.is_complete():
                run.phase = "verify"
                runtime.save_current_run(self.agent.context, run)
                completed_count = len(results)
                return _response(
                    f"Collected {completed_count} result(s). All sub-tasks complete. "
                    f"Moving to verification phase."
                )

            lines = []
            if results:
                for task_id, summary, error in results:
                    status = "failed" if error else "completed"
                    detail = error if error else (summary[:80] if summary else "")
                    lines.append(f"  - {task_id}: {status} — {detail}")
            if in_flight > 0:
                running = [tid for tid, s in status_map.items() if s == "running"]
                lines.append(f"  Still running: {', '.join(running)}")
                lines.append('  Call harness_run action="collect" again to check progress.')
            else:
                ready = run.task_graph.ready_tasks() if run.task_graph else []
                if ready:
                    lines.append(
                        f"  {len(ready)} task(s) now ready to dispatch. "
                        f'Use harness_run action="dispatch" to continue.'
                    )

            return _response(
                f"Collected {len(results)} result(s), {in_flight} still running.\n"
                + "\n".join(lines)
            )

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

        if action == "clean":
            if run.workspace:
                from usr.plugins.agent_harness.helpers.workspace import clean_workspace
                clean_workspace(run.workspace)
                return _response("Workspace cleaned. Outputs and run logs preserved.")
            return _response("No workspace to clean.")

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
