"""Plugin configuration hooks and non-executing dependency diagnostics.

The plugin never installs, repairs, or probes packages through subprocesses.
DSPy/GEPA setup is an explicit operator action in an isolated worker environment;
see :mod:`usr.plugins.dspy_rlm.execute` for its review-only setup plan.
"""
from __future__ import annotations

from typing import Any

from helpers.print_style import PrintStyle

from usr.plugins.dspy_rlm import execute
from usr.plugins.dspy_rlm.helpers import config as config_module


PLUGIN_NAME = "dspy_rlm"


def get_plugin_config(default: dict[str, Any] | None = None, **_kwargs: Any) -> dict[str, Any]:
    """Normalize the framework-resolved effective configuration at the plugin seam."""
    return _safe_normalize_config(default, "get_plugin_config")


def _safe_normalize_config(config: dict[str, Any] | None, context: str) -> dict[str, Any]:
    try:
        return config_module.normalize_config(config)
    except Exception as exc:
        PrintStyle.error(f"{PLUGIN_NAME}: failed to normalize config for {context}: {exc}")
        return config_module.normalize_config(None)


def save_plugin_config(settings: dict[str, Any] | None = None, **_kwargs: Any) -> dict[str, Any]:
    normalized = _safe_normalize_config(settings, "save_plugin_config")
    if settings is not None and not isinstance(settings, dict):
        PrintStyle.error(f"{PLUGIN_NAME}: save_plugin_config received non-dict settings; persisted fallback used")
    return normalized


def dependency_status() -> tuple[bool, list[str]]:
    """Report only current imports; never trigger setup or package resolution."""
    report = execute.dependency_diagnostics()
    return bool(report["ready"]), [str(item) for item in report["missing"]]


def dependency_install_plan() -> dict[str, Any]:
    """Return the manual, blocked-until-hashed operator setup plan without executing it."""
    return execute.manual_setup_plan()


def dependency_install_command_strings(config: dict[str, Any] | None = None) -> list[str]:
    """Compatibility display helper; commands are illustrative, never invoked here."""
    _ = config
    return list(execute.manual_setup_plan()["commands_for_operator_review"])


def dependency_install_commands(config: dict[str, Any] | None = None) -> list[str]:
    return dependency_install_command_strings(config)


def dependency_report() -> dict[str, Any]:
    plan = dependency_install_plan()
    plan["message"] = (
        "Manual isolated worker setup is required; no dependency operation was performed."
    )
    return plan


def install() -> dict[str, Any]:
    """Legacy hook name retained as a safe diagnostic, not an installer."""
    plan = dependency_install_plan()
    return {
        "ok": False,
        "execution_performed": False,
        "reason": "manual_operator_setup_required",
        "plan": plan,
    }


def pre_update() -> dict[str, Any]:
    """Updates must not mutate the host interpreter or perform package setup."""
    return install()


def ensure_dependencies(raise_on_error: bool = True) -> bool:
    """Compatibility check with no remediation side effects."""
    _ = raise_on_error
    return dependency_status()[0]


def load_default_config() -> dict[str, Any]:
    return config_module._load_default()
