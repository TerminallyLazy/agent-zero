# usr/plugins/qmd/helpers/client_access.py
"""Helpers to get or create the QMDClient for a given agent session."""
from __future__ import annotations

from helpers import plugins
from usr.plugins.qmd.helpers.qmd_client import QMDClient


async def get_or_create_client(agent) -> QMDClient:
    """Return the running QMDClient for this agent session, starting it if needed."""
    client = agent.get_data("qmd_client")
    if client is None or not client.is_running():
        config = plugins.get_plugin_config("qmd", agent=agent) or {}
        db_path = config.get("db_path") or None
        client = QMDClient()
        await client.start(db_path=db_path)
        agent.set_data("qmd_client", client)
    return client


def is_management_enabled(agent) -> bool:
    """Return True if management operations are enabled in plugin config."""
    config = plugins.get_plugin_config("qmd", agent=agent) or {}
    return bool(config.get("management_enabled", False))
