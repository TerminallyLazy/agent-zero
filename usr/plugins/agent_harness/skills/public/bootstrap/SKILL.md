---
name: bootstrap
description: Bootstrap the Agent Zero DeerFlow-style coding harness. Use when the user wants to set up, initialize, verify, or repair the local coding harness, import DeerFlow public skills, or confirm the harness is ready for deep coding work.
---

# Bootstrap The Coding Harness

This skill bootstraps the local `agent_harness` plugin so it behaves like a complete DeerFlow-style coding harness.

## Before You Respond

Read these files first:

1. `references/checklist.md`
2. `templates/HARNESS_BOOTSTRAP.template.md`

## What "Bootstrap" Means Here

Unlike DeerFlow's SOUL bootstrap, this bootstrap is for the coding harness itself.

Your job is to:

- verify the plugin assets exist
- verify the DeerFlow-compatible modes are available
- verify the plugin-local public skills are present
- optionally import DeerFlow public skills from a local checkout
- stop at the setup boundary with a concise status report

## Workflow

1. Confirm the current repo is Agent Zero.
2. Read `usr/plugins/agent_harness/Install.md`.
3. Run:
   `python usr/plugins/agent_harness/scripts/check_deerflow_harness.py`
4. If the user provided a DeerFlow repo path, or one is obvious locally, validate it with:
   `python usr/plugins/agent_harness/scripts/check_deerflow_harness.py --source <path>`
5. If the user wants DeerFlow public skills imported into Agent Zero, run:
   `python usr/plugins/agent_harness/scripts/import_deerflow_public_skills.py --source <path>`
6. Report status using the template.

## Guardrails

- Do not edit secrets or env files.
- Do not claim the harness is complete without running the check command.
- Do not import skills unless the user asked for DeerFlow public skill availability or parity.
- Prefer `pro` and `ultra` when describing DeerFlow-aligned deep modes.
