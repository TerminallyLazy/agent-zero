"""Shared subprocess runner for headless CLI commands."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

_ROOT_DIR = Path(__file__).resolve().parents[4]
_MODULE = "usr.plugins.headless_mode.cli"
_MAX_STDERR = 2000


async def run_cli_subprocess(
    args: list[str],
    timeout: int = 60,
) -> tuple[bool, str, str]:
    """Run the headless CLI as a subprocess.

    Returns (ok, stdout, stderr).
    """
    cmd = [sys.executable, "-m", _MODULE, *args]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(_ROOT_DIR),
    )
    try:
        raw_out, raw_err = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return False, "", f"Timed out after {timeout}s"

    stdout = raw_out.decode("utf-8", errors="replace") if raw_out else ""
    stderr = raw_err.decode("utf-8", errors="replace") if raw_err else ""
    if len(stderr) > _MAX_STDERR:
        stderr = stderr[:_MAX_STDERR] + "...(truncated)"

    return proc.returncode == 0, stdout, stderr
