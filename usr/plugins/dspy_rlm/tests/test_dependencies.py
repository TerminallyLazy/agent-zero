"""Dependency-plan tests that do not install, execute subprocesses, or use a network."""
from __future__ import annotations

from pathlib import Path

from usr.plugins.dspy_rlm import execute


def test_checked_in_lock_is_explicitly_diagnostic_not_hash_ready() -> None:
    report = execute.dependency_diagnostics()

    assert report["exact_requirements"] == ["dspy-ai==2.6.27", "gepa==0.0.17"]
    assert report["hash_complete"] is False
    assert report["ready"] is False
    assert "lock_manifest_missing_hashes" in report["diagnostics"]


def test_manual_plan_is_blocked_and_worker_isolated() -> None:
    plan = execute.manual_setup_plan()

    assert plan["ok"] is False
    assert plan["execution_performed"] is False
    assert plan["mode"] == "manual_explicit_setup_only"
    assert plan["trusted_index_required"] is True
    assert plan["hashes_required"] is True
    assert "lock_manifest_missing_hashes" in plan["blockers"]
    assert "operator_must_explicitly_execute_plan" in plan["blockers"]
    assert "worker-venv" in plan["isolated_worker_venv"]


def test_readme_has_no_host_install_command_and_declares_lock_not_installable() -> None:
    readme = (Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8")

    assert "**not installable**" in readme
    assert "pip install" not in readme
    assert "/Users/lazy/" not in readme
