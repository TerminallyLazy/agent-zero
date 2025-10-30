**Git Operations Tool**

This tool performs git operations on repositories.

**Arguments:**
- `operation` (string, required): Operation to perform
  - "diff": Generate diff against base commit
  - "apply_patch": Apply patch to repository
  - "reset": Reset repository to commit
  - "get_log": Get commit history
- `git_dir` (string, required): Path to git repository
- `base_commit` (string): Base commit for diff (default: HEAD)
- `patch_content` (string): Patch content for apply_patch
- `target_commit` (string): Target commit for reset
- `hard` (boolean): Whether to do hard reset
- `limit` (integer): Number of commits for get_log

**Example:**
```json
{
  "thoughts": [
    "I need to generate a diff of changes since the base commit",
    "Using git_operations_tool with diff operation"
  ],
  "tool_name": "git_operations_tool",
  "tool_args": {
    "operation": "diff",
    "git_dir": "/path/to/repo",
    "base_commit": "abc123def"
  }
}
```

{{error}}
