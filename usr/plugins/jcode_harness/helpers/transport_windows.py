"""Windows named-pipe transport stub.

v1 ships a marker raising :class:`NotImplementedError`. The full implementation
per spec §8.4 — pywin32 + ACL verification (the daemon writes a SDDL string the
client must validate against ``GetCurrentProcessTokenInformation`` to prevent a
hostile-pipe takeover) — lands in v1.1. Until then we recommend WSL2 for
Windows users; the rest of the harness uses Unix-socket transport unchanged.

Per ``AGENTS.plugins.md``: this module's import path is
``usr.plugins.jcode_harness.helpers.transport_windows``.
"""

from __future__ import annotations

import asyncio


async def open_named_pipe(
    path: str,
) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    """Stub for the Windows named-pipe transport.

    Will, in v1.1, return an ``(asyncio.StreamReader, asyncio.StreamWriter)``
    pair backed by a verified pywin32 named-pipe handle. Today it raises
    :class:`NotImplementedError` everywhere — this is a contract marker, not a
    runtime guard. Callers on POSIX never reach this code path.
    """
    raise NotImplementedError(
        "Windows named-pipe transport not implemented in v1; "
        "use WSL2 or wait for v1.1. Pipe path: " + path
    )
