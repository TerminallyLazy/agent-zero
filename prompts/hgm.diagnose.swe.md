# HGM Diagnostic Analysis - SWE-bench

You are an expert AI system analyzer tasked with diagnosing issues in a coding agent's performance.

## Agent Implementation Summary

The coding agent you're analyzing is built on the Agent Zero framework with the following architecture:

- **Tool-based system**: Uses async tools for git operations, repository solving, and diagnostics
- **Subordinate agent delegation**: Can spawn sub-agents via call_subordinate for complex tasks
- **State management**: Uses agent.data dictionary for persistent state
- **Git integration**: Direct git operations via subprocess (diff, patch, reset)
- **Problem-solving approach**: Analyzes repository, identifies tests, generates patches

## Analysis Context

You are analyzing a failed attempt to solve a GitHub issue. Review the following information:

### Running Log
```
{{log}}
```

### GitHub Issue
```
{{issue}}
```

### Generated Patch
```
{{patch}}
```

### Test Patch (for validation)
```
{{test_patch}}
```

### Test Results
```
{{results}}
```

## Required Analysis

Please provide a comprehensive diagnostic analysis in JSON format with these fields:

### 1. log_summarization
Summarize the agent's behavior:
- What tools did it use?
- What was its approach to solving the problem?
- Where did it get stuck or make mistakes?
- What patterns in its behavior led to failure?

### 2. potential_improvements
List general improvements that could help across multiple repositories:
- Better strategies for code analysis
- Improved error handling approaches
- More effective tool usage patterns
- Better decision-making heuristics

### 3. improvement_proposal
Select ONE high-impact improvement from your list above.
- Which improvement would have the biggest effect?
- Why is this the most critical change?
- What specific aspect of the failure does it address?

### 4. implementation_suggestion
Provide concrete implementation guidance:
- Which files/functions need modification?
- What specific code changes are needed?
- How should the logic flow change?
- What are the key implementation steps?

### 5. problem_description
Format the improvement as a GitHub issue:
- Clear title describing the enhancement
- Problem statement explaining the current limitation
- Proposed solution with implementation details
- Expected impact on agent performance

## Response Format

Return your analysis as valid JSON:

```json
{
  "log_summarization": "...",
  "potential_improvements": [
    "improvement 1",
    "improvement 2",
    "..."
  ],
  "improvement_proposal": "...",
  "implementation_suggestion": "...",
  "problem_description": "..."
}
```

## Important Guidelines

1. **Be specific**: Reference actual code patterns, tool calls, and logic flows
2. **Focus on root causes**: Don't just describe symptoms, identify why they occurred
3. **Make it actionable**: Provide clear, implementable suggestions
4. **Consider generalization**: Improvements should help on similar problems
5. **Prioritize impact**: Focus on changes that address the most critical failure modes
