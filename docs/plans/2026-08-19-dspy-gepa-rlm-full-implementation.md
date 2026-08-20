# DSPy GEPA/RLM Full Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the DSPy GEPA/RLM plugin into a safe, evidence-backed self-improvement system with recursive language-model reasoning, genuine GEPA compilation, paired replay evaluation, and schedulable workers.

**Architecture:** SQLite is the local authoritative store for redacted evidence, immutable RLM datasets, candidate artifacts, jobs, replay audits, and active-guidance pointers. An RLM recursively reasons over bounded, summarized evidence through a tool-like query interface; GEPA optimizes a constrained guidance program against frozen RLM-derived train/dev datasets; paired replay decides whether a candidate can be promoted. Workers only generate and evaluate candidates; an atomic coordinator is the only promotion writer.

**Tech Stack:** Python, SQLite WAL, pytest, Agent Zero plugin APIs/extensions, optional pinned DSPy/GEPA worker environment.

---

## Scope and terminology

- **RLM (Recursive Language Model):** a bounded recursive analysis layer. It receives a sanitized evidence manifest and may recursively query summaries, bucket slices, error clusters, and predecessor findings. It never receives raw uncontrolled trace storage, performs no tool execution, and has max depth/query/token/time budgets. Its output is a typed `RlmFinding`, not prompt text.
- **Guidance artifact:** structured rules from an allowlisted schema, rendered only by plugin-owned code. It cannot include copied user/tool/model content, commands, URLs, credentials, role markup, or policy overrides.
- **Replay:** paired offline replay of the active baseline and the candidate against an immutable, held-out fixture manifest. It is labelled `offline_prompt_output_replay` or `tool_fixture_replay`, never live execution replay.
- **Local multiprocess:** multiple processes on a single host sharing local SQLite. It must not be called distributed.
- **Distributed:** a later multi-host backend using PostgreSQL and content-addressed artifacts. It is not part of the SQLite milestone.

## File structure

| File | Responsibility |
| --- | --- |
| `usr/plugins/dspy_rlm/helpers/config.py` | Schema-v2 effective configuration, migration, safe gates |
| `usr/plugins/dspy_rlm/helpers/store.py` | SQLite migrations, atomic repositories, active-guidance CAS |
| `usr/plugins/dspy_rlm/helpers/redaction.py` | Recursive field allowlisting, secret detection, bounded projections |
| `usr/plugins/dspy_rlm/helpers/evidence.py` | Sanitized events, immutable sample manifests and deterministic splits |
| `usr/plugins/dspy_rlm/helpers/rlm.py` | Budgeted recursive evidence analysis and typed findings |
| `usr/plugins/dspy_rlm/helpers/guidance.py` | Constrained artifact schema, validator, renderer, injection selection |
| `usr/plugins/dspy_rlm/helpers/engines/heuristic.py` | Explicit heuristic candidate engine |
| `usr/plugins/dspy_rlm/helpers/engines/gepa.py` | Pinned DSPy/GEPA adapter and true compile invocation |
| `usr/plugins/dspy_rlm/helpers/replay.py` | Frozen paired baseline/candidate replay and promotion gates |
| `usr/plugins/dspy_rlm/helpers/promotion.py` | Audit-backed atomic promotion and rollback |
| `usr/plugins/dspy_rlm/helpers/queue.py` | SQLite local-multiprocess jobs, claims, leases and heartbeats |
| `usr/plugins/dspy_rlm/worker.py` | Explicit operator-managed worker process entry point |
| `usr/plugins/dspy_rlm/api/*.py` | Context-aware APIs: status, enqueue, candidates, promote, rollback |
| `usr/plugins/dspy_rlm/extensions/python/*` | Bounded capture, process-chain scheduling, validated injection |
| `usr/plugins/dspy_rlm/tests/` | Deterministic tests using temporary state and fake engines |

## Task 1: Freeze unsafe defaults and establish plugin-local test infrastructure

**Files:**
- Modify: `usr/plugins/dspy_rlm/default_config.yaml`
- Modify: `usr/plugins/dspy_rlm/config.json`
- Modify: `usr/plugins/dspy_rlm/plugin.yaml`
- Create: `usr/plugins/dspy_rlm/tests/conftest.py`
- Create: `usr/plugins/dspy_rlm/tests/test_config_contract.py`

- [ ] Write failing tests proving the checked-in effective defaults have: instrumentation off, optimization off, auto enqueue off, prompt injection off, automatic dependency installation off, engine `heuristic`, worker backend `sqlite_local`, and one worker.
- [ ] Implement the inert v2 defaults. Remove conflicting duplicate legacy runtime values from checked-in `config.json`; do not commit state databases or caches.
- [ ] Add pytest fixtures that monkeypatch plugin paths to a temporary directory and reset cached configuration/state between tests.
- [ ] Run `pytest usr/plugins/dspy_rlm/tests/test_config_contract.py -v` and verify it passes.

