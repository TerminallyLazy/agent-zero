"""Tests for the jcode_coder agent profile.

A0 loads system-prompt content from `<profile>/prompts/agent.system.main.*.md`.
The `context:` field in `agent.yaml` is short tooltip text shown in A0's
profile picker — it does NOT reach the LLM as a system prompt. Verified by
inspecting `agents/developer/` and `agents/hacker/` (both ship a long
`prompts/agent.system.main.specifics.md` and a one-line `context:`).

Regression: 2026-05-05 — initial jcode_coder/agent.yaml stuffed the routing
rules into the multi-line `context:` field, so the model never saw the
`call jcode_session` directive. Symptoms: user reported A0 ran a complex
build with no jcode usage at all.
"""

from __future__ import annotations

from pathlib import Path

import yaml

PROFILE_DIR = (
    Path(__file__).resolve().parents[2]
    / "agents"
    / "jcode_coder"
)
AGENT_YAML = PROFILE_DIR / "agent.yaml"
SPECIFICS_MD = PROFILE_DIR / "prompts" / "agent.system.main.specifics.md"


def test_profile_yaml_is_short_metadata():
    assert AGENT_YAML.exists(), f"missing {AGENT_YAML}"
    data = yaml.safe_load(AGENT_YAML.read_text(encoding="utf-8"))
    assert data["title"] == "jcode Coder"
    assert "description" in data
    # `context` is the picker tooltip; A0 convention is one line.
    # If it grows multi-line again, the routing rules belong in
    # prompts/agent.system.main.specifics.md instead.
    ctx = (data.get("context") or "").strip()
    assert "\n" not in ctx, (
        "agent.yaml `context:` must be a one-line tooltip; "
        "system-prompt content goes in prompts/agent.system.main.specifics.md"
    )


def test_profile_has_specifics_prompt_file():
    """Without this file A0 falls back to the default profile prompt and
    the model never sees the routing directive."""
    assert SPECIFICS_MD.exists(), (
        f"missing {SPECIFICS_MD} — A0 needs this for the system prompt"
    )


def test_specifics_prompt_directs_to_jcode_session():
    """The prompt MUST mention jcode_session by name. Otherwise the LLM
    has no idea the tool exists and won't route to it."""
    text = SPECIFICS_MD.read_text(encoding="utf-8")
    assert "jcode_session" in text, (
        "specifics.md must reference jcode_session — that's the whole point"
    )
    # The other six tools should also be mentioned so the model can
    # route to the lighter-weight options where appropriate.
    for tool in (
        "jcode_grep",
        "jcode_memory",
        "jcode_skill",
        "jcode_resume",
        "jcode_swarm_msg",
        "jcode_self_dev",
    ):
        assert tool in text, f"specifics.md should reference {tool}"


def test_specifics_prompt_has_explicit_routing_rules():
    """Vague hints don't move LLMs. Lock in concrete routing rules."""
    text = SPECIFICS_MD.read_text(encoding="utf-8").lower()
    # At least one explicit "call jcode_session" / "use jcode_session" form
    assert any(
        marker in text
        for marker in ("call jcode_session", "call `jcode_session`")
    ), "prompt must contain an explicit imperative to call jcode_session"
    # Routing examples (the model copies patterns it sees demonstrated)
    assert "user:" in text, "prompt should include routing examples"
