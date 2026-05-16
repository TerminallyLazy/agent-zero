### delegate_parallel
Spawn multiple subagents to work on independent tasks in parallel. Each agent runs concurrently in its own isolated context and returns its result when done. Use this when a task decomposes into independent subtasks with no sequential dependency between them.

All tasks in one `delegate_parallel` call share a single swarm run. Agents in the same run can message each other and the orchestrator with `swarm_message`. Use meaningful `label` values — the swarm panel uses them for observability.

Args:
- `tasks` (list, required): array of task objects. Each object:
  - `label` (string, required): human-readable name shown in the swarm panel (e.g. "Researcher", "Code Writer").
  - `task` (string, required): full task description for that agent.
  - `profile` (string, optional): Agent Zero profile for a local subagent.
  - `endpoint` (string, optional): route this task to a configured remote A2A Agent Zero instance by its settings `label` or a full `http(s)://host:port` URL. Test remotes in Plugin Settings before relying on them.

Returns: a structured markdown summary of all agent results once every agent completes.

Example:
~~~json
{
  "thoughts": ["I'll split this into research and implementation tasks."],
  "tool_name": "delegate_parallel",
  "tool_args": {
    "tasks": [
      {"label": "Researcher", "task": "Research the top 5 Python async frameworks and summarize their tradeoffs."},
      {"label": "Implementer", "task": "Write a working FastAPI hello-world server with JWT auth."}
    ]
  }
}
~~~