## Task 2: Unify configuration and enablement

**Files:**
- Modify: `usr/plugins/dspy_rlm/helpers/config.py`
- Modify: `usr/plugins/dspy_rlm/hooks.py`
- Create: `usr/plugins/dspy_rlm/helpers/runtime_policy.py`
- Test: `usr/plugins/dspy_rlm/tests/test_config_contract.py`

- [ ] Write failing tests that saved global plugin config resolves with and without an agent, sparse settings deep-merge defaults, legacy aliases migrate once, conflicting aliases fail closed, and `runtime_policy` independently gates instrumentation, enqueueing, manual optimization, and injection.
- [ ] Implement `load_config()` through Agent Zero `get_plugin_config()` for both agent and non-agent callers, safe deep merge, schema migration, bounded coercion, and explicit diagnostic reasons.
- [ ] Implement `RuntimePolicy.from_config()` with `can_capture`, `can_enqueue`, `can_optimize`, `can_inject`, and `can_auto_promote`; `force` only bypasses cooldown/sample thresholds.
- [ ] Run focused tests and `python3 -m compileall -q usr/plugins/dspy_rlm`.

## Task 3: Make SQLite authoritative and migrate durable state

**Files:**
- Create: `usr/plugins/dspy_rlm/helpers/store.py`
- Modify: `usr/plugins/dspy_rlm/helpers/paths.py`
- Modify: `usr/plugins/dspy_rlm/helpers/state.py`
- Test: `usr/plugins/dspy_rlm/tests/test_store.py`

- [ ] Write failing repository tests for schema migration, append-only candidate records, immutable sample manifests, atomic active-guidance compare-and-swap, rollback, and no JSON source-of-truth dependency.
- [ ] Implement migration-controlled SQLite tables for events, samples, manifests, guidance versions, active guidance, runs, evaluations, replay audits, jobs, leases, heartbeats, and promotion audits.
- [ ] Move mutable runtime state behind transaction-backed repository methods; retain JSON only as an atomically-written optional read cache.
- [ ] Run store tests under temporary paths, including concurrent compare-and-swap tests.

## Task 4: Build privacy-bounded evidence intake

**Files:**
- Create: `usr/plugins/dspy_rlm/helpers/redaction.py`
- Create: `usr/plugins/dspy_rlm/helpers/evidence.py`
- Modify: `usr/plugins/dspy_rlm/helpers/trace.py`
- Modify: `usr/plugins/dspy_rlm/extensions/python/tool_execute_after/_40_dspy_rlm_trace.py`
- Modify: `usr/plugins/dspy_rlm/extensions/python/message_loop_end/_90_dspy_rlm_optimize.py`
- Test: `usr/plugins/dspy_rlm/tests/test_redaction.py`
- Test: `usr/plugins/dspy_rlm/tests/test_evidence.py`

- [ ] Write failing nested-secret corpus tests: headers, JWTs, passwords, cookies, URLs with credentials, PEM blocks, lists, arbitrary object values, prompt-injection strings, and oversized payloads.
- [ ] Implement allowlisted event projections, recursive redaction, content hashing, per-event/context/loop caps, timestamp TTL sweep, and nonblocking drop-on-storage-failure behavior.
- [ ] Capture structured tool/turn metadata only; raw content requires an explicit approved privacy mode and still passes recursive redaction.
- [ ] Implement immutable objective sample projections and deterministic grouped train/dev/holdout splits that prevent near-duplicate objective families crossing partitions.
- [ ] Run evidence tests and ensure trace capture has no scheduling or optimizer side effects.

## Task 5: Implement the RLM evidence-analysis layer

**Files:**
- Create: `usr/plugins/dspy_rlm/helpers/rlm.py`
- Create: `usr/plugins/dspy_rlm/helpers/rlm_queries.py`
- Test: `usr/plugins/dspy_rlm/tests/test_rlm.py`

- [ ] Write failing tests for recursion depth, max query count, max evidence characters, cycle detection, deterministic query results, redacted-only input enforcement, and failure degradation to no findings.
- [ ] Define typed `RlmQuery`, `RlmFinding`, `RlmBudget`, and `EvidenceIndex` interfaces.
- [ ] Implement query handlers for aggregate metrics, objective bucket slices, error clusters, tool reliability summaries, and predecessor-finding references. Every handler returns bounded, redacted structured data.
- [ ] Implement a recursive controller that may request child queries only until budget/depth exhaustion; it stores a derivation DAG of hashes/reason codes, not raw prompt transcripts.
- [ ] Provide deterministic local reasoning for tests and an optional configured model adapter that emits JSON-schema-conforming query plans/findings. Model failures produce `review_only` and never an instruction artifact.
- [ ] Run RLM tests; demonstrate a multi-step finding where a parent conclusion depends on two bounded child evidence queries.

