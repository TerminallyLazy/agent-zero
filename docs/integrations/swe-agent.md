## SWE Agent Integration

This profile adds a specialized SWE-focused agent using Agent Zero's prompt/profile system.

### Activation
- Set `AgentConfig.prompts_subdir = "swe-agent"`
- Prompts fall back to defaults for any missing files

### Tools
The following SWE tools are provided and follow the Tool contract:
- `swe_repo_analysis`: read-only repository analysis and structure summary
  - Args:
    - `target_path` (default ".")
    - `analysis_depth` ("shallow" | "medium" | "deep")
    - `generate_summary` ("true"/"false")
    - `run` ("true"/"false") to execute a quick non-destructive scan via CodeExecution
- `swe_code_gen`: plan-based code generation with test/docs flags
  - Args:
    - `plan_items`: list of steps
    - `write_tests` ("true"/"false")
    - `write_docs` ("true"/"false")
- `swe_testing`: test runner and coverage helper
  - Args:
    - `install_deps` ("true"/"false")
    - `install_command` (e.g., "pip install -e .[dev]" or "pnpm install")
    - `test_command` (e.g., "pytest -q" or "pnpm test")
    - `coverage_command` (optional, e.g., "pytest --cov")
- `swe_code_review`: static checks and basic grep-based findings
  - Args:
    - `target_paths`: list of paths to scan (default ["." ])
    - `ruleset` (string, default "default")
    - `max_findings` (int, default 50)
    - `run` ("true"/"false", default "true") to execute checks via CodeExecution
    - `patterns` (list of regex strings) to customize findings
- `swe_docs`: documentation generator for API/ADR/runbooks

All tools inherit from `python/helpers/tool.py`, return `Response(message, break_loop)`, and integrate with lifecycle logging.

### Orchestration and Execution
- Use Delegation for splitting roles (planner/programmer/reviewer) if needed
- Uses CodeExecution for safe command execution (runtime="terminal") rather than direct OS calls

### Communication Protocol
- Strict JSON responses with fields: `thoughts[]`, `tool_name`, `tool_args`
- No text outside JSON

### Recommended Usage
- Start with `swe_repo_analysis` to build context
- Plan with `swe_code_gen` and then implement using file operation tools
- Validate using `swe_testing`, then review with `swe_code_review`
- Update docs with `swe_docs`
