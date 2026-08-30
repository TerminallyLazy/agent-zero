# Domain docs

This is a single-context repository. These rules define how engineering skills consume its domain documentation.

## Before exploring, read these

- **`CONTEXT.md`** at the repository root.
- **`docs/adr/`** for ADRs that affect the area being changed.

If either location does not exist, proceed silently. Do not recommend creating it preemptively. The `/domain-modeling` skill, reached through `/grill-with-docs` and `/improve-codebase-architecture`, creates domain documentation lazily when terminology or decisions are resolved.

## File structure

```text
/
├── CONTEXT.md
├── docs/
│   └── adr/
│       └── NNNN-decision-title.md
├── agent.py
├── initialize.py
└── ...
```

## Use the glossary’s vocabulary

When output names a domain concept—in an issue title, refactoring proposal, hypothesis, or test—use the term defined in `CONTEXT.md`. Do not drift to synonyms the glossary explicitly avoids.

If a needed concept is absent, reconsider whether the language belongs to the project or note the gap for `/domain-modeling`.

## Flag ADR conflicts

If proposed work contradicts an existing ADR, surface the conflict explicitly instead of silently overriding it:

> _Contradicts ADR-0007, but worth reopening because…_
