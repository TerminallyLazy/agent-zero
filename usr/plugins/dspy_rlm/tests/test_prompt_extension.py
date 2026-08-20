"""Isolated tests for the DSPy RLM system-prompt extension seam."""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from types import SimpleNamespace
from typing import Any

import pytest

from usr.plugins.dspy_rlm.helpers import guidance
from usr.plugins.dspy_rlm.extensions.python.system_prompt._30_dspy_rlm_guidance import (
    DspyRlmGuidance,
)


_HASH_A = "sha256:" + "a" * 64
_HASH_B = "sha256:" + "b" * 64
_NOW = datetime(2030, 1, 1, tzinfo=timezone.utc)


def _artifact() -> guidance.GuidanceArtifact:
    return guidance.GuidanceArtifact.create(
        artifact_id="artifact-01",
        context_id="context-01",
        objective_bucket="reasoning",
        rules=[{"type": "verify_tool_contract"}],
        source_manifest_hashes=[_HASH_A],
        source_finding_hashes=[_HASH_B],
        issued_at="2029-12-31T00:00:00Z",
        expires_at="2030-01-31T00:00:00Z",
        engine_kind="heuristic",
        engine_version="v1",
    )


def _agent() -> SimpleNamespace:
    return SimpleNamespace(context=SimpleNamespace(id="context-01"))


def _config(*, inject: bool, max_chars: int | None = None) -> dict[str, Any]:
    prompt: dict[str, Any] = {"inject_guidance": inject}
    if max_chars is not None:
        prompt["max_injected_chars"] = max_chars
    return {"enabled": True, "prompt": prompt}


@pytest.mark.asyncio
async def test_extension_injects_only_fixed_rendering_of_the_selected_artifact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    extension = DspyRlmGuidance(agent=_agent())
    artifact = _artifact()
    prompt: list[str] = ["core system prompt"]

    monkeypatch.setattr(
        "usr.plugins.dspy_rlm.extensions.python.system_prompt._30_dspy_rlm_guidance.config_module.load_config",
        lambda agent: _config(inject=True),
    )
    monkeypatch.setattr(
        "usr.plugins.dspy_rlm.extensions.python.system_prompt._30_dspy_rlm_guidance.state.load_context_state",
        lambda context_id: {"last_objective_bucket": "reasoning"},
    )
    monkeypatch.setattr(
        "usr.plugins.dspy_rlm.extensions.python.system_prompt._30_dspy_rlm_guidance.guidance.select_active_guidance_artifact",
        lambda context_id, bucket: artifact,
    )
    # Freeze the renderer's expiry reference while retaining the real public renderer.
    original_render = guidance.render_guidance_artifact
    expected = original_render(artifact, now=_NOW)
    monkeypatch.setattr(
        "usr.plugins.dspy_rlm.extensions.python.system_prompt._30_dspy_rlm_guidance.guidance.render_guidance_artifact",
        lambda value, *, max_chars: original_render(value, max_chars=max_chars, now=_NOW),
    )

    await extension.execute(system_prompt=prompt)

    assert prompt == ["core system prompt", expected]


@pytest.mark.asyncio
async def test_runtime_policy_injection_gate_stops_before_state_or_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    extension = DspyRlmGuidance(agent=_agent())
    prompt: list[str] = []

    monkeypatch.setattr(
        "usr.plugins.dspy_rlm.extensions.python.system_prompt._30_dspy_rlm_guidance.config_module.load_config",
        lambda agent: _config(inject=False),
    )
    monkeypatch.setattr(
        "usr.plugins.dspy_rlm.extensions.python.system_prompt._30_dspy_rlm_guidance.state.load_context_state",
        pytest.fail,
    )
    monkeypatch.setattr(
        "usr.plugins.dspy_rlm.extensions.python.system_prompt._30_dspy_rlm_guidance.guidance.select_active_guidance_artifact",
        pytest.fail,
    )

    await extension.execute(system_prompt=prompt)

    assert prompt == []


@pytest.mark.asyncio
async def test_extension_fails_closed_when_the_configured_render_limit_is_too_small(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    extension = DspyRlmGuidance(agent=_agent())
    artifact = _artifact()
    prompt: list[str] = []

    monkeypatch.setattr(
        "usr.plugins.dspy_rlm.extensions.python.system_prompt._30_dspy_rlm_guidance.config_module.load_config",
        lambda agent: _config(inject=True, max_chars=1),
    )
    monkeypatch.setattr(
        "usr.plugins.dspy_rlm.extensions.python.system_prompt._30_dspy_rlm_guidance.state.load_context_state",
        lambda context_id: {"last_objective_bucket": "reasoning"},
    )
    monkeypatch.setattr(
        "usr.plugins.dspy_rlm.extensions.python.system_prompt._30_dspy_rlm_guidance.guidance.select_active_guidance_artifact",
        lambda context_id, bucket: artifact,
    )

    await extension.execute(system_prompt=prompt)

    assert prompt == []
