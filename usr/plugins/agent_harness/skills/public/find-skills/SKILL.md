---
name: find-skills
description: Helps users discover DeerFlow-compatible skills for the Agent Harness plugin and import DeerFlow public skills into Agent Zero when needed.
---

# Find DeerFlow-Compatible Skills

Use this skill when the user asks for a skill, a workflow bundle, or DeerFlow skill parity for the coding harness.

## What To Check

1. Plugin-local skills in `usr/plugins/agent_harness/skills/public/`
2. Existing Agent Zero skill roots (`skills/`, `usr/skills/`)
3. Optional DeerFlow checkout that can be imported into Agent Zero

## Workflow

1. If the user only needs local harness skills, inspect:
   `usr/plugins/agent_harness/skills/public/`
2. If the user wants DeerFlow public skills, validate the checkout:
   `python usr/plugins/agent_harness/scripts/check_deerflow_harness.py --source <path>`
3. If they want those skills imported into Agent Zero, run:
   `python usr/plugins/agent_harness/scripts/import_deerflow_public_skills.py --source <path>`
4. Summarize what exists locally, what can be imported, and the smallest next step.

## Notes

- Agent Zero already supports plugin-local skills, so not every DeerFlow skill needs to be imported to be usable.
- Import upstream DeerFlow public skills only when the user wants broader parity, not by default.
