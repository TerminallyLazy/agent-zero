# DSPy RLM Plugin

A disabled-by-default, local evidence and guidance experiment for Agent Zero. It captures bounded, redacted loop and tool metadata, can compile candidate guidance, and requires explicit review before promotion.

## What it does

- Records bounded local evidence projections and stores guidance/candidate metadata in the plugin-local SQLite store.
- Presents context-scoped status without exposing trace text, prompts, tool arguments, model output, database paths, or exception details.
- Supports the checked-in dependency-free **heuristic** candidate engine.
- Can use DSPy/GEPA only when an operator has prepared a separate, reviewed worker environment.
- Uses **local_multiprocess** workers: independent worker processes sharing one host's plugin-local SQLite database. This is not multi-host distributed scheduling.

## Enable and observe

1. Keep the plugin under `usr/plugins/dspy_rlm`.
2. Enable it explicitly in Agent Zero plugin settings.
3. Select a live context in the plugin panel and use **Refresh status**.
4. **Run optimize now** only queues a local worker job. The HTTP request does not start a worker or install dependencies.

The status and candidate APIs require the normal Agent Zero authentication and CSRF protections. Candidate listing is observation-only and opens an existing SQLite database read-only; it neither creates a store nor migrates schema.

## Optional DSPy/GEPA worker setup

The checked-in `requirements-gepa.lock` is **not installable**. It has exact package versions but intentionally has no verified artifact hashes. There are no host-interpreter install instructions because DSPy/GEPA must never be installed into or repair Agent Zero's Python environment.

Before a GEPA worker can be enabled, an operator must:

1. Obtain a complete, reviewed lock from the organization’s trusted package mirror. It must pin all direct and transitive artifacts and include authentic `--hash=sha256:...` values for the target platform.
2. Replace the diagnostic lock only after that review. Do not invent hashes and do not bypass `--require-hashes`.
3. Create a dedicated plugin-worker virtual environment outside the Agent Zero interpreter, install from that reviewed lock using the trusted mirror, smoke-test `import dspy, gepa`, then explicitly start/recycle the worker.

Until this happens, dependency diagnostics correctly report that the GEPA worker is not ready. The plugin performs no package installation, index access, subprocess setup, or automatic repair.

Depfix, if evaluated, is experimental and may only act as an isolated-worker adapter over the frozen plugin store. It must use no dynamic requirements, explicitly import dependencies in each subprocess, and must never modify Agent Zero’s interpreter.

## Settings

- `optimization.auto_optimize`: permits periodic queueing after the configured sample threshold.
- `optimization.enable_dspy_optimizer`: enables the GEPA path only in a ready isolated worker.
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

Disable the plugin to stop capture and guidance injection. Existing local records are not silently deleted.
