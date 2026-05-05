"""Plugin monologue_start extension.

Per spec §5.7 (v1 prompt-routing mode): if the agent is using the
``jcode_coder`` profile, ensure the daemon is hot before the first turn
so ``jcode_session`` calls don't pay the spawn latency. Does NOT
short-circuit A0's loop — true full-takeover is deferred to v2 pending
an upstream ``LoopData.short_circuit`` field.

If creds are missing, this extension silently skips. The first
``jcode_session`` tool call will surface the friendly error.
"""

from __future__ import annotations

import os

from helpers.extension import Extension


class JcodeWarmup(Extension):
    async def execute(self, loop_data=None, **kwargs) -> None:
        agent = self.agent
        if agent is None:
            return
        profile = getattr(getattr(agent, "config", None), "profile", "")
        if profile != "jcode_coder":
            return
        try:
            from usr.plugins.jcode_harness.helpers.daemon import (
                DaemonSupervisor,
                NoCredentialsError,
                locate_jcode_binary,
            )
            from usr.plugins.jcode_harness.helpers.paths import jcode_runtime_dir
        except Exception:
            return
        bin_path = locate_jcode_binary()
        if not bin_path:
            return
        sup = DaemonSupervisor(bin_path, jcode_runtime_dir())
        if sup.is_running():
            return
        try:
            await sup.ensure_running(os.getcwd())
        except NoCredentialsError:
            pass  # silent; first tool call will report
        except Exception:
            pass
