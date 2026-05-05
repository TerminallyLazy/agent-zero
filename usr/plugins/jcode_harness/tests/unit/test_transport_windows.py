"""Contract tests for the Windows named-pipe transport stub.

Per spec §8.4 the v1 stub raises :class:`NotImplementedError` on every
platform — this is intentional. POSIX callers never invoke it
(``JcodeClient.connect`` branches on ``platform.system()``), and Windows
users are directed to WSL2 until v1.1 ships the pywin32-backed
implementation. These tests pin the stub's contract so v1.1 cannot
silently regress the error surface.
"""

from __future__ import annotations

import pytest

from usr.plugins.jcode_harness.helpers.transport_windows import open_named_pipe


pytestmark = pytest.mark.asyncio


async def test_open_named_pipe_raises_not_implemented():
    with pytest.raises(NotImplementedError) as exc_info:
        await open_named_pipe(r"\\.\pipe\jcode-test")
    msg = str(exc_info.value)
    # Helpful guidance + the offending path are both surfaced so users land
    # on something actionable rather than a bare traceback.
    assert "WSL2" in msg or "v1.1" in msg
    assert r"\\.\pipe\jcode-test" in msg
