from python.helpers.api import ApiHandler, Request, Response

import asyncio
import json
from pathlib import Path

_plugin_root = Path(__file__).parent.parent
_compose_file = _plugin_root / "docker-compose.context-engine.yaml"


class DockerHandler(ApiHandler):
    """Docker Compose lifecycle handler for the Context Engine stack."""

    async def process(self, input: dict, request: Request) -> dict | Response:
        action = input.get("action", "").strip().lower()

        if action not in ("up", "down", "ps"):
            return {
                "ok": False,
                "error": "Invalid action. Use 'up', 'down', or 'ps'.",
            }

        if not _compose_file.is_file():
            return {
                "ok": False,
                "error": f"Compose file not found: {_compose_file}",
            }

        if action == "up":
            return await self._up()
        elif action == "down":
            return await self._down()
        else:
            return await self._ps()

    async def _up(self) -> dict:
        return await self._run_compose(
            ["docker", "compose", "-f", str(_compose_file), "up", "-d"],
            timeout=120,
        )

    async def _down(self) -> dict:
        return await self._run_compose(
            ["docker", "compose", "-f", str(_compose_file), "down"],
            timeout=30,
        )

    async def _ps(self) -> dict:
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "compose", "-f", str(_compose_file), "ps", "--format", "json",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        except FileNotFoundError:
            return {"ok": False, "error": "Docker is not installed or not in PATH."}
        except asyncio.TimeoutError:
            return {
                "ok": False,
                "error": "Timed out checking services. Try running 'docker compose ps' manually.",
            }

        if proc.returncode != 0:
            return {
                "ok": False,
                "error": stderr.decode().strip() or "docker compose ps failed",
            }

        services = []
        for line in stdout.decode().strip().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                services.append(json.loads(line))
            except json.JSONDecodeError:
                continue

        running_count = sum(
            1 for s in services if s.get("State") == "running"
        )

        return {
            "ok": True,
            "running": running_count > 0 and running_count == len(services),
            "services": services,
            "service_count": len(services),
            "running_count": running_count,
        }

    async def _run_compose(self, cmd: list[str], timeout: int) -> dict:
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except FileNotFoundError:
            return {"ok": False, "error": "Docker is not installed or not in PATH."}
        except asyncio.TimeoutError:
            return {
                "ok": False,
                "error": f"Command timed out after {timeout}s. Try pulling images manually with 'docker compose pull'.",
            }

        output = stdout.decode().strip()
        err_output = stderr.decode().strip()
        # docker compose writes progress to stderr even on success,
        # so combine both streams for the output field.
        combined = "\n".join(filter(None, [output, err_output]))

        if proc.returncode != 0:
            return {
                "ok": False,
                "error": err_output or "Command failed",
                "output": combined,
            }

        return {"ok": True, "output": combined}
