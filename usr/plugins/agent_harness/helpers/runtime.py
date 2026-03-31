"""Backward-compat facade. Import from specific modules instead.

This module re-exports all public names from the new modular structure
so that existing code using `from usr.plugins.agent_harness.helpers import runtime`
continues to work unchanged. Deprecated — migrate to direct imports in Phase 2.
"""
from __future__ import annotations

import inspect
from typing import Any

from agent import AgentContext

# Models & constants
from usr.plugins.agent_harness.helpers.models import *  # noqa: F401,F403
# Settings
from usr.plugins.agent_harness.helpers.settings import *  # noqa: F401,F403
# Guardrails
from usr.plugins.agent_harness.helpers.guardrails import *  # noqa: F401,F403
# Lifecycle
from usr.plugins.agent_harness.helpers.lifecycle import *  # noqa: F401,F403
# Memory (most names; accept_memory_candidate overridden below for monkeypatch compat)
from usr.plugins.agent_harness.helpers.memory import (  # noqa: F401
    propose_memory_candidate,
    find_memory_candidate,
    maybe_mirror_rule_to_memory,
    reject_memory_candidate,
)
# Renderer
from usr.plugins.agent_harness.helpers.renderer import *  # noqa: F401,F403
# Phase 2 modules
from usr.plugins.agent_harness.helpers.planner import *  # noqa: F401,F403
from usr.plugins.agent_harness.helpers.orchestrator import *  # noqa: F401,F403
# Phase 3 modules
from usr.plugins.agent_harness.helpers.context_engine import *  # noqa: F401,F403
from usr.plugins.agent_harness.helpers.workspace import *  # noqa: F401,F403
from usr.plugins.agent_harness.helpers.cost_tracker import *  # noqa: F401,F403
# Parallel dispatch
from usr.plugins.agent_harness.helpers.parallel import *  # noqa: F401,F403

# Re-import models needed for the accept_memory_candidate override
from usr.plugins.agent_harness.helpers.models import MemoryCandidate, MemoryScope
from usr.plugins.agent_harness.helpers.settings import (
    load_scope_settings as _load_scope_settings,
    _merge_unique_rules as _merge_unique_rules_fn,
)
from usr.plugins.agent_harness.helpers.lifecycle import (
    get_current_run as _get_current_run,
    save_current_run as _save_current_run,
)
from usr.plugins.agent_harness.helpers.memory import (
    find_memory_candidate as _find_memory_candidate,
)
from usr.plugins.agent_harness.helpers.models import now_iso as _now_iso


async def accept_memory_candidate(
    *,
    context: AgentContext,
    candidate_id: str,
    scope: MemoryScope,
    project_name: str = "",
    agent_profile: str = "",
) -> MemoryCandidate:
    """Facade override — calls persist_scope_settings and maybe_mirror_rule_to_memory
    through this module's namespace so monkeypatching runtime.persist_scope_settings
    and runtime.maybe_mirror_rule_to_memory is interceptable by tests."""
    import sys
    _this = sys.modules[__name__]

    run = _get_current_run(context)
    if not run:
        raise ValueError("No active harness run found")
    candidate = _find_memory_candidate(run, candidate_id)
    candidate.status = "accepted"
    candidate.scope = scope
    candidate.decided_at = _now_iso()

    scope_settings = _load_scope_settings(
        scope=scope,
        project_name=project_name,
        agent_profile=agent_profile,
    )
    accepted_rules = list(scope_settings.get("accepted_rules", []))
    accepted_rules = _merge_unique_rules_fn(
        accepted_rules,
        [
            {
                "scope": scope,
                "rule_text": candidate.rule_text,
                "reason": candidate.reason,
                "source": candidate.source,
                "confidence": candidate.confidence,
                "accepted_at": candidate.decided_at,
            }
        ],
    )
    scope_settings["accepted_rules"] = accepted_rules

    # Call through this module's namespace so monkeypatching runtime.persist_scope_settings
    # is intercepted correctly.
    _this.persist_scope_settings(
        scope=scope,
        settings=scope_settings,
        project_name=project_name,
        agent_profile=agent_profile,
    )
    _save_current_run(context, run)
    mirror_result = _this.maybe_mirror_rule_to_memory(
        agent=context.get_agent(),
        candidate=candidate,
    )
    if inspect.isawaitable(mirror_result):
        await mirror_result
    return candidate
