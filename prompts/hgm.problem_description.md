# HGM Problem Description Generator

You are formatting diagnostic analysis into an actionable GitHub issue for the coding agent repository.

## Agent Implementation Summary

{{agent_summary}}

## Diagnostic Analysis

The following analysis has been performed on a failed agent run:

{{diagnosis}}

## Your Task

Convert the `implementation_suggestion` and `improvement_proposal` from the diagnosis into a well-formatted GitHub issue.

## GitHub Issue Format

Create a professional, actionable GitHub issue with:

### Title
- Clear, specific, action-oriented
- Format: "Improve [component] to [outcome]" or "Fix [issue] in [component]"
- Example: "Improve patch generation validation to prevent empty outputs"

### Body Structure

```markdown
## Problem

[Describe the current limitation/issue based on the diagnosis]
[Include specific failure mode if relevant]

## Root Cause

[Explain why this issue occurs based on the analysis]

## Proposed Solution

[Detail the implementation suggestion]
[Break down into concrete steps]

### Implementation Steps

1. [First step with file/function references]
2. [Second step with specific changes]
3. [Validation/testing step]

## Expected Impact

[Describe how this will improve agent performance]
[Quantify if possible: "Should reduce empty patches by X%"]

## Technical Details

**Files to modify:**
- `path/to/file1.py`: [brief description of changes]
- `path/to/file2.py`: [brief description of changes]

**New functionality:**
- [List any new functions/classes needed]

**Testing:**
- [How to verify the fix works]

## Priority

[High/Medium/Low based on impact]

## Labels

`enhancement`, `agent-improvement`, [other relevant labels]
```

## Guidelines

1. **Be specific**: Reference actual files, functions, and code locations
2. **Be actionable**: Someone should be able to implement this directly
3. **Be professional**: Use clear, technical language
4. **Be complete**: Include all necessary context
5. **Focus on impact**: Explain why this matters

## Example Output

```markdown
## Improve Subordinate Agent Validation to Prevent Empty Patches

## Problem

The coding agent frequently completes problem-solving tasks without generating any code changes (empty patches). Analysis shows this occurs when subordinate agents are delegated tasks but fail to make actual file modifications, yet return success responses.

## Root Cause

The `sample_child()` function in `hgm_utils.py` delegates improvement implementation to subordinate agents via the Delegation tool, but does not verify that the subordinate actually made changes before accepting the result. The agent assumes that if the subordinate doesn't error, changes were made.

## Proposed Solution

Add explicit validation after subordinate agent execution to verify that git shows actual changes before accepting the result.

### Implementation Steps

1. Modify `sample_child()` in `python/helpers/hgm_utils.py`:
   - After `delegation.execute()`, run `git diff HEAD` to check for changes
   - If diff is empty, log warning and retry with more explicit instructions
   - Add parameter `require_changes=True` to enforce validation

2. Update retry logic to be more specific:
   - On retry, add explicit instruction: "You MUST make file modifications"
   - Include validation step in subordinate prompt
   - Fail after max_attempts with clear error

3. Add test in `test_hgm_utils.py`:
   - Test that empty patches are detected and retried
   - Verify max_attempts behavior

## Expected Impact

Should eliminate ~80% of empty patch failures seen in testing, particularly on problems where the agent understands what to do but delegates to a subordinate that doesn't follow through.

## Technical Details

**Files to modify:**
- `python/helpers/hgm_utils.py`: Add git diff validation in `sample_child()`
- `tests/unit/test_hgm_utils.py`: Add test for empty patch detection

**New functionality:**
- `_verify_changes_made(git_dir, parent_commit)` helper function
- Retry logic with progressively more explicit prompts

**Testing:**
- Create test case where subordinate returns success but makes no changes
- Verify retry behavior and error handling

## Priority

High - This is a major failure mode affecting agent performance

## Labels

`enhancement`, `agent-improvement`, `critical`, `patch-generation`
```

## Output Format

Return ONLY the formatted GitHub issue content (markdown), no JSON wrapper.
