### harness_run
manage the active agent harness run — this is your primary workflow orchestration tool

#### WORKFLOW: plan → dispatch → collect → verify → complete
For any task that requires creating or modifying 2+ files:
1. Use `action="plan"` to decompose into sub-tasks FIRST
2. Use `action="dispatch"` to spawn parallel sub-agents for ready tasks
3. Use `action="collect"` to harvest results as sub-agents finish
4. Repeat dispatch/collect until all sub-tasks complete
5. Run tests and use `action="verification"` to record results
6. Use `action="complete"` to finish the run

Do NOT skip planning and implement everything yourself under normal conditions. Sub-agents run in parallel and are faster.
If sub-agent execution is unavailable or repeatedly failing, you may take over the work yourself and then use `action="adopt"` to reconcile the completed sub-task back into the graph.

#### harness_run actions
- `start`: begin a harness run with `mode`, `objective`, and optional `constraints`
- `phase`: update the current phase with `phase`
- `plan`: submit a task graph — REQUIRED before implementing multi-file work
- `dispatch`: spawn parallel sub-agents for ready tasks (up to mode's subagent_limit)
- `collect`: check progress and harvest results from parallel sub-agents
- `adopt`: mark a planned sub-task as completed manually using `sub_task_id`, optional `summary`, and optional `result_files`
- `task`: track a subtask using `task_title`, optional `task_status`, and optional `task_details`
- `verification`: record a verification result with `verification_name`, `verification_status` (must be "passed", "failed", or "unknown"), and `verification_summary`
- `failure`: note a failure summary when a repair loop needs context
- `complete`: mark the current run complete after verification and summary
- `status`: read back the current run state
- `clean`: remove temporary workspace files (keeps outputs and run logs)

usage:
~~~json
{
  "thoughts": [
    "This task requires multiple files. I need to plan before implementing."
  ],
  "headline": "Planning the implementation",
  "tool_name": "harness_run",
  "tool_args": {
    "action": "plan",
    "sub_tasks": [
      {"title": "Research existing patterns", "description": "Read the codebase to understand conventions", "role": "research"},
      {"title": "Implement core module", "description": "Create the main module with business logic", "role": "code", "depends_on": [0]},
      {"title": "Write tests", "description": "Create comprehensive tests", "role": "verify", "depends_on": [1]}
    ]
  }
}
~~~
