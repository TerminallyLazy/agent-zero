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
- `swe_code_gen`: plan-based code generation with file writes and validation
  - Args:
    - `plan_items`: list of steps
    - `files`: list of { path, content } to write
    - `dry_run` ("true"/"false", default "false")
    - `write_tests` ("true"/"false")
    - `write_docs` ("true"/"false")
    - `create_validation` ("true"/"false", default "true")
    - `run_validation` ("true"/"false", default "true")
    - `validation_path` (default "scripts/validate_swe_changes.py")
    - `validation_code` (optional custom script content)
    - `validation_cmd` (optional custom shell command to run validation)
- `swe_testing`: test runner and coverage helper
  - Args:
    - `install_deps` ("true"/"false")
    - `install_command` (e.g., "pip install -e .[dev]" or "pnpm install")
    - `test_command` (e.g., "pytest -q" or "pnpm test")
    - `coverage_command` (optional, e.g., "pytest --cov")
    - `parse_summary` ("true"/"false", default "true")
    - `failures_top_n` (int, default 5)
- `swe_code_review`: static checks and basic grep-based findings
  - Args:
    - `target_paths`: list of paths to scan (default ["." ])
    - `ruleset` (string, default "default")
    - `max_findings` (int, default 50)
    - `run` ("true"/"false", default "true") to execute checks via CodeExecution
    - `patterns` (list of regex strings) to customize findings
    - `include_exts` (list of file extensions to include, e.g., ["py","ts"])
- `swe_docs`: documentation generator for API/ADR/runbooks
  - Args:
    - `docs`: list of { path, content } to write
    - `target_dir` (default "docs")
    - `ensure_index` ("true"/"false", default "true")
    - `template` (optional: "api" | "adr" | "runbook")

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
### End-to-end example

1) Analyze repository
```json
{
  "thoughts": ["Analyze repo to identify tech stack and tests"],
  "tool_name": "swe_repo_analysis",
  "tool_args": {
    "target_path": ".",
    "analysis_depth": "medium",
    "run": "true"
  }
}
```

2) Plan and dry-run code generation
```json
{
  "thoughts": ["Plan changes and preview file writes"],
  "tool_name": "swe_code_gen",
  "tool_args": {
    "plan_items": [
      "Add utility module for parsing",
      "Expose CLI entrypoint",
      "Add unit tests"
    ],
    "files": [
      { "path": "src/utils/parser.py", "content": "def parse(x): return x" },
      { "path": "tests/test_parser.py", "content": "def test_parse(): assert True" }
    ],
    "dry_run": "true",
    "create_validation": "true",
    "run_validation": "false"
  }
}
```

3) Apply code generation and run validation
```json
{
  "thoughts": ["Apply file writes and run validation script"],
  "tool_name": "swe_code_gen",
  "tool_args": {
    "plan_items": [],
    "files": [
      { "path": "src/utils/parser.py", "content": "def parse(x): return x" },
      { "path": "tests/test_parser.py", "content": "def test_parse(): assert True" }
    ],
    "dry_run": "false",
    "create_validation": "true",
    "run_validation": "true",
    "validation_path": "scripts/validate_swe_changes.py"
  }
}
```

4) Run tests and summarize results
```json
{
  "thoughts": ["Run unit tests with coverage and summarize"],
  "tool_name": "swe_testing",
  "tool_args": {
    "install_deps": "true",
    "install_command": "pip install -e .[dev]",
    "test_command": "pytest -q",
    "coverage_command": "pytest --cov",
    "parse_summary": "true",
    "failures_top_n": 5
  }
}
```

5) Static code review (non-destructive)
```json
{
  "thoughts": ["Run grep-based static checks"],
  "tool_name": "swe_code_review",
  "tool_args": {
    "target_paths": ["src", "tests"],
    "ruleset": "default",
    "max_findings": 50,
    "run": "true",
    "include_exts": ["py"],
    "patterns": [
      "TODO",
      "FIXME",
      "password\\s*=",
      "secret",
      "PRIVATE KEY"
    ]
  }
}
```

6) Generate docs
```json
{
  "thoughts": ["Write minimal API and ADR docs"],
  "tool_name": "swe_docs",
  "tool_args": {
    "target_dir": "docs",
    "ensure_index": "true",
    "docs": [
      { "path": "API.md", "content": "# API\\n\\n- parse(x): returns x" },
      { "path": "adr/0001-initial-decision.md", "content": "# ADR: Parser\\n\\nContext, Decision, Consequences." }
    ]
  }
}
```

### Delegation orchestration example

Use Delegation to split planner/programmer/reviewer flows while keeping the swe-agent profile:

```json
{
  "thoughts": ["Delegate planning to subordinate agent with the swe profile"],
  "tool_name": "call_subordinate",
  "tool_args": {
    "prompt_profile": "swe-agent",
    "message": "Planner: Analyze the repository and propose a 3-step plan to add a parser utility, tests, and docs."
  }
}
```

You can follow up with additional Delegation calls for programmer and reviewer roles, each time setting "prompt_profile": "swe-agent" and providing the appropriate role-specific message context.
