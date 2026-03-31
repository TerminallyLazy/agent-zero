from __future__ import annotations

from helpers.extension import Extension
from helpers.tool import Response

from usr.plugins.agent_harness.helpers import runtime


class HarnessToolEvents(Extension):
    async def execute(
        self,
        tool_name: str = "",
        response: Response | None = None,
        **kwargs,
    ):
        if not self.agent:
            return
        run = runtime.get_current_run(self.agent)
        if not run:
            return
        current_tool = self.agent.loop_data.current_tool
        tool_args = current_tool.args if current_tool else {}
        runtime.record_tool_activity(
            run=run,
            tool_name=tool_name,
            tool_args=tool_args,
            tool_response=response.message if response else "",
        )
        # Task graph: match call_subordinate results to dispatched sub-tasks
        if tool_name == "call_subordinate" and run.task_graph:
            from usr.plugins.agent_harness.helpers.orchestrator import record_dispatch_result
            message = str(tool_args.get("message", "")).strip()
            tool_response_str = response.message if response else ""
            for task in run.task_graph.sub_tasks:
                if task.status == "dispatched" and (task.id in message or task.title in message):
                    record_dispatch_result(run, task.id, {
                        "summary": tool_response_str[:500] if tool_response_str else "",
                        "files": [],
                        "status": "completed",
                    })
                    break
            if run.task_graph.is_complete():
                run.phase = "verify"
        runtime.save_current_run(self.agent.context, run)