## Task 6: Constrain guidance artifacts and injection

**Files:**
- Create: `usr/plugins/dspy_rlm/helpers/guidance.py`
- Modify: `usr/plugins/dspy_rlm/extensions/python/system_prompt/_30_dspy_rlm_guidance.py`
- Test: `usr/plugins/dspy_rlm/tests/test_guidance.py`
- Test: `usr/plugins/dspy_rlm/tests/test_prompt_extension.py`

- [ ] Write failing tests proving user/tool/model/RLM raw strings, commands, URLs, credentials, role tokens, policy overrides, and unrecognized rule types are rejected.
- [ ] Define an allowlisted `GuidanceArtifact` schema with narrow rule types, bounded values, source manifest/finding hashes, expiration, engine metadata, and artifact digest.
- [ ] Implement validator, fixed renderer, and active-artifact selector. Only promoted, nonexpired, compatible artifacts are renderable.
- [ ] Update system-prompt extension to require `RuntimePolicy.can_inject`, bounded rendered size, and an active artifact from SQLite. It must never depend on auto enqueue/optimization settings.
- [ ] Run prompt injection adversarial tests and confirm a disabled injection flag appends nothing.

## Task 7: Local multiprocess queue and single-writer promotion

**Files:**
- Create: `usr/plugins/dspy_rlm/helpers/queue.py`
- Create: `usr/plugins/dspy_rlm/helpers/promotion.py`
- Create: `usr/plugins/dspy_rlm/worker.py`
- Modify: `usr/plugins/dspy_rlm/helpers/_scheduler_coordinator.py`
- Modify: `usr/plugins/dspy_rlm/helpers/scheduler/worker.py`
- Modify: `usr/plugins/dspy_rlm/api/optimize.py`
- Test: `usr/plugins/dspy_rlm/tests/test_queue.py`
- Test: `usr/plugins/dspy_rlm/tests/test_promotion.py`

- [ ] Write failing tests for duplicate enqueue idempotency, `force` not replacing a leased job, single successful claim, owner-token/fencing enforcement, heartbeat renewal, prompt expiry reclamation, cancellation, retry classification, and coordinator-only promotion.
- [ ] Replace request-triggered daemon spawning with explicit `python3 -m usr.plugins.dspy_rlm.worker --once|--serve` worker operation. APIs enqueue only and return job metadata.
- [ ] Implement SQLite transactional claims with lease owner and fencing token. Workers create candidates/evaluations; they cannot update active guidance.
- [ ] Implement promotion with active revision compare-and-swap, audit record, immutable previous versions, and rollback.
- [ ] Rename every local SQLite worker status/mode from `distributed` to `local_multiprocess`.
- [ ] Run queue/promotion tests including multiprocessing fault injection where supported.

## Task 8: Implement genuine GEPA compilation and candidate engines

**Files:**
- Create: `usr/plugins/dspy_rlm/helpers/engines/__init__.py`
- Create: `usr/plugins/dspy_rlm/helpers/engines/heuristic.py`
- Create: `usr/plugins/dspy_rlm/helpers/engines/gepa.py`
- Modify: `usr/plugins/dspy_rlm/helpers/optimizer.py`
- Modify: `usr/plugins/dspy_rlm/requirements.txt`
- Create: `usr/plugins/dspy_rlm/requirements-gepa.lock`
- Test: `usr/plugins/dspy_rlm/tests/test_gepa_engine.py`

- [ ] Write failing fake-DSPy tests proving a genuine GEPA engine creates examples, configures a declared program/metric, invokes the pinned GEPA compile API, and persists its returned candidate artifact.
- [ ] Keep a dependency-free heuristic engine that consumes only RLM findings and emits a schema-valid guidance artifact labelled `heuristic`.
- [ ] Implement GEPA adapter capability checks, explicit model configuration reference, train/dev manifest loading, cost/runtime budget enforcement, compile invocation, and complete reproducibility metadata.
- [ ] Pin the validated compatible dependency set in a lock artifact. Do not install dependencies in this task.
- [ ] Ensure absent/failed GEPA produces `gepa_unavailable`/`failed` and cannot label or promote a heuristic candidate as GEPA.
- [ ] Run fake-engine tests without network or real API keys.

## Task 9: Implement paired replay, evaluation, and promotion gates

**Files:**
- Create: `usr/plugins/dspy_rlm/helpers/replay.py`
- Create: `usr/plugins/dspy_rlm/helpers/evaluation.py`
- Modify: `usr/plugins/dspy_rlm/helpers/objective_validation.py`
- Modify: `usr/plugins/dspy_rlm/helpers/semantic_evaluator.py`
- Test: `usr/plugins/dspy_rlm/tests/test_replay.py`

