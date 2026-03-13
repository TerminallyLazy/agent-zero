# usr/plugins/qmd/helpers/client_access.py
"""Helpers to get or create the QMDClient for a given agent session."""
from __future__ import annotations

from helpers import plugins
from usr.plugins.qmd.helpers.qmd_client import QMDClient

# Module-level singleton so the config UI can check bridge status without a
# live agent ctxid.  Per-agent callers use this same instance.
_global_client: QMDClient | None = None


def get_global_client() -> QMDClient | None:
    """Return the global QMDClient if one has been created, or None."""
    return _global_client


async def get_or_create_client(agent) -> QMDClient:
    """Return the running QMDClient for this agent session, starting it if needed."""
    global _global_client
    client = agent.get_data("qmd_client")
    if client is None or not client.is_running():
        config = plugins.get_plugin_config("qmd", agent=agent) or {}
        db_path = config.get("db_path") or None
        client = QMDClient()
        await client.start(db_path=db_path)
        agent.set_data("qmd_client", client)
        _global_client = client
    return client


async def get_or_create_global_client(db_path: str | None = None) -> QMDClient:
    """Start (or reuse) the global bridge client, independent of any agent."""
    global _global_client
    if _global_client is None or not _global_client.is_running():
        _global_client = QMDClient()
        await _global_client.start(db_path=db_path)
    return _global_client


def is_management_enabled(agent) -> bool:
    """Return True if management operations are enabled in plugin config."""
    config = plugins.get_plugin_config("qmd", agent=agent) or {}
    return bool(config.get("management_enabled", False))
