from __future__ import annotations

from agent import AgentContext

from usr.plugins.agent_harness.helpers.deerflow_core import (
    build_core_state,
    clear_thread_workspace,
    ensure_context_workspace,
    get_memory_status,
    list_configured_models,
    list_skill_entries,
    summarize_thread_paths,
)
from usr.plugins.agent_harness.helpers.workspace import (
    delete_upload,
    list_artifacts,
    list_uploads,
    resolve_artifact,
    save_upload,
)


class DeerFlowClient:
    def __init__(self, context: AgentContext):
        self.context = context

    def thread_paths(self):
        return ensure_context_workspace(self.context)

    def thread_status(self):
        return summarize_thread_paths(self.thread_paths())

    async def core_state(self, *, skills_limit: int = 50):
        return await build_core_state(self.context, skills_limit=skills_limit)

    def list_models(self):
        return list_configured_models(self.context.get_agent())

    def list_skills(self, *, limit: int = 50):
        return list_skill_entries(self.context.get_agent(), limit=limit)

    async def memory_status(self):
        return await get_memory_status(self.context)

    def list_thread_uploads(self):
        return list_uploads(self.thread_paths())

    def save_thread_upload(self, filename: str, content: bytes):
        return save_upload(self.thread_paths(), filename, content)

    def delete_thread_upload(self, relative_path: str):
        return delete_upload(self.thread_paths(), relative_path)

    def list_thread_artifacts(self):
        return list_artifacts(self.thread_paths())

    def resolve_thread_artifact(self, relative_path: str):
        return resolve_artifact(self.thread_paths(), relative_path)

    def cleanup_thread(self):
        return clear_thread_workspace(self.context)
