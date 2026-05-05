# Spike 0.3: `provider_session_id` cache warmth round-trip

**Date:** 2026-05-05
**Spec ref:** §6.3, §10, §11
**Status:** Deferred to integration phase

## Why deferred

Verifying upstream-provider cache warmth on cross-harness resume requires:

1. Configured Claude / OpenAI / Gemini credentials (real, not dummy)
2. An existing seeded session in another harness (Claude Code at `~/.claude/`, Codex at
   `~/.codex/`, etc.) that hasn't aged past the provider's cache TTL (Anthropic's KV cache TTL
   is 5 minutes per spec §6.3)
3. Resuming that session via jcode and inspecting `cache_read_input_tokens` vs
   `cache_creation_input_tokens` from the first turn after resume

Real OAuth/API key auth + scripted multi-tool conversation is out of scope for this
brainstorm/plan session.

## Acceptance per spec §10 (downgrade-tolerant)

Spec already declares cache-warmth on resume as downgrade-tolerant: resume passes acceptance
even when the provider's KV cache has been evicted (one-time cache-creation cost on first turn,
warm thereafter). This means the spike is **observability**, not gating.

## Plan path forward

Defer to **integration testing phase**. Add an opt-in benchmark
`tests/perf/test_cross_harness_cache_warmth.py` requiring:

```bash
JCODE_TEST_CLAUDE_SESSION_ID=<seeded-session-id> \
  pytest tests/perf/test_cross_harness_cache_warmth.py
```

Test logic:

1. Find seeded session (skip if env var not set)
2. Resume via plugin's `JcodeResume` tool
3. Send one short prompt
4. Capture `TokenUsage` event
5. Record `cache_read_input_tokens` / `cache_creation_input_tokens` ratios
6. Report — never fail (downgrade-tolerant)

## Plan impact

Plan Task 12.6 acceptance criterion already says "downgrade-tolerant"; no further change
needed. Add the opt-in perf test to Chunk 12 task list.
