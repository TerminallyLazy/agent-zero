### delegate_parallel
Spawn multiple subagents to work on independent tasks in parallel. Each agent runs concurrently and returns its result when done. Use this when a task can be decomposed into independent subtasks that do not need to wait for each other.

**When to use:** The task has clearly separable subtasks with no sequential dependency between them.

**Args:**
- `tasks` (list, required): Array of task objects. Each object:
  - `label` (string): Human-readable name for this agent shown in the UI (e.g. "Research Agent", "Code Writer")
  - `task` (string): Full task description for this agent
  - `profile` (string, optional): Agent profile name to use

**Example:**
```json
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
```

**Returns:** A structured markdown summary of all agent results once all agents complete.
