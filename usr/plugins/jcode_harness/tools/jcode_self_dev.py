"""jcode_self_dev: trigger jcode self-modification. Gated on Rust toolchain.

Per AGENTS.plugins.md non-tech-user rule, the plugin never auto-installs
Rust. If ``cargo`` is missing on PATH at invocation time, return a clean
error pointing the user at https://rustup.rs.

Spec ref: §4.3 "Self-development gate".
"""

from __future__ import annotations

import shutil

from helpers.tool import Tool, Response

from usr.plugins.jcode_harness.tools.jcode_session import JcodeSession


_RUSTUP_HINT = (
    "Self-dev requires the Rust toolchain. "
    "Install from https://rustup.rs and re-enable in plugin settings."
)


class JcodeSelfDev(Tool):
    """Run a jcode self-dev task; require Rust to be present."""

    async def execute(self, task: str = "", **_kwargs) -> Response:
        if not shutil.which("cargo"):
            return Response(message=_RUSTUP_HINT, break_loop=False)
        if not task.strip():
            return Response(
                message="task description required",
                break_loop=False,
            )
        # Reuse this tool instance's runtime state without re-running
        # ``Tool.__init__`` (which expects the full A0 runtime). Mirrors the
        # ``make_tool`` helper used in unit tests.
        sess = JcodeSession.__new__(JcodeSession)
        sess.agent = self.agent
        sess.loop_data = getattr(self, "loop_data", None)
        sess.name = "jcode_session"
        sess.method = None
        sess.args = {}
        sess.message = ""
        sess.progress = ""
        return await sess.execute(task=f"Enter selfdev mode and: {task}")
