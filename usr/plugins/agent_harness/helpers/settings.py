from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from agent import Agent, AgentContext
from helpers import files, plugins, projects, yaml as yaml_helper

from usr.plugins.agent_harness.helpers.models import (
    PLUGIN_NAME, HarnessMode, MemoryScope, DEFAULT_DEEP_MODE, _plugin_dir,
    normalize_harness_mode,
)

CURRENT_CONFIG_VERSION = 3


def load_default_settings() -> dict[str, Any]:
    default_path = files.get_abs_path(_plugin_dir(), plugins.CONFIG_DEFAULT_FILE_NAME)
    if files.exists(default_path):
        return yaml_helper.loads(files.read_file(default_path))
    return {
        "ambient_assist_enabled": True,
        "default_deep_mode": "pro",
        "memory_curation_enabled": True,
        "show_status_ui": True,
        "max_auto_edit_files": 8,
        "dependency_install_requires_checkpoint": True,
        "destructive_actions_require_checkpoint": True,
        "protected_paths": ["agent.py", "initialize.py", "usr/plugins/"],
        "accepted_rules": [],
        "mode_policies": {
            "flash": {"subagent_limit": 0, "repair_limit": 0},
            "standard": {"subagent_limit": 0, "repair_limit": 1},
            "pro": {"subagent_limit": 0, "repair_limit": 1},
            "ultra": {"subagent_limit": 3, "repair_limit": 3},
        },
    }


def _merge_unique_rules(
    base_rules: list[dict[str, Any]],
    extra_rules: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged = list(base_rules)
    seen = {str(rule.get("rule_text", "")).strip().lower() for rule in merged}
    for rule in extra_rules:
        text = str(rule.get("rule_text", "")).strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        merged.append(rule)
        seen.add(key)
    return merged


def _deep_merge_settings(
    base: dict[str, Any],
    override: dict[str, Any],
) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in override.items():
        if key == "accepted_rules":
            result[key] = _merge_unique_rules(
                list(result.get(key, [])),
                list(value or []),
            )
            continue
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge_settings(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def _load_json_if_exists(path: str) -> dict[str, Any]:
    if not path or not files.exists(path):
        return {}
    return json.loads(files.read_file(path))


def resolve_context(context_id: str = "") -> AgentContext | None:
    return AgentContext.get(context_id) if context_id else AgentContext.current()


def _settings_path(project_name: str = "", agent_profile: str = "") -> str:
    return plugins.determine_plugin_asset_path(
        PLUGIN_NAME,
        project_name,
        agent_profile,
        plugins.CONFIG_FILE_NAME,
    )


def load_scope_settings(
    *,
    scope: MemoryScope,
    project_name: str = "",
    agent_profile: str = "",
) -> dict[str, Any]:
    if scope == "global":
        return _load_json_if_exists(_settings_path())
    if scope == "agent":
        return _load_json_if_exists(_settings_path(agent_profile=agent_profile))
    return _load_json_if_exists(_settings_path(project_name=project_name))


def load_effective_settings(
    *,
    agent: Agent | None = None,
    context: AgentContext | None = None,
    project_name: str | None = None,
    agent_profile: str | None = None,
) -> dict[str, Any]:
    effective = load_default_settings()
    resolved_context = context or (agent.context if agent else None)
    resolved_project_name = (
        project_name
        if project_name is not None
        else (
            projects.get_context_project_name(resolved_context)
            if resolved_context is not None
            else ""
        )
    ) or ""
    resolved_agent_profile = (
        agent_profile
        if agent_profile is not None
        else (agent.config.profile if agent is not None else "")
    ) or ""

    candidate_paths = [_settings_path()]
    if resolved_agent_profile:
        candidate_paths.append(_settings_path(agent_profile=resolved_agent_profile))
    if resolved_project_name:
        candidate_paths.append(_settings_path(project_name=resolved_project_name))
    if resolved_project_name and resolved_agent_profile:
        candidate_paths.append(
            _settings_path(
                project_name=resolved_project_name,
                agent_profile=resolved_agent_profile,
            )
        )

    for path in candidate_paths:
        if files.exists(path):
            effective = _deep_merge_settings(effective, _load_json_if_exists(path))

    return effective


def load_context_settings(context: AgentContext) -> dict[str, Any]:
    return load_effective_settings(
        agent=context.get_agent(),
        context=context,
    )


def load_agent_settings(agent: Agent) -> dict[str, Any]:
    return load_effective_settings(
        agent=agent,
        context=agent.context,
    )


def get_mode_policy(
    settings: dict[str, Any],
    mode: HarnessMode,
) -> dict[str, int]:
    policies = settings.get("mode_policies", {})
    policy = (
        policies.get(normalize_harness_mode(mode), {})
        if isinstance(policies, dict)
        else {}
    )
    return {
        "subagent_limit": int(policy.get("subagent_limit", 0)),
        "repair_limit": int(policy.get("repair_limit", 0)),
    }


def get_default_mode(settings: dict[str, Any]) -> HarnessMode:
    return normalize_harness_mode(settings.get("default_deep_mode", DEFAULT_DEEP_MODE))


def dashboard_settings(settings: dict[str, Any]) -> dict[str, Any]:
    return {
        "show_status_ui": bool(settings.get("show_status_ui", True)),
        "default_deep_mode": get_default_mode(settings),
        "memory_curation_enabled": bool(settings.get("memory_curation_enabled", True)),
    }


def persist_scope_settings(
    *,
    scope: MemoryScope,
    settings: dict[str, Any],
    project_name: str = "",
    agent_profile: str = "",
) -> None:
    if scope == "global":
        plugins.save_plugin_config(PLUGIN_NAME, "", "", settings)
        return
    if scope == "agent":
        plugins.save_plugin_config(PLUGIN_NAME, "", agent_profile, settings)
        return
    plugins.save_plugin_config(PLUGIN_NAME, project_name, "", settings)


def check_config_version(settings: dict[str, Any]) -> bool:
    return int(settings.get("config_version", 0)) >= CURRENT_CONFIG_VERSION


def auto_upgrade_config(settings: dict[str, Any], settings_path: str = "") -> dict[str, Any]:
    if settings_path:
        import shutil
        from pathlib import Path
        path = Path(settings_path)
        if path.exists():
            shutil.copy2(str(path), str(path) + ".bak")

    defaults = load_default_settings()
    upgraded = _deep_merge_settings(defaults, settings)
    upgraded["config_version"] = CURRENT_CONFIG_VERSION
    return upgraded
