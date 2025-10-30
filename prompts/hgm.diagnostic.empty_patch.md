You are diagnosing why an agent generated an empty patch (no code changes) when trying to solve a problem.

## Execution Log
{{log}}

## Problem Statement
{{issue}}

## Analysis Task

An empty patch usually means:
1. The agent didn't understand what to do
2. The agent thought no changes were needed
3. The agent made changes in the wrong location
4. The agent's tool calls failed without proper error handling

Provide:
1. **Most likely cause** based on the log
2. **Specific recommendations** to prevent empty patches:
   - Prompt improvements to clarify expectations
   - Tool enhancements to verify changes
   - Workflow modifications to validate progress
3. **Example fix** showing what a good solution would look like

Be concrete and actionable.
