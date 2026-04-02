from __future__ import annotations

import asyncio
import sys
import threading
from pathlib import Path

import pytest
from flask import Flask

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent import AgentContext
from api.load_webui_extensions import LoadWebuiExtensions
from helpers import plugins
from helpers.errors import RepairableException
from initialize import initialize_agent
from usr.plugins.agent_harness.api.deerflow_core import DeerflowCore
from usr.plugins.agent_harness.api.memory_queue import MemoryQueue
from usr.plugins.agent_harness.api.run import Run
from usr.plugins.agent_harness.api.state import State
from usr.plugins.agent_harness.api.thread_data import ThreadData
from usr.plugins.agent_harness.extensions.python.tool_execute_before._20_harness_guardrails import (
    HarnessGuardrails,
)
from usr.plugins.agent_harness.helpers import runtime as harness_runtime
from usr.plugins.agent_harness.helpers.deerflow_sync import (
    list_public_skills,
    resolve_public_skills_root,
)
from usr.plugins.agent_harness.helpers.models import WorkspacePaths


def _new_app() -> Flask:
    app = Flask("test_agent_harness_plugin")
    app.secret_key = "test-secret"
    return app


def _new_context() -> AgentContext:
    return AgentContext(config=initialize_agent(), set_current=False)


def _run(awaitable):
    return asyncio.run(awaitable)


def _call_api(handler, payload: dict):
    return _run(handler.process(payload, None))


def test_agent_harness_plugin_metadata_and_defaults_are_present() -> None:
    meta = plugins.get_plugin_meta("agent_harness")
    assert meta is not None
    assert meta.name == "agent_harness"
    assert meta.settings_sections == ["agent", "developer"]
    assert meta.per_project_config is True
    assert meta.per_agent_config is True

    plugin_entry = next(
        item
        for item in plugins.get_enhanced_plugins_list(
            custom=True,
            builtin=False,
            plugin_names=["agent_harness"],
        )
        if item.name == "agent_harness"
    )
    assert plugin_entry.has_main_screen is True
    assert plugin_entry.has_config_screen is True

    defaults = harness_runtime.load_default_settings()
    assert defaults["ambient_assist_enabled"] is True
    assert defaults["default_deep_mode"] == "pro"
    assert defaults["memory_curation_enabled"] is True
    assert defaults["show_status_ui"] is True
    assert defaults["protected_paths"] == ["agent.py", "initialize.py", "usr/plugins/"]
    assert harness_runtime.get_mode_policy(defaults, "pro") == {
        "subagent_limit": 0,
        "repair_limit": 1,
    }
    assert harness_runtime.get_mode_policy(defaults, "ultra") == {
        "subagent_limit": 3,
        "repair_limit": 3,
    }


def test_agent_harness_deerflow_assets_are_present() -> None:
    plugin_root = PROJECT_ROOT / "usr/plugins/agent_harness"

    assert (plugin_root / "plugin.yaml").is_file()
    assert (plugin_root / "README.md").is_file()
    assert (plugin_root / "Install.md").is_file()
    assert (plugin_root / "scripts/check_deerflow_harness.py").is_file()
    assert (plugin_root / "scripts/import_deerflow_public_skills.py").is_file()
    assert (plugin_root / "api/deerflow_core.py").is_file()
    assert (plugin_root / "api/state.py").is_file()
    assert (plugin_root / "api/thread_data.py").is_file()
    assert (plugin_root / "api/thread_uploads.py").is_file()
    assert (plugin_root / "api/thread_artifacts.py").is_file()
    assert (plugin_root / "tools/harness_checkpoint.py").is_file()
    assert (plugin_root / "tools/harness_memory_propose.py").is_file()
    assert (plugin_root / "extensions/python/chat_model_call_after/_20_harness_cost.py").is_file()
    assert (plugin_root / "extensions/python/message_loop_prompts_after/_20_harness_runtime.py").is_file()
    assert (plugin_root / "extensions/python/monologue_start/_20_harness_workspace.py").is_file()
    assert (plugin_root / "extensions/python/tool_execute_after/_20_harness_tool_events.py").is_file()
    assert (plugin_root / "extensions/python/tool_execute_before/_20_harness_guardrails.py").is_file()
    assert (plugin_root / "extensions/webui/chat-input-progress-start/agent-harness-status.html").is_file()
    assert (plugin_root / "extensions/webui/sidebar-quick-actions-main-end/agent-harness-entry.html").is_file()
    assert (plugin_root / "helpers/deerflow_core.py").is_file()
    assert (plugin_root / "helpers/deerflow_client.py").is_file()
    assert (plugin_root / "webui/harness-store.js").is_file()
    assert (plugin_root / "webui/main.html").is_file()
    assert (plugin_root / "skills/public/bootstrap/SKILL.md").is_file()
    assert (plugin_root / "skills/public/find-skills/SKILL.md").is_file()


