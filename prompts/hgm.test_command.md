# HGM Test Command Generator

You are generating test execution instructions for evaluating a coding agent's solution.

## Repository Context

{{repo_context}}

## Test Information

{{test_info}}

## Your Task

Generate clear, precise instructions for running tests to validate the agent's solution.

### For SWE-bench Repositories

Format the test command with:
- Exact command-line arguments required
- File path notation: Use `<file>` placeholder for test files
- Example: `pytest <file> -xvs`
- Include any necessary environment setup

**Important**:
- Do NOT modify the test command structure
- Keep all specified command-line options
- Use the exact test framework command (pytest, npm test, etc.)

### For Polyglot Repositories

Provide the evaluation script exactly as specified:
```
{{eval_script}}
```

### For HGM Self-Improvement Tests

Use pytest with these constraints:
```bash
pytest <file> -xvs
```

**Restrictions**:
- Do NOT test `python/tools/call_subordinate.py`
- Do NOT test `python/tools/diagnostic_tool.py`
- Do NOT test `python/tools/git_operations_tool.py`
- Focus only on the modified components

## Output Format

Return your test instructions in this format:

```markdown
## Test Command

[Exact command to run]

## Pre-requisites

[Any setup needed before running tests]

## Expected Output

[What success looks like]

## Notes

[Any important warnings or considerations]
```

## Examples

### Example 1: SWE-bench Python Repository
```markdown
## Test Command

pytest tests/test_module.py::test_function -xvs

## Pre-requisites

- Ensure virtual environment is activated
- Install dependencies: pip install -r requirements.txt

## Expected Output

All tests should pass with no failures.

## Notes

The -xvs flags enable: stop on first failure (x), verbose output (v), no capture (s)
```

### Example 2: Polyglot Go Repository
```markdown
## Test Command

go test -v ./...

## Pre-requisites

- Go 1.19+ installed
- Dependencies fetched: go mod download

## Expected Output

All test cases pass, showing "PASS" for each test

## Notes

The -v flag enables verbose output showing each test name
```

### Example 3: HGM Self-Improvement Test
```markdown
## Test Command

pytest tests/unit/test_hgm_utils.py -xvs

## Pre-requisites

- Agent Zero environment setup
- Test fixtures initialized

## Expected Output

15/15 tests passing

## Notes

Do not test subordinate delegation or diagnostic tools directly
```
