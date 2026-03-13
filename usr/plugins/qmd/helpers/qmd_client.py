"""
QMDClient — Python async client that manages the Node.js bridge subprocess.

Protocol:
  stdin:  {"jsonrpc":"2.0","id":N,"method":"...","params":{...}}\n
  stdout: {"jsonrpc":"2.0","id":N,"result":{...}}\n  (or "error")

Startup:
  1. Spawns bridge.js as a subprocess.
  2. Waits for {"ready":true} line on stdout (30s timeout).
  3. Serialises all requests through an asyncio.Lock.

Auto-respawn:
  If the subprocess has died when call() is entered, it is restarted
  transparently before the request is sent.

Gating:
  Methods that mutate the store are "gated".  The caller must pass
  gated=True AND management_enabled=True; otherwise an error dict is
  returned immediately without touching the bridge.
"""

import asyncio
import json
import os
from pathlib import Path

TIMEOUT_SEARCH = 120  # query, search, vsearch, embed — GGUF model loading can be slow
TIMEOUT_DEFAULT = 10  # get, status, ping, management, etc.
_LONG_METHODS = {"query", "search", "vsearch", "embed"}
_STREAM_LIMIT = 16 * 1024 * 1024  # 16 MB — bridge responses can be large JSON lines

BRIDGE_JS = Path(__file__).parent.parent / "bridge" / "bridge.js"


class QMDClient:
    def __init__(self):
        self._proc = None
        self._lock = asyncio.Lock()
        self._id = 0
        self._db_path: str | None = None

    async def start(self, db_path: str = None) -> None:
        """Spawn bridge.js subprocess and wait for {"ready":true}."""
        self._db_path = db_path
        env = os.environ.copy()
        if db_path:
            env["QMD_DB_PATH"] = db_path
        self._proc = await asyncio.create_subprocess_exec(
            "node", str(BRIDGE_JS),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            limit=_STREAM_LIMIT,
        )
        # Wait for {"ready":true} line with 30s timeout
        try:
            line = await asyncio.wait_for(self._proc.stdout.readline(), timeout=30)
        except asyncio.TimeoutError:
            raise RuntimeError("QMD not installed. Run plugin initialization.")
        data = json.loads(line)
        if not data.get("ready"):
            raise RuntimeError(f"Bridge startup failed: {data}")

    async def stop(self) -> None:
        """Gracefully stop the bridge subprocess."""
        if self._proc and self._proc.returncode is None:
            self._proc.stdin.close()
            try:
                await asyncio.wait_for(self._proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                self._proc.kill()
        self._proc = None

    async def call(
        self,
        method: str,
        params: dict = None,
        gated: bool = False,
        management_enabled: bool = False,
    ) -> dict:
        """Send a JSON-RPC request and return the result dict.

        Args:
            method: Bridge method name (e.g. "ping", "query", "collection_add").
            params: Optional parameters dict forwarded as-is.
            gated: Set True for management methods that mutate the store.
            management_enabled: Plugin setting that unlocks gated methods.

        Returns:
            Result dict on success, or {"error": "..."} on failure/blocked.

        Raises:
            RuntimeError: If the bridge times out on a request.
        """
        if gated and not management_enabled:
            return {
                "error": (
                    "Management operations are disabled. "
                    "Enable in plugin settings."
                )
            }

        # Auto-respawn if subprocess died
        if not self.is_running():
            await self.start(self._db_path)

        async with self._lock:
            self._id += 1
            req = {
                "jsonrpc": "2.0",
                "id": self._id,
                "method": method,
                "params": params or {},
            }
            self._proc.stdin.write((json.dumps(req) + "\n").encode())
            await self._proc.stdin.drain()

            timeout = TIMEOUT_SEARCH if method in _LONG_METHODS else TIMEOUT_DEFAULT
            try:
                line = await asyncio.wait_for(
                    self._proc.stdout.readline(), timeout=timeout
                )
            except asyncio.TimeoutError:
                raise RuntimeError(f"QMD bridge timeout on method '{method}'")

            if not line:
                self._proc = None  # reset so next call auto-respawns
                raise RuntimeError(
                    "QMD bridge process exited unexpectedly. "
                    "This can happen on first search while GGUF models load (~3 GB). "
                    "Try again — the bridge will restart automatically."
                )

            resp = json.loads(line)
            if "error" in resp:
                return {"error": resp["error"]["message"]}
            return resp.get("result", {})

    def is_running(self) -> bool:
        """Return True if the bridge subprocess is alive."""
        return self._proc is not None and self._proc.returncode is None
