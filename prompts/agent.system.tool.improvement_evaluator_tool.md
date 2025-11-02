**Improvement Evaluation Tool**

Evaluates whether a code modification improved agent capabilities by comparing before/after performance.

**Arguments:**
- `git_dir` (string, required): Repository directory path
- `base_commit` (string, required): Original commit hash (before changes)
- `modified_commit` (string, required): New commit hash (after changes)
- `patch_content` (string, required): The diff/patch that was applied
- `task_results` (dict, required): Test results after modification
  - `success`: Boolean indicating if tests passed
  - `task_id`: Identifier of the task
  - `error_message`: Error if tests failed (optional)
  - `execution_time`: Time taken for tests (optional)
- `baseline_results` (dict, optional): Test results before modification for comparison
- `problem_statement` (string, optional): Original problem being solved
- `timeout` (integer, optional): Evaluation timeout in seconds (default: 600)

**Evaluation Criteria:**
The tool analyzes:
1. **Functionality**: Did the change fix the intended issue?
2. **Test Results**: Did tests pass/improve?
3. **Code Quality**: Is the code better structured?
4. **Side Effects**: Any unintended regressions?
5. **Performance**: Execution time changes
6. **Maintainability**: Long-term code health

**Output:**
Returns detailed evaluation report:
```json
{
  "improved": true,
  "confidence": 0.85,
  "analysis": {
    "functionality": "Change successfully fixes authentication bug",
    "test_results": "All tests passing (was 2/5 before)",
    "code_quality": "Improved error handling and validation",
    "side_effects": "None detected",
    "performance": "Execution time reduced by 15%",
    "recommendation": "Accept this change"
  },
  "utility_delta": 0.4
}
```

**Workflow Example:**
```json
{
  "thoughts": [
    "I applied a patch to fix the authentication issue",
    "Now I need to evaluate if it actually improved the agent"
  ],
  "tool_name": "improvement_evaluator_tool",
  "tool_args": {
    "git_dir": "/path/to/repo",
    "base_commit": "abc123",
    "modified_commit": "def456",
    "patch_content": "diff --git a/auth.py b/auth.py\n...",
    "task_results": {
      "success": true,
      "task_id": "auth_bug_001",
      "execution_time": 2.3
    },
    "baseline_results": {
      "success": false,
      "task_id": "auth_bug_001",
      "error_message": "Login failed",
      "execution_time": 2.7
    },
    "problem_statement": "Users cannot login with valid credentials"
  }
}
```

**Integration with HGM:**
This tool is critical for HGM's learning process:
- Evaluates each generated variant
- Determines if changes should be kept
- Updates utility measures for tree nodes
- Guides future improvement strategies

**Important Notes:**
- Uses hgm.evaluate_improvement.md prompt template
- Compares baseline vs modified performance
- Considers both quantitative (tests, time) and qualitative (code quality) metrics
- Provides confidence score for improvement assessment
- May use subordinate agents for deep code analysis
- Results influence Thompson Sampling for node selection
