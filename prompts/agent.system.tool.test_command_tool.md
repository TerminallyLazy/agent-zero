**Test Command Generation Tool**

Analyzes repository structure and generates appropriate test execution commands.

**Arguments:**
- `git_dir` (string, required): Repository directory path
- `base_commit` (string, required): Commit hash to analyze from
- `test_description` (string, optional): Specific testing requirements or focus areas
- `test_type` (string, optional): Type of tests to run
  - "unit": Unit tests only
  - "integration": Integration tests
  - "all": All available tests (default)
- `timeout` (integer, optional): Command generation timeout in seconds (default: 300)

**Detection Capabilities:**
Automatically detects test framework and generates appropriate commands for:
- Python: pytest, unittest, nose, tox
- JavaScript/TypeScript: jest, mocha, jasmine, vitest, npm test
- Java: JUnit, maven, gradle
- Go: go test
- Ruby: RSpec, minitest
- Rust: cargo test
- And many more...

**Output:**
Returns structured test command information:
```json
{
  "command": "pytest tests/ -v --tb=short",
  "framework": "pytest",
  "test_directory": "tests/",
  "additional_flags": ["-v", "--tb=short"],
  "environment_setup": ["pip install -r requirements.txt"],
  "description": "Run all pytest tests with verbose output"
}
```

**Workflow Example:**
```json
{
  "thoughts": [
    "I need to run tests for this Python repository",
    "Let me generate the appropriate test command"
  ],
  "tool_name": "test_command_tool",
  "tool_args": {
    "git_dir": "/path/to/repo",
    "base_commit": "abc123",
    "test_description": "Run unit tests for authentication module"
  }
}
```

```json
{
  "thoughts": [
    "Need to verify JavaScript integration tests",
    "Generate command for integration tests only"
  ],
  "tool_name": "test_command_tool",
  "tool_args": {
    "git_dir": "/path/to/js-repo",
    "base_commit": "def456",
    "test_type": "integration"
  }
}
```

**Integration with HGM:**
This tool is used during agent evaluation to:
- Determine how to run tests for task verification
- Generate consistent test commands across different repositories
- Ensure proper test execution in diverse environments

**Important Notes:**
- Analyzes repository files (package.json, setup.py, pom.xml, etc.)
- Generates language-appropriate commands automatically
- Includes necessary environment setup steps
- Respects existing test configurations
- Uses hgm.test_command.md prompt template for analysis
