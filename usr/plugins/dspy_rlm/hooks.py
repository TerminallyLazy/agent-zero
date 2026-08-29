"""Plugin configuration hooks and isolated worker dependency setup."""
from __future__ import annotations

import threading
from typing import Any

from helpers.print_style import PrintStyle

from usr.plugins.dspy_rlm.helpers import dependencies
from usr.plugins.dspy_rlm.helpers import config as config_module


PLUGIN_NAME = "dspy_rlm"
_dependency_thread: threading.Thread | None = None
_dependency_thread_lock = threading.Lock()


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
    try:
        from usr.plugins.dspy_rlm.helpers.worker_supervisor import reconcile
        reconcile(normalized)
    except Exception as exc:
        PrintStyle.error(f"{PLUGIN_NAME}: worker reconciliation failed: {exc}")
    return normalized


def dependency_status() -> tuple[bool, list[str]]:
    """Report readiness of the isolated worker environment."""
    report = dependencies.dependency_diagnostics()
    return bool(report["ready"]), [str(item) for item in report["missing"]]


def dependency_install_plan() -> dict[str, Any]:
    """Return the manual, blocked-until-hashed operator setup plan without executing it."""
    return dependencies.manual_setup_plan()


def dependency_install_command_strings(config: dict[str, Any] | None = None) -> list[str]:
    """Return the exact commands used by the isolated setup action."""
    _ = config
    return list(dependencies.manual_setup_plan()["commands_for_operator_review"])


def dependency_install_commands(config: dict[str, Any] | None = None) -> list[str]:
    return dependency_install_command_strings(config)


def dependency_report() -> dict[str, Any]:
    plan = dependency_install_plan()
    plan["message"] = "Dependencies are installed only in the plugin worker virtual environment."
    return plan


def install() -> dict[str, Any]:
    """Install pinned dependencies into the isolated worker environment."""
    result = dependencies.install_worker_environment()
    try:
        from usr.plugins.dspy_rlm.helpers.worker_supervisor import reconcile
        result["workers"] = reconcile(config_module.load_config())
    except Exception as exc:
        result["workers"] = {"reason": f"reconciliation_failed:{type(exc).__name__}"}
    return result


def pre_update() -> dict[str, Any]:
    """Refresh the isolated environment without mutating the host interpreter."""
    return install()


def uninstall() -> dict[str, int]:
    from usr.plugins.dspy_rlm.helpers.worker_supervisor import stop_all
    return stop_all()


def ensure_dependencies(raise_on_error: bool = True) -> bool:
    try:
        return bool(dependencies.install_worker_environment()["ok"])
    except Exception:
        if raise_on_error:
            raise
        return False


def ensure_dependencies_background(config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Repair an ephemeral worker environment without delaying WebUI startup."""
    global _dependency_thread

    cfg = _safe_normalize_config(config if config is not None else config_module.load_config(), "startup")
    dependency_cfg = cfg.get("dependencies") if isinstance(cfg.get("dependencies"), dict) else {}
    if not bool(cfg.get("enabled", False)):
        return {"started": False, "reason": "plugin_disabled"}
    if not bool(dependency_cfg.get("ensure_at_startup", True)):
        return {"started": False, "reason": "startup_install_disabled"}
    if dependencies.dependency_diagnostics()["ready"]:
        return {"started": False, "reason": "ready"}

    with _dependency_thread_lock:
        if _dependency_thread and _dependency_thread.is_alive():
            return {"started": False, "reason": "already_running"}
        _dependency_thread = threading.Thread(
            target=_install_dependencies_safely,
            name="dspy-rlm-dependency-install",
            daemon=True,
        )
        _dependency_thread.start()
    return {"started": True, "reason": "worker_environment_not_ready"}


def _install_dependencies_safely() -> None:
    try:
        dependencies.install_worker_environment()
        PrintStyle.info(f"{PLUGIN_NAME}: isolated worker environment ready")
    except Exception as exc:
        PrintStyle.warning(f"{PLUGIN_NAME}: startup dependency preparation failed:", exc)


def load_default_config() -> dict[str, Any]:
    return config_module._load_default()
