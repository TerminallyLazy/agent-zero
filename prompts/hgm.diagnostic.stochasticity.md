You are analyzing stochastic behavior in an agent's problem-solving.

## Execution Log
{{log}}

## Problem Statement
{{issue}}

## Analysis Task

Stochastic behavior (inconsistent results across runs) can come from:
1. Ambiguous prompts allowing multiple interpretations
2. Unstable tool outputs (race conditions, timing issues)
3. LLM sampling randomness
4. Environment state dependencies

Analyze the log and suggest:
1. **Sources of variability** - What's causing inconsistency?
2. **Determinism improvements** - How to make behavior more predictable?
3. **Validation strategies** - How to detect when outputs diverge?

Focus on engineering solutions, not just "reduce temperature".