def test_deerflow_sync_resolves_public_skill_root_and_lists_skills(tmp_path: Path) -> None:
    repo_root = tmp_path / "deer-flow"
    public_root = repo_root / "skills" / "public"
    (public_root / "bootstrap").mkdir(parents=True)
    (public_root / "bootstrap" / "SKILL.md").write_text(
        "---\nname: bootstrap\ndescription: Bootstrap\n---\n",
        encoding="utf-8",
    )
    (public_root / "find-skills").mkdir(parents=True)
    (public_root / "find-skills" / "SKILL.md").write_text(
        "---\nname: find-skills\ndescription: Find Skills\n---\n",
        encoding="utf-8",
    )

    resolved = resolve_public_skills_root(repo_root)

    assert resolved == public_root
    assert list_public_skills(repo_root) == ["bootstrap", "find-skills"]


def test_create_run_record_uses_expected_phase_and_structure() -> None:
    defaults = harness_runtime.load_default_settings()

    run = harness_runtime.create_run_record(
        context_id="ctx-1234",
        mode="pro",
        objective="Implement a new Agent Zero plugin",
        constraints=["No core framework edits"],
        settings=defaults,
    )

    assert run.context_id == "ctx-1234"
    assert run.mode == "pro"
    assert run.phase == "inspect"
    assert run.status == "active"
    assert run.risk_level == "elevated"
    assert run.constraints == ["No core framework edits"]
    assert run.tasks == []
    assert run.checkpoints == []
    assert run.verification == []
    assert run.failures == []
    assert run.memory_candidates == []


@pytest.mark.parametrize(
    ("prepared_run", "tool_name", "tool_args", "reason_fragment"),
    [
        (
            harness_runtime.create_run_record(
                context_id="ctx-deps",
                mode="pro",
                objective="Install toolchain",
                constraints=[],
                settings=harness_runtime.load_default_settings(),
            ),
            "code_execution_tool",
            {
                "runtime": "terminal",
                "code": "pip install rich",
            },
            "dependency install",
        ),
        (
            harness_runtime.create_run_record(
                context_id="ctx-protected",
                mode="pro",
                objective="Patch protected file",
                constraints=[],
                settings=harness_runtime.load_default_settings(),
            ),
            "text_editor",
            {
                "path": str(PROJECT_ROOT / "agent.py"),
            },
            "protected path",
        ),
        (
            harness_runtime.create_run_record(
                context_id="ctx-breadth",
                mode="pro",
                objective="Rewrite many files",
                constraints=[],
                settings=harness_runtime.load_default_settings(),
            ).model_copy(
                update={
                    "touched_files": [
                        f"/tmp/harness-file-{index}.py" for index in range(8)
                    ]
                }
            ),
            "text_editor",
            {
                "path": "/tmp/harness-file-9.py",
            },
            "breadth",
        ),
    ],
)
def test_assess_tool_guardrail_requires_checkpoint_for_risky_actions(
    prepared_run: harness_runtime.RunRecord,
    tool_name: str,
    tool_args: dict,
    reason_fragment: str,
) -> None:
    checkpoint = harness_runtime.assess_tool_guardrail(
        run=prepared_run,
        tool_name=tool_name,
        tool_args=tool_args,
        settings=harness_runtime.load_default_settings(),
    )

    assert checkpoint is not None
    assert checkpoint.status == "pending"
    assert reason_fragment in checkpoint.reason.lower()


