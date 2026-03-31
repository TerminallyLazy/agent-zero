### harness_run
manage the active agent harness run
use to start a deep run or keep its phase, tasks, verification, and completion state up to date

#### harness_run actions
- `start`: begin a harness run with `mode`, `objective`, and optional `constraints`
- `phase`: update the current phase with `phase`
- `task`: track a subtask using `task_title`, optional `task_status`, and optional `task_details`
- `verification`: record a verification result with `verification_name`, `verification_status`, and `verification_summary`
- `failure`: note a failure summary when a repair loop needs context
- `complete`: mark the current run complete after verification and summary
- `status`: read back the current run state
- `plan`: submit a task graph for the current objective with `sub_tasks` list
- `dispatch`: get dispatch instructions for ready sub-tasks (reads from task graph)

usage:
~~~json
{
  "thoughts": [
    "I should keep the harness state aligned with my execution plan."
  ],
  "headline": "Updating harness run status",
  "tool_name": "harness_run",
  "tool_args": {
    "action": "phase",
    "phase": "implement"
  }
}
~~~
