### Planning with harness_run

When the harness is in `plan` phase, decompose the objective into sub-tasks using `harness_run action="plan"`.

Each sub-task should be independently executable by a sub-agent. Use roles:
- `research`: gather information, read docs, explore code
- `code`: implement features, fix bugs, write code
- `verify`: run tests, validate output
- `synthesize`: combine results from other sub-tasks

Reference dependencies by index (0-based). Example:

~~~json
{
  "tool_name": "harness_run",
  "tool_args": {
    "action": "plan",
    "sub_tasks": [
      {"title": "Research Stripe API", "description": "Read webhook documentation", "role": "research"},
      {"title": "Implement handler", "description": "Write webhook endpoint", "role": "code", "depends_on": [0]},
      {"title": "Write tests", "description": "Test the handler", "role": "verify", "depends_on": [1]}
    ]
  }
}
~~~

After planning, use `action="dispatch"` to get dispatch instructions for ready sub-tasks.
