# HGM Diagnostic Analysis - Polyglot (Multi-Language)

You are an expert AI system analyzer tasked with diagnosing issues in a multi-language coding agent's performance.

## Agent Implementation Summary

The coding agent supports multiple programming languages and uses:

- **Tool-based system**: Async tools for git operations, repository solving, and diagnostics
- **Language-agnostic approach**: Works across Python, JavaScript, Java, Go, Rust, etc.
- **Subordinate agent delegation**: Spawns sub-agents for language-specific tasks
- **State management**: Uses agent.data dictionary for persistent state
- **Problem-solving flow**: Analysis → Test identification → Language-specific implementation

## Analysis Context

You are analyzing a failed attempt to solve a programming problem that may involve multiple languages.

### Running Log
```
{{log}}
```

### Problem Description
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

Please provide a comprehensive diagnostic analysis in JSON format with these fields:

### 1. log_summarization
Summarize the agent's behavior:
- Which programming language(s) were involved?
- What was the agent's approach?
- Did it correctly identify language-specific requirements?
- Where did language-specific handling fail?
- What patterns led to failure?

### 2. potential_improvements
List general improvements for multi-language scenarios:
- Better language detection/identification
- Improved language-specific tool selection
- More effective cross-language dependency handling
- Better understanding of language-specific idioms
- Improved build system integration

### 3. improvement_proposal
Select ONE high-impact improvement:
- Which improvement would have the biggest effect across languages?
- Why is this the most critical change?
- What specific aspect of the failure does it address?

### 4. implementation_suggestion
Provide concrete implementation guidance:
- Which files/functions need modification?
- What language-specific logic is needed?
- How should the tool selection change?
- What are the key implementation steps?

### 5. problem_description
Format the improvement as a GitHub issue:
- Clear title describing the enhancement
- Problem statement explaining the current limitation
- Language-specific considerations
- Proposed solution with implementation details
- Expected impact on multi-language support

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

## Language-Specific Considerations

When analyzing multi-language failures, consider:

1. **Language Detection**: Did the agent correctly identify all languages involved?
2. **Build Systems**: Maven, Gradle, npm, cargo, go mod, etc.
3. **Test Frameworks**: JUnit, pytest, Jest, RSpec, etc.
4. **Dependency Management**: Package managers and dependency resolution
5. **Idioms**: Language-specific patterns and best practices
6. **Tooling**: Compilers, interpreters, linters, formatters
7. **Cross-language**: How do different languages interact in the project?

## Important Guidelines

1. **Be language-aware**: Reference language-specific patterns and tools
2. **Focus on generalization**: Improvements should work across languages
3. **Make it actionable**: Provide clear, implementable suggestions
4. **Consider edge cases**: Multi-language projects, polyglot repositories
5. **Prioritize impact**: Focus on changes that help the most languages
