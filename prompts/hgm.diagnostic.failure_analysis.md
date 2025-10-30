You are an expert software engineering analyst. Analyze this failed solution attempt and provide actionable improvement recommendations.

## Execution Log
{{log}}

## Problem Statement
{{issue}}

## Generated Patch
{{patch}}

## Test Results
{{results}}

{{#test_patch}}
## Reference Tests
{{test_patch}}
{{/test_patch}}

## Your Analysis Task

Carefully analyze the failure and provide a JSON response with these fields:

```json
{
  "log_summarization": "Brief summary of what the agent attempted and why it failed",
  "potential_improvements": [
    "Specific improvement idea 1",
    "Specific improvement idea 2",
    "Specific improvement idea 3"
  ],
  "improvement_proposal": "The most promising improvement to implement",
  "implementation_suggestion": "Detailed technical approach for implementing the improvement",
  "problem_description": "Reformulated problem as a GitHub issue that would help agent developers understand what to fix"
}
```

Focus on:
1. **Root causes** - What fundamentally went wrong?
2. **Agent capabilities** - What tools/knowledge was missing?
3. **Prompt improvements** - How could instructions be clearer?
4. **Tool enhancements** - What new tools or tool improvements would help?
5. **Workflow changes** - Should the solving approach be different?

Be specific and actionable. Avoid generic advice.
