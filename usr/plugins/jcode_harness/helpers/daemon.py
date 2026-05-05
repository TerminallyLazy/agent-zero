"""DaemonSupervisor — manage a per-A0 jcode child process.

Spec ref: §4.1, §5.3, §6.1, §8.4.

Spike 0.6 findings (jcode v0.11.10) baked in:
- ``jcode serve`` has NO ``--owner-pid`` flag — do not pass it.
- ``jcode serve`` refuses to start without at least one configured provider —
  pre-spawn ``_has_creds()`` gate is required so we surface a friendly error.
- The internal "gateway" listener is disabled by passing
  ``JCODE_CONFIG=<overlay>`` env var pointing at a TOML file with
  ``[gateway]\\nenabled = false``.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import signal
import subprocess
import time
from pathlib import Path


class NoCredentialsError(RuntimeError):
    """Raised when jcode daemon cannot start — no providers configured."""


def locate_jcode_binary() -> str | None:
    """Find a jcode binary: PATH first, then ``~/.jcode/builds/stable/jcode``.

    Bundled here for Task 4.4 — single source of truth for binary discovery.
    """
    p = shutil.which("jcode")
    if p:
        return p
    stable = Path.home() / ".jcode" / "builds" / "stable" / "jcode"
    if stable.exists() and os.access(stable, os.X_OK):
        return str(stable)
    return None


class DaemonSupervisor:
    """Lifecycle manager for one jcode child per A0 instance.

    Responsibilities:
      - Spawn ``jcode serve`` with a per-instance unix socket.
      - Track pid/socket files, archive stale pids on restart.
      - Pre-flight credential check (``_has_creds``) — jcode refuses to
        start without at least one provider configured.
      - Disable the jcode gateway via overlay TOML config.
      - Clean shutdown via SIGTERM with a SIGKILL fallback.
      - ``health()`` introspection for the WebUI badge / API surface.
    """

    def __init__(self, jcode_binary: str, instance_dir: Path):
        self.jcode_binary = jcode_binary
        self.instance_dir = Path(instance_dir)
        self.pid_file = self.instance_dir / "pid"
        self.socket_file = self.instance_dir / "socket"
        self.overlay_config = self.instance_dir / "jcode-config.toml"
        self.log_dir = self.instance_dir / "logs"
        self.instance_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.log_dir.mkdir(parents=True, exist_ok=True, mode=0o700)

    # ------------------------------------------------------------------
    # state predicates
    # ------------------------------------------------------------------

    def is_running(self) -> bool:
        if not self.pid_file.exists() or not self.socket_file.exists():
            return False
        try:
            pid = int(self.pid_file.read_text().strip())
            os.kill(pid, 0)
            return self._socket_perms_ok()
        except (ValueError, ProcessLookupError, PermissionError):
            return False

    def _socket_perms_ok(self) -> bool:
        try:
            st = self.socket_file.stat()
        except FileNotFoundError:
            return False
        return (st.st_mode & 0o777) == 0o600 and st.st_uid == os.getuid()

    def _has_creds(self) -> bool:
        """Pre-spawn credential check.

        Spike 0.6: jcode serve refuses to start without any configured
        provider. We accept any of:
          - On-disk auth files under ``~/.jcode/``.
          - One of the well-known provider env vars set.
          - ``jcode provider list --json`` returning a non-empty array.
        """
        auth_files = [
            Path.home() / ".jcode" / "auth.json",
            Path.home() / ".jcode" / "openai-auth.json",
            Path.home() / ".jcode" / "gemini_oauth.json",
            Path.home() / ".jcode" / "antigravity_oauth.json",
        ]
        if any(f.exists() for f in auth_files):
            return True
        for env_name in (
            "ANTHROPIC_API_KEY",
            "OPENAI_API_KEY",
            "GEMINI_API_KEY",
            "OPENROUTER_API_KEY",
            "AZURE_OPENAI_API_KEY",
        ):
            if env_name in os.environ:
                return True
        try:
            result = subprocess.run(
                [self.jcode_binary, "provider", "list", "--json"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode != 0:
                return False
            return bool(json.loads(result.stdout or "[]"))
        except Exception:
            return False

    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------

    async def ensure_running(self, working_dir: str) -> str:
        """Idempotently ensure a jcode daemon is up; return socket path."""
        if self.is_running():
            return str(self.socket_file)
        if not self._has_creds():
            raise NoCredentialsError(
                "jcode harness needs at least one configured provider. "
                "Open plugin settings → Login, or set an API key env var."
            )
        # Archive stale pid file rather than overwrite — keeps audit trail.
        if self.pid_file.exists():
            ts = int(time.time())
            try:
                self.pid_file.rename(
                    self.instance_dir / f"pid.dead.{ts}"
                )
            except OSError:
                self.pid_file.unlink(missing_ok=True)
        # Stale socket file from a dead daemon would block bind() — clear it.
        if self.socket_file.exists():
            try:
                self.socket_file.unlink()
            except OSError:
                pass

        # Overlay config: disable gateway listener (Spike 0.6).
        self.overlay_config.write_text("[gateway]\nenabled = false\n")
        self.overlay_config.chmod(0o600)

        env = dict(os.environ, JCODE_CONFIG=str(self.overlay_config))
        log_file = self.log_dir / f"jcode-{int(time.time())}.log"
        # NOTE: --owner-pid does NOT exist on jcode v0.11.10 `serve`.
        log_fp = open(log_file, "ab")  # closed by Popen lifecycle
        try:
            proc = subprocess.Popen(
                [
                    self.jcode_binary,
                    "--socket",
                    str(self.socket_file),
                    "serve",
                ],
                env=env,
                stdout=log_fp,
                stderr=subprocess.STDOUT,
                cwd=working_dir,
                start_new_session=True,
            )
        except Exception:
            log_fp.close()
            raise

        self.pid_file.write_text(str(proc.pid))
        self.pid_file.chmod(0o600)

        # Wait up to 5 s for the socket to appear with the right perms.
        for _ in range(50):
            if self.socket_file.exists() and self._socket_perms_ok():
                return str(self.socket_file)
            # Did the child die early?
            if proc.poll() is not None:
                raise RuntimeError(
                    f"jcode daemon exited early (code={proc.returncode}); "
                    f"see {log_file}"
                )
            await asyncio.sleep(0.1)
        raise RuntimeError(
            f"jcode daemon did not become ready in 5s; see {log_file}"
        )

    def stop(self, timeout: float = 5.0) -> None:
        """Best-effort graceful shutdown; SIGKILL on timeout."""
        if not self.pid_file.exists():
            self.socket_file.unlink(missing_ok=True)
            return
        pid: int | None = None
        try:
            pid = int(self.pid_file.read_text().strip())
        except (ValueError, OSError):
            pid = None

        if pid is not None:
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            except PermissionError:
                pass
            else:
                deadline = time.time() + timeout
                killed = False
                while time.time() < deadline:
                    try:
                        os.kill(pid, 0)
                    except ProcessLookupError:
                        killed = True
                        break
                    time.sleep(0.05)
                if not killed:
                    try:
                        os.kill(pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass

        self.pid_file.unlink(missing_ok=True)
        self.socket_file.unlink(missing_ok=True)

    async def restart(self, working_dir: str) -> str:
        self.stop()
        return await self.ensure_running(working_dir)

    # ------------------------------------------------------------------
    # introspection
    # ------------------------------------------------------------------

    def health(self) -> dict:
        """Return a JSON-serializable health snapshot for UI/API surfaces.

        Bundled here for Task 4.5 — keeps state inspection co-located with
        the writer so we cannot drift.
        """
        running = self.is_running()
        pid: int | None = None
        started_at: float | None = None
        if self.pid_file.exists():
            try:
                started_at = self.pid_file.stat().st_mtime
            except OSError:
                started_at = None
            try:
                pid = int(self.pid_file.read_text().strip())
            except (ValueError, OSError):
                pid = None
        log_files = sorted(self.log_dir.glob("*.log"))
        return {
            "running": running,
            "pid": pid,
            "started_at": started_at,
            "uptime_s": (time.time() - started_at) if started_at else None,
            "socket": str(self.socket_file),
            "last_log": str(log_files[-1]) if log_files else None,
        }
