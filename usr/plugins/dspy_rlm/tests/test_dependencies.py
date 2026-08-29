"""Isolated worker dependency setup contracts."""
from __future__ import annotations

from usr.plugins.dspy_rlm.helpers import dependencies


def test_current_worker_pins_include_rlm_gepa_and_cli() -> None:
    assert dependencies.locked_requirements() == [
        "dspy[deno]==3.3.1",
        "gepa[dspy]==0.1.4",
        "dspy-cli==0.1.13",
    ]


def test_setup_plan_targets_only_the_isolated_worker() -> None:
    plan = dependencies.manual_setup_plan()
    assert plan["mode"] == "isolated_worker_venv"
    assert plan["execution_performed"] is False
    assert "worker-venv" in plan["isolated_worker_venv"]
    assert all("worker-venv" in command for command in plan["commands_for_operator_review"])


def test_diagnostics_fail_closed_without_a_matching_marker(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(dependencies, "WORKER_VENV", tmp_path / "worker-venv")
    monkeypatch.setattr(dependencies, "WORKER_PYTHON", tmp_path / "worker-venv" / "bin" / "python")
    monkeypatch.setattr(dependencies, "INSTALL_MARKER", tmp_path / "worker-env.json")
    report = dependencies.dependency_diagnostics()
    assert report["ready"] is False
    assert report["missing"]
