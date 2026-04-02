from __future__ import annotations

from typing import Any

from agent import Agent, AgentContext
from helpers import persist_chat, plugins, projects, skills as host_skills

from usr.plugins.agent_harness.helpers import lifecycle
from usr.plugins.agent_harness.helpers.workspace import (
    cleanup_thread_data,
    ensure_gitignore,
    ensure_workspace,
    list_artifacts,
    list_uploads,
)


def ensure_context_workspace(context: AgentContext):
    run = lifecycle.get_current_run(context)
    if run and run.workspace and run.workspace.thread_root and run.workspace.uploads:
        return run.workspace

    project_name = projects.get_context_project_name(context) or ""
    project_dir = projects.get_project_folder(project_name) if project_name else ""
    base_dir = project_dir or persist_chat.get_chat_folder_path(context.id)
    paths = ensure_workspace(base_dir, context_id=context.id)
    if project_dir:
        ensure_gitignore(project_dir)

    if run:
        run.workspace = paths
        lifecycle.save_current_run(context, run)
    return paths


def summarize_thread_paths(paths) -> dict[str, Any]:
    uploads = list_uploads(paths)
    artifacts = list_artifacts(paths)
    return {
        "root": paths.root,
        "thread_root": paths.thread_root,
        "user_data": paths.user_data,
        "workspace": paths.workspace,
        "uploads": paths.uploads,
        "outputs": paths.outputs,
        "runs": paths.runs,
        "upload_count": len(uploads),
        "artifact_count": len(artifacts),
    }


def list_configured_models(agent: Agent | None) -> list[dict[str, Any]]:
    from plugins._model_config.helpers import model_config

    configured: list[tuple[str, dict[str, Any]]] = [
        ("chat", model_config.get_chat_model_config(agent)),
        ("utility", model_config.get_utility_model_config(agent)),
        ("embedding", model_config.get_embedding_model_config(agent)),
    ]
    result: list[dict[str, Any]] = []
    for kind, cfg in configured:
        provider = str(cfg.get("provider", "")).strip()
        name = str(cfg.get("name", "")).strip()
        if not provider and not name:
            continue
        result.append(
            {
                "kind": kind,
                "provider": provider,
                "name": name,
                "display_name": f"{provider}/{name}".strip("/"),
                "ctx_length": int(cfg.get("ctx_length", 0) or 0),
                "vision": bool(cfg.get("vision", False)),
            }
        )
    return result


def list_skill_entries(agent: Agent | None, limit: int = 50) -> list[dict[str, Any]]:
    entries = []
    for skill in host_skills.list_skills(agent):
        entries.append(
            {
                "name": skill.name,
                "description": skill.description,
                "path": str(skill.path),
            }
        )
    entries.sort(key=lambda item: (item["name"], item["path"]))
    return entries[: max(limit, 0)]


async def get_memory_status(context: AgentContext) -> dict[str, Any]:
    agent = context.get_agent()
    enabled_plugins = plugins.get_enabled_plugins(agent)
    if "_memory" not in enabled_plugins:
        return {
            "enabled": False,
            "current_subdir": "",
            "available_subdirs": [],
            "storage_path": "",
        }

    from plugins._memory.helpers.memory import (
        get_context_memory_subdir,
        get_existing_memory_subdirs,
        get_memory_subdir_abs,
    )

    current_subdir = get_context_memory_subdir(context) or "default"
    return {
        "enabled": True,
        "current_subdir": current_subdir,
        "available_subdirs": sorted(get_existing_memory_subdirs()),
        "storage_path": get_memory_subdir_abs(agent) if agent else "",
    }


async def build_core_state(
    context: AgentContext,
    *,
    skills_limit: int = 50,
) -> dict[str, Any]:
    agent = context.get_agent()
    paths = ensure_context_workspace(context)
    return {
        "thread": summarize_thread_paths(paths),
        "models": list_configured_models(agent),
        "skills": list_skill_entries(agent, limit=skills_limit),
        "memory": await get_memory_status(context),
    }


def clear_thread_workspace(context: AgentContext) -> dict[str, Any]:
    paths = ensure_context_workspace(context)
    cleanup_thread_data(paths)
    run = lifecycle.get_current_run(context)
    if run and run.workspace and run.workspace.thread_root == paths.thread_root:
        run.workspace = None
        lifecycle.save_current_run(context, run)
    return summarize_thread_paths(paths)
