# A0 Self-Improvement

An Agent Zero learning plugin powered by DSPy, GEPA, and RLM. It captures bounded, redacted execution evidence, evaluates recurring behavior, compiles candidate guidance, and promotes improvements through explicit quality and safety gates.

## What it does

- Records bounded local evidence projections and stores guidance/candidate metadata in the plugin-local SQLite store.
- Presents context-scoped status without exposing trace text, prompts, tool arguments, model output, database paths, or exception details.
- Supports the checked-in dependency-free **heuristic** candidate engine.
- Uses a plugin-owned worker virtual environment for DSPy RLM, GEPA, and dspy-cli.
- Uses **local_multiprocess** workers: independent worker processes sharing one host's plugin-local SQLite database. This is not multi-host distributed scheduling.

## Install and use

1. Install the repository as `usr/plugins/dspy_rlm` or use Agent Zero's Plugin Hub.
2. Enable the plugin and open **A0 Self-Improvement Settings**.
3. Leave the DSPy selector blank to inherit the active Agent Zero utility model, or provide an explicit `provider/model` selector.
4. Open the plugin dashboard for a live context to observe evidence, workers, candidates, quality gates, and active guidance.
5. **Run optimize now** queues a managed local worker job; the request itself does not run optimization inline.

The status and candidate APIs require the normal Agent Zero authentication and CSRF protections. Candidate listing is observation-only and opens an existing SQLite database read-only; it neither creates a store nor migrates schema.

## DSPy/GEPA worker setup

The plugin `install()` and `pre_update()` hooks create an isolated environment, bridge it read-only to the current Agent Zero framework packages, install the exact direct pins from `requirements-gepa.lock` through `uv`, and smoke-test both the Agent Zero worker imports and `dspy.RLM`/`dspy.GEPA`. A non-blocking startup extension repairs the environment after Docker container recreation. Native development uses `state/worker-venv`; Docker uses container-local `/opt/dspy-rlm-worker-venv` to avoid synchronizing dependency trees through the host bind mount. `DSPY_RLM_WORKER_VENV` may override either location. Agent Zero's framework interpreter is never modified. The status endpoint reads a version marker instead of importing DSPy on every refresh.

The current pins are DSPy 3.3.1 with the managed Deno extra, GEPA 0.1.4, and dspy-cli 0.1.13. Re-run the setup action after changing the lock or rebuilding the Docker container.

Depfix, if evaluated, is experimental and may only act as an isolated-worker adapter over the frozen plugin store. It must use no dynamic requirements, explicitly import dependencies in each subprocess, and must never modify Agent Zero’s interpreter.

## Settings

- `optimization.auto_optimize`: permits periodic queueing after the configured sample threshold.
- `optimization.enable_dspy_optimizer`: enables the GEPA path in a ready isolated worker.
- `rlm.enabled`: defaults on and uses `dspy.RLM` for bounded long-context analysis of aggregate evidence; deterministic analysis remains the fail-closed fallback until a DSPy model selector is configured.
- `rlm.model_ref` / `evaluator.preferred_dspy_model`: optional explicit DSPy model selectors used by RLM, semantic evaluation, and GEPA reflection. When both are blank, the worker checks `DSPY_RLM_MODEL`, then `DSPY_MODEL`, then derives a selector and credentials from Agent Zero's effective utility-model preset.
- `optimization.dry_run_mode`: evaluates candidates without promotion.
- `scheduler.max_workers`: desired count of local worker processes on this host.
- `trace_capture`: bounded metadata capture and retention settings.
- `prompt.inject_guidance`: explicit opt-in for applying active guidance.

## Safety and state labels

- **heuristic** is the dependency-free local candidate engine. It is not GEPA.
- **GEPA** is shown only for an actual GEPA candidate artifact, not merely because imports are present.
- **candidate** is staged guidance, not active guidance.
- **review_only** means a promotion gate did not authorize automatic promotion.
- **local_multiprocess** means one host with multiple local processes and SQLite coordination.
- Replay labels describe offline prompt-output or tool-fixture replay. They never mean live tool execution.

## Data locations

All runtime data is plugin local:

- `state/dspy_rlm_runtime.sqlite` for authoritative candidate, job, and guidance metadata.
- `state/traces.jsonl` for bounded redacted trace projections.
- `state/runtime_state.json` and `state/compiled_guidance.json` as compatibility/read-cache artifacts.

Disable the plugin to stop capture and guidance injection. Existing local records are not silently deleted. Remove `usr/plugins/dspy_rlm` to uninstall after preserving or deleting plugin-local state according to your retention needs.
