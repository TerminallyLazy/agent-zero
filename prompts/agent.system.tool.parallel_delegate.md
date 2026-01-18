### parallel_delegate

Delegate complex tasks to multiple subordinate agents working in parallel with coordination and review.

**Key benefit:** Multiple agents work simultaneously on independent tasks. Each task is reviewed and verified before being signed off as complete. Results are only accepted when correct.

**When to use:**
- Task can be decomposed into independent or loosely dependent sub-tasks
- Sub-tasks can be worked on simultaneously by different agents
- You need faster completion through parallelization
- The work involves code changes that benefit from isolated workspaces
- You want automatic review/verification of each sub-task before acceptance

**Task breakdown requirements:**
Each task in the breakdown must have:
- `id`: Unique identifier (e.g., "task_001", "frontend", "api")
- `description`: Clear description of what the task accomplishes
- `profile`: (optional) Agent profile to use (default: "default")
- `dependencies`: (optional) List of task IDs that must complete first

**Coordination modes:**
- `scratchpad`: Memory-based coordination only (good for non-code tasks)
- `git_worktree`: Isolated git workspaces per agent (required for code changes)
- `both`: Use both mechanisms (recommended for complex projects)

**Merge strategies:**
- `sequential`: Merge branches one by one in dependency order (safer)
- `parallel_safe`: Merge independent branches together (faster)

**Your responsibilities as orchestrator:**
1. Break down the task into clear, independent sub-tasks
2. Identify dependencies between tasks accurately
3. Choose appropriate coordination mode
4. Review the consolidated results after completion

**Example usage:**
~~~json
{
    "thoughts": [
        "This web application needs frontend, backend, and database work",
        "Frontend and backend can be developed in parallel",
        "Integration requires both to be complete first",
        "I'll use git worktrees to prevent conflicts"
    ],
    "tool_name": "parallel_delegate",
    "tool_args": {
        "task_breakdown": [
            {
                "id": "frontend",
                "description": "Create React frontend with login page, dashboard, and user settings",
                "profile": "developer",
                "dependencies": []
            },
            {
                "id": "backend",
                "description": "Build Express.js REST API with authentication and user endpoints",
                "profile": "developer",
                "dependencies": []
            },
            {
                "id": "database",
                "description": "Design and implement PostgreSQL schema for users and sessions",
                "profile": "developer",
                "dependencies": []
            },
            {
                "id": "integration",
                "description": "Connect frontend to backend API and test end-to-end flow",
                "profile": "developer",
                "dependencies": ["frontend", "backend", "database"]
            }
        ],
        "coordination_mode": "both",
        "merge_strategy": "sequential"
    }
}
~~~

**Sub-agent coordination:**
- Each sub-agent automatically receives coordination context
- Sub-agents check file registry before modifying shared files
- Sub-agents update scratchpad with their progress
- File conflicts are detected and blocked to prevent merge issues

**Review and sign-off process:**
- Each sub-agent completes their task and reports results
- Tasks are only marked complete when work is verified correct
- If issues are found, the sub-agent fixes them before sign-off
- You (the orchestrator) review the consolidated results after all tasks complete
- Only successful, reviewed work is merged back

**Project requirement:**
This tool requires an active project context. Create or select a project before using parallel delegation.
