# DSPy RLM — Implementation Specification

## Context

This specification is in service of a local Agent Zero plugin under `usr/plugins/dspy_rlm` with minimal, explicit core-runtime support outside plugin seams for objective lifecycle metadata.

## Problem

Agent Zero needs a bounded and auditable self-improvement pipeline that can synthesize trace evidence into optimizer inputs, evaluate outputs semantically, and safely promote prompt guidance without degrading baseline behavior.

## Product Objective

Deliver an opt-in system that:

- Records compact traces and objective samples from loop/tool events.
- Computes objective-level quality signals using semantic evaluation.
- Runs GEPA optimization with matrix-based admission control.
- Supports multi-process distributed optimization scheduling.
- Keeps optimizer failures isolated from core reasoning.

## Architecture overview

- Plugin control plane: `usr/plugins/dspy_rlm`.
- Runtime metadata intake: read-only core fields exported into plugin envelope.
- Optimizer data plane: local state + optional distributed queue/worker model.

## Module model (SDD)

## In-scope non-seam work

- Core loop context and completion payload extensions are required so plugin gating can be objective-aware. This is explicitly **in scope** and is not postponed as an external dependency.
- Plugin metadata reads are read-only and must never mutate assistant behavior unless plugin is enabled.
- All promotions, retries, and scheduler state transitions must be deterministic and replay-safe.

### Module: Objective extractor

- **Interface:** `extract_objective_sample(context_state, traces, max_span)`
- **Implementation:** Converts normalized loop/tool events into typed `ObjectiveSample`.
- **Inputs:** `context_id`, objective metadata from core envelope, sanitized loop/tool signals.
- **Output:** Objective sample list with optional labels and bucketed metrics.
- **Seam:** Internal to plugin, called by trace/loop collectors.
- **Store:** `state/objectives.jsonl` in distributed mode, optional compacted `state/objectives_index.json`.

### Module: Semantic evaluator

- **Interface:** `evaluate_objective_sample(sample: ObjectiveSample) -> EvaluationResult`.
- **Implementation:** Runs one or more judge passes, returns:
  - `semantic_score`,
  - `rationale`,
  - `risk_flags`,
  - `confidence`.
- **Inputs:** prompt output candidate, target intent, tool constraints, and trace context.
- **Output:** objective and bucket-specific scores plus error taxonomies for hard-fail logic.
- **Quality loops:** Loop B executes for any candidate before matrix evaluation and is retried once when a scoring model is unavailable.
- **Seam:** Plugin internal module.

### Module: Matrix validator

- **Interface:** `validate(samples, thresholds, metrics, baselines)`.
- **Implementation:** Applies objective/validation matrix and computes promotion gate + reason codes.
- **Inputs:** evaluator outputs and sample histories.
- **Output:** `ValidationBundle` with:
  - `passed`,
  - `bucket_scores`,
  - `global_score`,
  - `hard_fail_flags`,
  - `reasons`.
- **Hard-fail matrix policy:** all hard-fail thresholds must pass before any candidate may be promoted.
- **Loop C (calibration):** objective-specific confidence calibration updates per bucket EWMA and confidence floor checks; scores below floor cause `review_only`.
- **Seam:** Plugin internal module.

### Module: Optimizer orchestrator

- **Interface:** `run_optimization_sync(context_id, cfg, force)`/`run_optimization` returns result state with status and guidance.
- **Implementation:** Gate checks (cooldown/min samples/force), sample selection, objective validation, evaluator loops, replay audit, GEPA compile, then promotion arbitration.
- **Loop chain:** loop_trace_to_sample -> evaluator -> calibration -> compile -> replay audit -> promote/rollback.
- **Seam:** `message_loop_end` extension and manual API trigger.
- **Store:** `state/runtime_state.json`, `state/compiled_guidance.json`, `state/optimization_runs.jsonl`.

### Module: Distributed scheduler

- **Interface:** `schedule_optimization(job_spec)`, `acquire_lease`, `report_result`.
- **Implementation:**
  - Coordinator maintains queue and lease table.
  - Workers pop jobs, run `OptimizerOrchestrator`, write candidate artifacts.
  - Coordinator performs promotion and cleanup.
- **Modes:**
  - single-process (legacy path),
  - distributed workers mode when `optimization_workers > 1`.
- **Seam:** Plugin internal modules `helpers/scheduler.py` and `helpers/scheduler/worker.py`.

### Module: Guidance adapter

- **Interface:** `system_prompt` extension executes with current loop state and appends one deterministic guidance block.
- **Implementation:** Reads current compiled guidance and active version metadata.
- **Seam:** Existing `system_prompt` extension hook.

### Module: Trace collector