def test_run_api_start_status_checkpoint_and_stop_flow() -> None:
    context = _new_context()
    handler = Run(_new_app(), threading.RLock())

    start = _call_api(
        handler,
        {
            "action": "start",
            "context_id": context.id,
            "mode": "pro",
            "objective": "Ship the harness plugin",
            "constraints": ["Stay inside plugin seams"],
        },
    )

    assert start["success"] is True
    assert start["context_id"] == context.id
    assert start["run"]["mode"] == "pro"
    assert start["run"]["phase"] == "inspect"

    status = _call_api(
        handler,
        {
            "action": "status",
            "context_id": context.id,
        },
    )
    assert status["success"] is True
    assert status["run"]["objective"] == "Ship the harness plugin"

    run = harness_runtime.get_current_run(context)
    assert run is not None
    checkpoint = harness_runtime.assess_tool_guardrail(
        run=run,
        tool_name="code_execution_tool",
        tool_args={"runtime": "terminal", "code": "npm install"},
        settings=harness_runtime.load_default_settings(),
    )
    assert checkpoint is not None
    harness_runtime.save_current_run(context, run)

    approve = _call_api(
        handler,
        {
            "action": "checkpoint_decide",
            "context_id": context.id,
            "checkpoint_id": checkpoint.id,
            "decision": "approved",
        },
    )
    assert approve["success"] is True
    assert approve["run"]["phase"] == "implement"

    stop = _call_api(
        handler,
        {
            "action": "stop",
            "context_id": context.id,
        },
    )
    assert stop["success"] is True
    assert harness_runtime.get_current_run(context) is None


def test_memory_queue_accept_persists_rule_and_updates_candidate_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _new_context()
    run = harness_runtime.create_run_record(
        context_id=context.id,
        mode="pro",
        objective="Learn repo conventions",
        constraints=[],
        settings=harness_runtime.load_default_settings(),
    )
    candidate = harness_runtime.propose_memory_candidate(
        run=run,
        rule_text="Use rg before grep for repo search.",
        reason="It is faster and already the local convention.",
        source="agent_harness",
        scope="project",
        confidence=0.91,
    )
    harness_runtime.save_current_run(context, run)

    persisted_settings: dict[str, object] = {}

    monkeypatch.setattr(
        harness_runtime,
        "load_effective_settings",
        lambda *args, **kwargs: {
            **harness_runtime.load_default_settings(),
            "accepted_rules": [],
        },
    )
    monkeypatch.setattr(
        harness_runtime,
        "persist_scope_settings",
        lambda **kwargs: persisted_settings.update(kwargs["settings"]),
    )
    monkeypatch.setattr(
        harness_runtime,
        "maybe_mirror_rule_to_memory",
        lambda **kwargs: None,
    )

    handler = MemoryQueue(_new_app(), threading.RLock())
    accepted = _call_api(
        handler,
        {
            "action": "accept",
            "context_id": context.id,
            "candidate_id": candidate.id,
            "scope": "project",
            "project_name": "demo-project",
        },
    )

    assert accepted["success"] is True
    assert accepted["candidate"]["status"] == "accepted"
    assert persisted_settings["accepted_rules"][0]["rule_text"] == (
        "Use rg before grep for repo search."
    )


def test_state_api_returns_dashboard_run_and_pending_items() -> None:
    context = _new_context()
    defaults = harness_runtime.load_default_settings()
    run = harness_runtime.create_run_record(
        context_id=context.id,
        mode="ultra",
        objective="Harden the harness",
        constraints=[],
        settings=defaults,
    )
    harness_runtime.request_checkpoint(
        run,
        reason="Checkpoint required for dependency install in deep harness mode.",
        proposed_action="pip install rich",
        tool_name="code_execution_tool",
        tool_args={"runtime": "terminal", "code": "pip install rich"},
        risk_level="high",
    )
    harness_runtime.propose_memory_candidate(
        run=run,
        rule_text="Run focused tests before the whole suite.",
        reason="Keeps verification loops tight.",
        source="agent_harness",
        scope="project",
        confidence=0.88,
    )
    harness_runtime.record_verification(
        run,
        name="pytest",
        status="passed",
        summary="2 passed",
    )
    harness_runtime.save_current_run(context, run)

    handler = State(_new_app(), threading.RLock())
    response = _call_api(handler, {"context_id": context.id})

    assert response["success"] is True
    assert response["dashboard"]["default_deep_mode"] == "pro"
    assert response["run"]["objective"] == "Harden the harness"
    assert len(response["pending_checkpoints"]) == 1
    assert len(response["pending_memory_candidates"]) == 1
    assert response["latest_verification"]["status"] == "passed"


def test_guardrail_extension_blocks_risky_tool_execution_and_creates_checkpoint() -> None:
    context = _new_context()
    run = harness_runtime.create_run_record(
        context_id=context.id,
        mode="pro",
        objective="Protect the repo",
        constraints=[],
        settings=harness_runtime.load_default_settings(),
    )
    harness_runtime.save_current_run(context, run)

    extension = HarnessGuardrails(agent=context.get_agent())

    with pytest.raises(RepairableException):
        _run(
            extension.execute(
                tool_name="code_execution_tool",
                tool_args={"runtime": "terminal", "code": "pip install rich"},
            )
        )

    refreshed = harness_runtime.get_current_run(context)
    assert refreshed is not None
    checkpoint = harness_runtime.get_pending_checkpoint(refreshed)
    assert checkpoint is not None
    assert "dependency install" in checkpoint.reason.lower()


