**Repository Solver Tool**

This tool solves coding problems in git repositories using subordinate agents.

**Arguments:**
- `mode` (string, required): Operation mode
  - "identify_tests": Find regression tests
  - "solve": Generate solution patch
  - "run_tests": Execute tests
- `git_dir` (string, required): Repository directory path
- `base_commit` (string, required): Base commit hash
- `problem_statement` (string, required): Problem description
- `test_description` (string): Testing requirements
- `timeout` (integer): Execution timeout in seconds (default: 3600)
- `instance_id` (string): Unique identifier for this solving session

**Workflow:**
1. identify_tests: Analyze repo, find relevant tests
2. solve: Generate solution, create diff
3. run_tests: Execute tests, report results

**Example:**
```json
{
  "thoughts": [
    "I need to solve a bug in this repository",
    "First, identify the regression tests"
  ],
  "tool_name": "repo_solver_tool",
  "tool_args": {
    "mode": "identify_tests",
    "git_dir": "/path/to/repo",
    "base_commit": "abc123",
    "problem_statement": "Fix authentication bug where users can't login",
    "instance_id": "auth_bug_001"
  }
}
```

{{operation}}
{{git_dir}}
{{problem_statement}}
