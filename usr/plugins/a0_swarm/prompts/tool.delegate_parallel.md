# delegate_parallel

Use `delegate_parallel` to split independent work across multiple swarm agents.

Arguments:

- `tasks`: list of task objects.
- Each task needs `label` and `task`.
- Optional `profile` selects an Agent Zero profile for a local subagent.
- Optional `endpoint` routes the task to a configured remote A2A Agent Zero endpoint by label or URL.

Guidance:

- Use meaningful labels. The swarm panel uses labels for operator observability.
- Tasks in one `delegate_parallel` call share a swarm run and can message each other with `swarm_message`.
- Subagents can message the orchestrator with `recipient="orchestrator"`.
- Remote endpoints must be tested in Plugin Settings before relying on them for long-running work.
