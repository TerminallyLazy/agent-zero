**Diagnostic Analysis Tool**

Analyzes agent performance and generates targeted improvement patches using multiple diagnostic strategies.

**Arguments:**
- `strategy` (string, required): Diagnostic strategy to use
  - "swe": Software engineering best practices analysis
  - "empty_patch": Generate baseline patch for comparison
  - "stochasticity": Address non-deterministic behavior
  - "contextlength": Optimize context window usage
  - "polyglot": Multi-language code analysis
  - "problem_description": Analyze problem understanding
- `git_dir` (string, required): Repository directory path
- `base_commit` (string, required): Commit hash to analyze from
- `task_id` (string, optional): Specific task to analyze
- `failure_info` (dict, optional): Information about test failures
  - `error_message`: The error that occurred
  - `stack_trace`: Full stack trace
  - `test_name`: Name of failed test
- `problem_statement` (string, optional): Description of the problem to solve
- `test_description` (string, optional): Description of testing requirements
- `timeout` (integer, optional): Analysis timeout in seconds (default: 1800)

**Diagnostic Strategies:**

1. **swe** (Software Engineering):
   - Analyzes code quality and best practices
   - Identifies architectural issues
   - Suggests refactoring opportunities
   - Use when: General code improvement needed

2. **empty_patch**:
   - Generates minimal baseline patch
   - Used for A/B testing improvements
   - Establishes control conditions
   - Use when: Need baseline for comparison

3. **stochasticity**:
   - Analyzes non-deterministic behavior
   - Identifies race conditions
   - Addresses random failures
   - Use when: Tests pass/fail inconsistently

4. **contextlength**:
   - Optimizes context window usage
   - Reduces token consumption
   - Improves memory efficiency
   - Use when: Context limits are an issue

5. **polyglot**:
   - Multi-language code analysis
   - Cross-language integration issues
   - Language-specific optimizations
   - Use when: Multiple programming languages involved

6. **problem_description**:
   - Analyzes problem understanding
   - Clarifies requirements
   - Identifies specification gaps
   - Use when: Requirements are unclear

**Output:**
Returns a patch (git diff) with suggested improvements based on the diagnostic analysis.

**Workflow Example:**
```json
{
  "thoughts": [
    "The agent failed on task_042 with an unclear error",
    "Let me run SWE diagnostic to analyze the code"
  ],
  "tool_name": "diagnostic_tool",
  "tool_args": {
    "strategy": "swe",
    "git_dir": "/path/to/repo",
    "base_commit": "abc123",
    "task_id": "task_042",
    "failure_info": {
      "error_message": "AssertionError: Expected 5, got 3",
      "test_name": "test_calculation"
    }
  }
}
```

```json
{
  "thoughts": [
    "Tests are failing randomly",
    "This looks like a stochasticity issue"
  ],
  "tool_name": "diagnostic_tool",
  "tool_args": {
    "strategy": "stochasticity",
    "git_dir": "/path/to/repo",
    "base_commit": "def456",
    "problem_statement": "Random test failures in concurrent operations"
  }
}
```

**Integration with HGM:**
This tool is used internally by HGM during the expand operation to generate improvement patches.
The strategy is selected based on configuration weights.

**Important Notes:**
- Each strategy uses specialized prompts in prompts/hgm.diagnostic.*.md
- Diagnostic analysis uses subordinate agents for deep code analysis
- Results are returned as git patches that can be applied directly
- Multiple strategies can be tried sequentially if first attempt fails