- **Interface:** `tool_execute_after` and `message_loop_end` extension writers.
- **Implementation:** Sanitizes and stores compact loop/tool events in `traces.jsonl`, updates counters, and records objective-envelope data.
- **Seam:** Existing extension hooks.

### Module: Status API + web UI

- **Interface:** `POST /plugins/dspy_rlm/status` and `POST /plugins/dspy_rlm/optimize`.
- **Implementation:** API handlers return sanitized status/summary payloads and scheduler queue state.
- **UI contract:** status payload must expose `matrix_scores` and scheduler job status map so dashboard can render matrix gates and queue state continuously.

## Validation loop sequence (full loop map)

- **Loop A**: objective extraction from captured loop and tool traces.
- **Loop B**: semantic evaluator scoring and policy breach extraction.
- **Loop C**: sample-to-metric calibration and confidence floor enforcement.
- **Loop D**: GEPA candidate compile (if optimizer mode enabled).
- **Loop E**: replay audit against shadow samples and baseline guidance.
- **Loop F**: promotion commit/rollback with single-writer arbitration.

## Data model

### `runtime_state.json`

- `optimization_status`, `optimization_status_message`
- `last_run_at`, `last_run_ms`, `last_result_status`
- `cooldown_until`, `running_job_id`
- `queued_jobs`, `failed_jobs`
- `scheduler_mode` and worker heartbeat snapshots

### `compiled_guidance.json`

- `global` guidance + per-context guidance mapping
- `compiled_version`, `source_objective_id`, `promoted_at`

### `traces.jsonl`

- `context_id`, `event_type`, `tool`, `success`, `loop_iteration`, `ts`, sanitized content preview fields

### `objectives.jsonl`

- `objective_sample` payload plus bucket tags, labels, and confidence

### `optimization_runs.jsonl`

- `job_key`, `objective_bucket`, `status`, `requester`, `created_at`, `ended_at`
- `validation_bundle` summary and `promotion_decision`

### Scheduler persistence

- `scheduler_state.json` (single-node control state)
- `scheduler_lock` lease files or SQLite queue table for distributed mode

## Core behavior changes (outside plugin seams)

These are required only if objective metadata is not already sufficient from existing extension payloads:

- **Core context model extension:** add objective intent fields to loop context.
- **Loop completion payload extension:** include:
  - objective identifier,
  - expected output type,
  - validation/event signals,
  - tool contract summary.
- **Plugin accessor endpoint:** internal helper in core runtime to read envelope snapshots for plugin context.
- **No behavior change to default reasoning flow** unless plugin actively enabled.

## Control policy

- Auto schedule triggers when:
  - auto optimization enabled,
  - required sample threshold reached,
  - no optimization already running,
  - cooldown condition satisfied,
  - objective gating has not failed hard criteria.
- Manual run (`force=true`) bypasses sample/cooldown gates and runs objective matrix in strict validation mode.
- Objective promotion requires matrix pass and replay-audit pass.
- Promotion writes are single-writer to prevent split-brain guidance updates.

## Scheduler behavior

- **Job keying and idempotency:** deterministic `job_key` from context, objective bucket, trace signature, and optimization profile.
- **Lease model:** each worker obtains lease with TTL and heartbeat refresh; stale leases auto-reclaimed.
- **Retry policy:** transient failures retry with capped exponential backoff; hard failures become terminal with reason codes.
- **Result states:** `queued`, `running`, `candidate`, `promoted`, `rejected`, `failed`.
- **Cleanup:** prune stale logs, completed jobs, and finished run artifacts beyond retention limits.

## Failure and rollback behavior

- Dependency/optimization failures never block core prompt generation.
- Guidance fallback remains last successful candidate or empty guidance if no successful candidate exists.
- Evaluator exception, empty objective samples, or lock contention produce explicit `warning` status and skip promotion.
- Any distributed worker failure does not affect coordinator state integrity.

## Risks and mitigations

- **Dependency mismatch:** GEPA/DSPy import drift. Mitigation: optional import paths and heuristic fallback.
- **Trace growth:** unbounded logs. Mitigation: retention caps plus objective- and run-level pruning.
- **Semantic evaluator noise:** prompt ambiguity around goals. Mitigation: dual scoring pass and confidence floor.
- **False positives in policy checks:** strict allowlist and hard-fail classification before promotion.
- **Scheduler split-brain:** single-writer promotion arbitration and stale-lock recovery.

## Validation checkpoints

- Enable plugin + status load works for context.
- Objective envelope appears for active contexts and survives failure paths.
- Trace and objective sample counters advance.
- Validation matrix gates block hard-fail scenarios.
- Manual optimization + distributed schedule path produce `candidate`/`promoted` state transitions.
- Replay audit detects regressions and prevents promotion.
- UI shows scheduler and validation states, and manual run updates status.