def test_deerflow_core_api_returns_gateway_like_state(monkeypatch) -> None:
    context = _new_context()
    workspace = WorkspacePaths(
        root="/tmp/.harness",
        workspace="/tmp/.harness/threads/ctx/user-data/workspace",
        outputs="/tmp/.harness/threads/ctx/user-data/outputs",
        uploads="/tmp/.harness/threads/ctx/user-data/uploads",
        offloads="/tmp/.harness/offloads",
        runs="/tmp/.harness/runs",
        thread_root="/tmp/.harness/threads/ctx",
        user_data="/tmp/.harness/threads/ctx/user-data",
    )

    from usr.plugins.agent_harness.helpers import deerflow_core

    monkeypatch.setattr(deerflow_core, "ensure_context_workspace", lambda _context: workspace)
    monkeypatch.setattr(
        deerflow_core,
        "list_configured_models",
        lambda _agent: [{"kind": "chat", "provider": "openai", "name": "gpt-test"}],
    )
    monkeypatch.setattr(
        deerflow_core,
        "list_skill_entries",
        lambda _agent, limit=50: [{"name": "bootstrap", "description": "Setup", "path": "/tmp/bootstrap"}],
    )

    async def fake_memory_status(_context):
        return {
            "enabled": True,
            "current_subdir": "default",
            "available_subdirs": ["default"],
            "storage_path": "/tmp/memory/default",
        }

    monkeypatch.setattr(deerflow_core, "get_memory_status", fake_memory_status)

    payload = _call_api(DeerflowCore(_new_app(), threading.Lock()), {"context_id": context.id})

    assert payload["success"] is True
    assert payload["thread"]["thread_root"] == workspace.thread_root
    assert payload["models"][0]["name"] == "gpt-test"
    assert payload["skills"][0]["name"] == "bootstrap"
    assert payload["memory"]["enabled"] is True


def test_thread_data_api_can_cleanup_workspace(monkeypatch) -> None:
    context = _new_context()

    from usr.plugins.agent_harness.helpers.deerflow_client import DeerFlowClient

    monkeypatch.setattr(
        DeerFlowClient,
        "cleanup_thread",
        lambda self: {"thread_root": "/tmp/thread", "artifact_count": 0, "upload_count": 0},
    )

    payload = _call_api(
        ThreadData(_new_app(), threading.Lock()),
        {"context_id": context.id, "action": "cleanup"},
    )

    assert payload["success"] is True
    assert payload["thread"]["thread_root"] == "/tmp/thread"


def test_render_system_prompt_includes_mode_policy_and_accepted_rules() -> None:
    defaults = harness_runtime.load_default_settings()
    run = harness_runtime.create_run_record(
        context_id="ctx-prompt",
        mode="ultra",
        objective="Implement and verify the harness",
        constraints=["No core rewrites"],
        settings=defaults,
    )
    prompt = harness_runtime.render_system_prompt(
        settings=defaults,
        run=run,
        accepted_rules=[
            {
                "scope": "project",
                "rule_text": "Run file-scoped pytest first before the full suite.",
                "reason": "Keeps verification loops tight.",
            }
        ],
    )

    assert "ULTRA MODE" in prompt
    assert "Implement and verify the harness" in prompt
    assert "Run file-scoped pytest first before the full suite." in prompt
    assert "3 parallel sub-agents" in prompt


def test_agent_harness_webui_extensions_are_discoverable() -> None:
    handler = LoadWebuiExtensions(_new_app(), threading.RLock())

    quick_actions = _call_api(
        handler,
        {
            "extension_point": "sidebar-quick-actions-main-end",
            "filters": ["*.html"],
        },
    )
    status_strip = _call_api(
        handler,
        {
            "extension_point": "chat-input-progress-start",
            "filters": ["*.html"],
        },
    )

    assert any(
        "agent_harness/extensions/webui/sidebar-quick-actions-main-end/"
        in extension
        for extension in quick_actions["extensions"]
    )
    assert any(
        "agent_harness/extensions/webui/chat-input-progress-start/"
        in extension
        for extension in status_strip["extensions"]
    )