- [ ] Write failing tests for disjoint frozen manifests, blind paired baseline/candidate execution, per-case safety hard-fail, protected-bucket non-regression, missing baseline `review_only`, judge failure `review_only`, and a degraded candidate rejected despite higher average score.
- [ ] Implement deterministic executable checks, schema/policy checks, and optional blinded structured judge adapter. Rename existing lexical checks to telemetry-only signals.
- [ ] Implement paired replay using the same offline prompt/tool-fixture case for baseline and candidate, recording per-case outcomes, evaluator/model/harness provenance, confidence, and replay mode.
- [ ] Require all hard gates, adequate coverage, no protected regression, and an active baseline revision match before marking a candidate promotion-ready.
- [ ] Run replay tests proving the candidate artifact is actually supplied to execution and initial lack of baseline cannot pass automatically.

## Task 10: Complete context-safe API/UI and dependency setup design

**Files:**
- Modify: `usr/plugins/dspy_rlm/api/status.py`
- Modify: `usr/plugins/dspy_rlm/api/optimize.py`
- Create: `usr/plugins/dspy_rlm/api/candidates_list.py`
- Create: `usr/plugins/dspy_rlm/api/promote.py`
- Create: `usr/plugins/dspy_rlm/api/rollback.py`
- Modify: `usr/plugins/dspy_rlm/webui/dspy-rlm-store.js`
- Modify: `usr/plugins/dspy_rlm/webui/main.html`
- Modify: `usr/plugins/dspy_rlm/webui/config.html`
- Modify: `usr/plugins/dspy_rlm/hooks.py`
- Create: `usr/plugins/dspy_rlm/execute.py`
- Test: `usr/plugins/dspy_rlm/tests/test_api.py`
- Test: `usr/plugins/dspy_rlm/tests/test_dependencies.py`

- [ ] Write failing API tests for missing/unknown context IDs, disabled contexts, queue-only manual request, no raw trace/status leakage, stable state payloads, and promote/rollback revision conflicts.
- [ ] Resolve an existing context without `use_context(create_if_not_exists=True)`, use its agent for effective config, preserve API auth/CSRF, and return sanitized metadata only.
- [ ] Update UI to use standard A0 notifications, clearly distinguish observe/candidate/review/promotion/replay/engine/worker states, and never call a candidate “GEPA optimized” unless an actual GEPA run completed.
- [ ] Replace startup auto-install with dependency diagnostics. Implement a manual `execute.py` setup action that only proposes exact locked packages and an isolated plugin-worker environment; it requires explicit operator action, one installer lock, finite timeout, trusted index, hashes, logs, smoke test, and worker recycle.
- [ ] Document Depfix only as an experimental isolated worker adapter: plugin-scoped frozen store, no dynamic requirements, each subprocess explicit import setup. It must not modify Agent Zero’s interpreter or automatically repair/install packages.
- [ ] Run API/dependency tests with all subprocess and network actions mocked.

## Task 11: Documentation, migration, and verification

**Files:**
- Modify: `usr/plugins/dspy_rlm/README.md`
- Modify: `usr/plugins/dspy_rlm/IMPLEMENTATION_SPEC.md`
- Create: `usr/plugins/dspy_rlm/docs/architecture.md`
- Create: `usr/plugins/dspy_rlm/docs/operations.md`
- Test: `usr/plugins/dspy_rlm/tests/test_documented_contract.py`

- [ ] Update all claims so `heuristic`, `RLM`, `GEPA`, `offline_prompt_output_replay`, `tool_fixture_replay`, `local_multiprocess`, and true `distributed` have precise truthful definitions.
- [ ] Document privacy modes, redaction/retention/deletion, prompt-injection trust boundary, worker operation, promotion/rollback, budgets, dependency setup, and emergency disablement.
- [ ] Add static documentation contract tests rejecting legacy false claims such as SQLite multi-host distributed workers or GEPA from import availability alone.
- [ ] Run plugin test suite, focused framework extension/API tests, syntax check, and a temporary-state worker smoke test. Do not claim real DSPy/GEPA validation without the pinned environment and explicit operator setup.

## Deferred approval-gated work

A small core shutdown extension seam in `run_ui.py` may be proposed after Task 7 if plugin-owned worker lifecycle cannot be safely terminated through existing plugin toggle/task mechanisms. `agent.py` and `initialize.py` remain untouched unless separate explicit approval is provided.

## Self-review

- RLM is first-class in Task 5 and feeds both heuristic and GEPA candidate engines in Task 8.
- Guidance injection, workers, dependency setup, GEPA, and replay all have independent release gates.
- All external models, installs, subprocesses, and network work are optional and blocked by safe defaults.
- SQLite is explicitly local-only; multi-host distributed mode is deferred to a PostgreSQL-backed phase.
