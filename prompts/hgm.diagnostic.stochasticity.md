# HGM Diagnostic Analysis - Stochasticity

You are an expert AI system analyzer diagnosing inconsistent behavior in a coding agent.

## Agent Implementation Summary

The coding agent uses:
- **Tool-based architecture**: Async tools with potential timing dependencies
- **LLM-based decision making**: Subject to sampling randomness
- **Subordinate agent delegation**: Multiple agents may behave differently
- **State management**: Agent.data persistence across operations

## Analysis Context

The agent shows INCONSISTENT behavior across runs - sometimes succeeds, sometimes fails on the same problem.

### Running Log (First Attempt - Failed)
```
{{log}}
```

### Problem Statement
```
{{issue}}
```

### Test Results
```
{{results}}
```

## Required Analysis

Diagnose why behavior is NON-DETERMINISTIC. Provide JSON with these fields:

### 1. log_summarization
- What decisions did the agent make?
- Which choices could vary between runs?
- Are there race conditions or timing dependencies?
- Do subordinate agents behave consistently?

### 2. potential_improvements
List ways to improve consistency:
- Add explicit ordering/sequencing
- Remove ambiguous decision points
- Implement retry logic with backoff
- Add validation before proceeding
- Make prompts more specific
- Cache intermediate results

### 3. improvement_proposal
Select the ONE most critical fix for consistency:
- What specific change would reduce variability?
- Why does this have the biggest impact?

### 4. implementation_suggestion
Concrete steps to improve determinism:
- Which component has the most variability?
- What validation/verification should be added?
- How to make decisions more explicit?
- Should we add retry logic?

### 5. problem_description
Format as GitHub issue:
```
Title: Improve consistency in [specific operation]

Problem: Agent shows inconsistent behavior when...
Root Cause: [Ambiguity/Timing/State dependency]
Solution: Add [validation/sequencing/retry logic] to ensure...
Expected: Consistent behavior across multiple runs
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

## Common Sources of Stochasticity

1. **LLM Sampling**: Different responses to same prompt
2. **Ambiguous Prompts**: Multiple valid interpretations
3. **Timing Dependencies**: Race conditions in async operations
4. **Tool Variability**: External tools with non-deterministic output
5. **State Dependencies**: Behavior changes based on previous state
6. **Subordinate Agent Variance**: Different sub-agents make different choices

**Focus**: Make the agent's behavior predictable and reproducible.
