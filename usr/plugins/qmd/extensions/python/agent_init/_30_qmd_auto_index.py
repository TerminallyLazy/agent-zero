# usr/plugins/qmd/extensions/python/agent_init/_30_qmd_auto_index.py
"""Auto-index the current project directory on first agent init."""
from __future__ import annotations

import os
from helpers.extension import Extension
from helpers import plugins
from helpers.defer import DeferredTask


PLUGIN_NAME = "qmd"
AUTO_INDEXED_KEY = "qmd_auto_indexed"


class QMDAutoIndex(Extension):

    async def execute(self, **kwargs):
        if not self.agent:
            return

        # Root agent only — sub-agents do not auto-index
        if self.agent.number != 0:
            return

        # Run only once per agent context
        if self.agent.get_data(AUTO_INDEXED_KEY):
            return

        # Check config
        config = plugins.get_plugin_config(PLUGIN_NAME, agent=self.agent) or {}
        if not config.get("auto_index_project", True):
            return
        if not config.get("management_enabled", False):
            # Auto-index requires management access
            return

        cwd = self.agent.get_data("cwd") or os.getcwd()
        project_name = os.path.basename(cwd.rstrip("/\\"))

        try:
            from usr.plugins.qmd.helpers.client_access import get_or_create_client
            client = await get_or_create_client(self.agent)

            # Check if a collection for this path already exists
            result = await client.call("collection_list")
            collections = result.get("collections", [])
            existing_paths = {c.get("pwd", "") for c in collections}

            if cwd not in existing_paths:
                await client.call(
                    "collection_add",
                    {"path": cwd, "name": project_name, "_management_enabled": True},
                    gated=True,
                    management_enabled=True,
                )

                # Fire embed in background — don't block agent startup
                async def run_embed():
                    await client.call("embed", {"_management_enabled": True}, gated=True, management_enabled=True)

                DeferredTask().start_task(run_embed)  # IMPORTANT: pass callable, NOT run_embed()

        except Exception:
            # Auto-index is best-effort — never fail agent init
            pass

        self.agent.set_data(AUTO_INDEXED_KEY, True)
