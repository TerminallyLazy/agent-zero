# HGM Improvement Evaluation

You are an expert evaluator assessing whether a code modification has improved a coding agent's performance.

## Agent Implementation (Before Patch)

### Current Code

```
{{before_code}}
```

### Current Tools

```
{{before_tools}}
```

## Applied Modification

### Model Patch

```diff
{{model_patch}}
```

### Modification Description

{{patch_description}}

## Evaluation Context

### Test Case

**Problem ID**: {{problem_id}}

**Problem Statement**:
```
{{problem_statement}}
```

**Ground Truth Solution**:
```
{{ground_truth_solution}}
```

**Test Cases**:
```
{{test_cases}}
```

## Performance Data

### Before Patch

**Agent Log**:
```
{{before_log}}
```

**Predicted Solution**:
```
{{before_prediction}}
```

**Test Results**:
```
{{before_test_results}}
```

### After Patch

**Agent Log**:
```
{{after_log}}
```

**Predicted Solution**:
```
{{after_prediction}}
```

**Test Results**:
```
{{after_test_results}}
```

## Your Task

Analyze the modification's impact on the coding agent's capabilities. Provide a comprehensive comparative analysis.

## Required Analysis

### 1. Performance Impact

Compare the agent's behavior before and after the patch:
- Did solution quality improve?
- Are there changes in reasoning patterns?
- Did test pass rates change?
- Are there differences in tool usage patterns?

### 2. Improvements Identified

List specific improvements observed:
- Better problem understanding
- More effective tool usage
- Improved code quality
- Better error handling
- Enhanced reasoning capabilities

### 3. Regressions Detected

Identify any negative impacts:
- New failures introduced
- Reduced performance on certain tasks
- Loss of capabilities
- Increased errors or instability

### 4. Overall Assessment

Provide a numerical score from -2 to +2:
- **+2**: Major improvement, significant capability enhancement
- **+1**: Minor improvement, incremental gains
- **0**: No meaningful change
- **-1**: Minor regression, small capability loss
- **-2**: Major regression, significant capability loss

## Response Format

Return your evaluation as JSON:

```json
{
  "performance_impact": "Detailed analysis of performance changes...",
  "improvements": [
    "Specific improvement 1",
    "Specific improvement 2",
    "..."
  ],
  "regressions": [
    "Specific regression 1",
    "Specific regression 2",
    "..."
  ],
  "overall_score": 1,
  "confidence": "high|medium|low",
  "reasoning": "Justification for the score...",
  "recommendation": "Should this patch be kept, refined, or discarded?"
}
```

## Evaluation Criteria

### Code Quality Changes
- Correctness: Does the patch fix bugs or introduce new ones?
- Maintainability: Is the code cleaner or more complex?
- Efficiency: Are there performance improvements?

### Capability Changes
- Problem-solving: Can the agent solve more problems?
- Tool usage: Does it use tools more effectively?
- Error handling: Better recovery from failures?

### Test Results
- FAIL_TO_PASS: Tests that now pass (good)
- PASS_TO_PASS: Tests that still pass (neutral)
- PASS_TO_FAIL: Tests that now fail (bad)
- FAIL_TO_FAIL: Tests that still fail (neutral)

### Log Analysis
- Reasoning quality: Is the thought process clearer?
- Action sequences: More efficient tool usage?
- Error patterns: Fewer mistakes?

## Important Guidelines

1. **Be objective**: Base assessment on concrete evidence from logs and results
2. **Be specific**: Reference exact log excerpts and test outcomes
3. **Be balanced**: Acknowledge both improvements and regressions
4. **Be actionable**: Provide clear guidance on whether to keep the patch
5. **Be quantitative**: Use test pass rates and concrete metrics when possible

## Example Evaluation

```json
{
  "performance_impact": "The patch adds validation to ensure subordinate agents make actual file modifications. In the before logs, the agent completed with empty patches 3/5 times. In the after logs, all 5 attempts resulted in valid patches. Test pass rate improved from 0% to 60%.",
  "improvements": [
    "Empty patch detection prevents false successes",
    "Retry logic with progressively explicit prompts",
    "Validation using git diff before accepting results",
    "Better error messages when subordinates fail"
  ],
  "regressions": [
    "Slightly increased execution time due to validation",
    "More verbose logging output"
  ],
  "overall_score": 2,
  "confidence": "high",
  "reasoning": "The patch addresses a critical failure mode (empty patches) that was causing 60% task failure. The fix is clean, well-tested, and shows immediate improvement in test results with minimal downsides.",
  "recommendation": "Keep this patch. It solves a major problem with minimal overhead. Consider applying similar validation to other tool outputs."
}
```
