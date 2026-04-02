# Agent Harness DeerFlow Install

This file bootstraps the Agent Zero `agent_harness` plugin so it behaves like a DeerFlow-style coding harness instead of just a latent backend module.

## Goal

Prepare the local Agent Zero workspace for DeerFlow-style coding runs with:

- DeerFlow-compatible modes: `flash`, `standard`, `pro`, `ultra`
- DeerFlow-style thread data roots for `workspace`, `uploads`, and `outputs`
- plugin-local DeerFlow core APIs for thread state, uploads, artifacts, and host catalogs
- plugin-local bootstrap and skill-discovery skills
- optional import of DeerFlow public skills into Agent Zero's skill registry

## Success Criteria

Consider the harness bootstrap complete when all of the following are true:

- `usr/plugins/agent_harness/plugin.yaml` exists and the plugin loads
- the plugin ships `skills/public/bootstrap` and `skills/public/find-skills`
- the plugin exposes `deerflow_core`, `thread_data`, `thread_uploads`, and `thread_artifacts` APIs
- `python usr/plugins/agent_harness/scripts/check_deerflow_harness.py` exits successfully
- if a local DeerFlow checkout is available, its public skills can be listed or imported without manual path surgery
- the user receives the exact next step for either verification or skill import

## Steps

1. Confirm you are in the Agent Zero repository root.
2. Verify the plugin assets:

   ```bash
   python usr/plugins/agent_harness/scripts/check_deerflow_harness.py
   ```

3. If you have a local DeerFlow checkout and want the upstream public skills available in Agent Zero, import them:

   ```bash
   python usr/plugins/agent_harness/scripts/import_deerflow_public_skills.py --source /path/to/deer-flow
   ```

4. Run the harness tests:

   ```bash
   ./.venv/bin/pytest -q tests/test_agent_harness_plugin.py tests/test_harness_*.py
   ```

5. Start the harness from the UI or via the tool in `pro` or `ultra` mode.
6. If you want to inspect the DeerFlow-style core bridge, call:

   - `/plugins/agent_harness/deerflow_core`
   - `/plugins/agent_harness/thread_data`
   - `/plugins/agent_harness/thread_uploads`
   - `/plugins/agent_harness/thread_artifacts`

## Recommended Next Commands

- Verify local harness assets:

  ```bash
  python usr/plugins/agent_harness/scripts/check_deerflow_harness.py
  ```

- Verify thread-data and core bridge coverage:

  ```bash
  ./.venv/bin/pytest -q tests/test_harness_workspace.py tests/test_agent_harness_plugin.py
  ```

- Verify against a DeerFlow checkout:

  ```bash
  python usr/plugins/agent_harness/scripts/check_deerflow_harness.py --source /path/to/deer-flow
  ```

- Import DeerFlow public skills:

  ```bash
  python usr/plugins/agent_harness/scripts/import_deerflow_public_skills.py --source /path/to/deer-flow
  ```
