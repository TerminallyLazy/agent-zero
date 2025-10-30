# HGM Diagnostic Analysis - Empty Patch

You are an expert AI system analyzer diagnosing why a coding agent failed to generate any code changes.

## Agent Implementation Summary

The coding agent uses:
- **Tool-based architecture**: Async tools for git, repository operations
- **Subordinate agent delegation**: Spawns sub-agents for implementation
- **Problem-solving flow**: Analysis → Test identification → Patch generation

## Analysis Context

The agent was asked to solve a problem but generated NO code changes (empty patch).

### Running Log
```
{{log}}
```

### Problem Statement
```
{{issue}}
```

### Generated Patch
```
{{patch}}
```

### Test Results
```
{{results}}
```

## Required Analysis

Diagnose why NO patch was generated. Provide JSON with these fields:

### 1. log_summarization
- Did the agent understand the problem?
- Did it identify files to modify?
- Where in the process did it fail to generate changes?
- Did subordinate agents complete their work?

### 2. potential_improvements
List fixes for empty patch generation:
- Ensure subordinate agents make actual changes
- Verify modifications before completing
- Add validation that changes were made
- Improve problem understanding

### 3. improvement_proposal
Select the ONE most critical fix for empty patches:
- What specific change would ensure patches are generated?
- Why is this the root cause?

### 4. implementation_suggestion
Concrete steps to fix empty patch generation:
- Which tool/function needs modification?
- What validation should be added?
- How to ensure changes are made?

### 5. problem_description
Format as GitHub issue:
```
Title: Fix empty patch generation in [specific scenario]

Problem: Agent completes without making changes...
Solution: Add validation/checks to ensure...
Expected: Agent always generates patches when modifications are needed
```

## Response Format

```json
{
  "log_summarization": "...",
  "potential_improvements": ["...", "..."],
  "improvement_proposal": "...",
  "implementation_suggestion": "...",
  "problem_description": "..."
}
```

**Focus**: Ensure the agent actually implements the changes it identifies.
