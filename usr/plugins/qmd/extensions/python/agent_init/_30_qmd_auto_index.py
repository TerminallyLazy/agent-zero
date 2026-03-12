# usr/plugins/qmd/extensions/python/agent_init/_30_qmd_auto_index.py
"""Auto-index the current project directory on first agent init.

NOTE: agent_init extensions are called synchronously during Agent.__init__.
All async bridge work is dispatched via DeferredTask using an isolated
QMDClient that is created and destroyed within the task's own event loop.
"""
from __future__ import annotations

import os
from helpers.extension import Extension
from helpers import plugins
from helpers.defer import DeferredTask


PLUGIN_NAME = "qmd"
AUTO_INDEXED_KEY = "qmd_auto_indexed"


class QMDAutoIndex(Extension):

    def execute(self, **kwargs):  # sync — agent_init hook is synchronous
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
            # Auto-index requires management access to be enabled
            return

        cwd = self.agent.get_data("cwd") or os.getcwd()
        project_name = os.path.basename(cwd.rstrip("/\\"))
        db_path = config.get("db_path") or None

        async def do_auto_index():
            """Runs in DeferredTask's isolated event loop with its own client."""
            from usr.plugins.qmd.helpers.qmd_client import QMDClient
            client = QMDClient()
            try:
                await client.start(db_path=db_path)
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
                    # Embed inline — we're already in a background task
                    await client.call(
                        "embed",
                        {"_management_enabled": True},
                        gated=True,
                        management_enabled=True,
                    )
            except Exception:
                # Auto-index is best-effort — never propagate errors
                pass
            finally:
                await client.stop()

        DeferredTask().start_task(do_auto_index)
        self.agent.set_data(AUTO_INDEXED_KEY, True)
