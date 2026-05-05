"""Plugin agent_init extension.

Registers nothing explicitly — A0 auto-discovers tools from the plugin's
``tools/`` directory. This extension exists as a hook point for future v2
work (e.g., deferring tool list based on settings) and to optionally
pre-warm the jcode daemon when the user has selected the ``jcode_coder``
profile.

Daemon spawn is best-effort and gated on credentials presence. Spike 0.6
confirmed ``jcode serve`` refuses to start without a configured provider,
so we defer the actual spawn to the first tool invocation if creds aren't
ready yet.
"""

from __future__ import annotations

import asyncio
import os

from helpers.extension import Extension


class JcodeRegister(Extension):
    # NOTE: execute() must be SYNC. A0 calls this hook via
    # `helpers.extension.call_extensions_sync("agent_init", ...)` from
    # `agent.py:370`, which raises ValueError("Extension ... returned
    # awaitable in sync mode") if execute returns an awaitable. The actual
    # daemon-warmup work is dispatched as a fire-and-forget task below
    # (see `loop.create_task(_warm())`), so the sync function returns
    # immediately while the warmup runs in the background event loop.
    def execute(self, **kwargs) -> None:
        agent = self.agent
        if agent is None:
            return
        profile = getattr(getattr(agent, "config", None), "profile", "")
        if profile != "jcode_coder":
            return  # only pre-warm for the dedicated profile
        try:
            from usr.plugins.jcode_harness.helpers.daemon import (
                DaemonSupervisor,
                NoCredentialsError,
                locate_jcode_binary,
            )
            from usr.plugins.jcode_harness.helpers.paths import jcode_runtime_dir
        except Exception:
            return  # plugin helpers unavailable — silent no-op
        bin_path = locate_jcode_binary()
        if not bin_path:
            return
        sup = DaemonSupervisor(bin_path, jcode_runtime_dir())
        if sup.is_running():
            return

        # Don't block agent_init on daemon spawn; fire-and-forget background task
        async def _warm() -> None:
            try:
                await sup.ensure_running(os.getcwd())
            except NoCredentialsError:
                pass  # silent — first tool invocation will surface the error
            except Exception:
                pass

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_warm())
        except RuntimeError:
            pass  # no event loop running; skip
