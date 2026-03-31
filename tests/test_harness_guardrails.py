from __future__ import annotations
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from usr.plugins.agent_harness.helpers.models import RunRecord, now_iso, new_id


def _make_run(**overrides) -> RunRecord:
    ts = now_iso()
    defaults = {
        "run_id": new_id("run"), "context_id": "ctx-test", "mode": "build",
        "objective": "Test", "phase": "inspect", "status": "active",
        "risk_level": "elevated", "created_at": ts, "updated_at": ts,
    }
    defaults.update(overrides)
    return RunRecord(**defaults)


def _default_settings() -> dict:
    from usr.plugins.agent_harness.helpers.settings import load_default_settings
    return load_default_settings()


def test_protected_path_matches_glob_pattern():
    from usr.plugins.agent_harness.helpers.guardrails import _is_protected_path
    settings = {"protected_paths": ["agent.py", "usr/plugins/*"]}
    assert _is_protected_path("agent.py", settings) is True
    assert _is_protected_path("usr/plugins/my_plugin.py", settings) is True
    assert _is_protected_path("helpers/utils.py", settings) is False


def test_dependency_install_triggers_checkpoint():
    from usr.plugins.agent_harness.helpers.guardrails import assess_tool_guardrail
    run = _make_run()
    checkpoint = assess_tool_guardrail(
        run=run, tool_name="code_execution_tool",
        tool_args={"runtime": "terminal", "code": "pip install rich"},
        settings=_default_settings(),
    )
    assert checkpoint is not None
    assert "dependency install" in checkpoint.reason.lower()


def test_destructive_command_triggers_checkpoint():
    from usr.plugins.agent_harness.helpers.guardrails import assess_tool_guardrail
    run = _make_run()
    checkpoint = assess_tool_guardrail(
        run=run, tool_name="code_execution_tool",
        tool_args={"runtime": "terminal", "code": "rm -rf /tmp/test"},
        settings=_default_settings(),
    )
    assert checkpoint is not None
    assert checkpoint.risk_level == "critical"


def test_harness_tools_are_exempt_from_guardrails():
    from usr.plugins.agent_harness.helpers.guardrails import assess_tool_guardrail
    run = _make_run()
    for tool_name in ["harness_run", "harness_checkpoint", "harness_memory_propose"]:
        checkpoint = assess_tool_guardrail(
            run=run, tool_name=tool_name, tool_args={}, settings=_default_settings(),
        )
        assert checkpoint is None


def test_edit_breadth_limit_triggers_checkpoint():
    from usr.plugins.agent_harness.helpers.guardrails import assess_tool_guardrail
    run = _make_run(touched_files=[f"/tmp/file-{i}.py" for i in range(8)])
    checkpoint = assess_tool_guardrail(
        run=run, tool_name="text_editor", tool_args={"path": "/tmp/new-file.py"},
        settings=_default_settings(),
    )
    assert checkpoint is not None
    assert "breadth" in checkpoint.reason.lower()


def test_pending_checkpoint_is_returned_instead_of_new():
    from usr.plugins.agent_harness.helpers.guardrails import assess_tool_guardrail
    from usr.plugins.agent_harness.helpers.models import CheckpointRecord
    run = _make_run()
    run.checkpoints.append(CheckpointRecord(
        id="chk_existing", reason="Existing", proposed_action="test",
        status="pending", created_at=now_iso(),
    ))
    checkpoint = assess_tool_guardrail(
        run=run, tool_name="code_execution_tool",
        tool_args={"runtime": "terminal", "code": "pip install foo"},
        settings=_default_settings(),
    )
    assert checkpoint is not None
    assert checkpoint.id == "chk_existing"
