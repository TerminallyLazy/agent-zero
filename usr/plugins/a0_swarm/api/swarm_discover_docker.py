from helpers.api import ApiHandler, Request

# Agent Zero runs inside a Docker container, so there is no `docker` CLI on
# PATH. Discovery talks to the Docker daemon through the Python SDK over the
# Docker socket (/var/run/docker.sock). The socket must be mounted into the
# A0 container for this to work; if it is not, we return an actionable error
# instead of a misleading "command not found".

_SOCKET_HINT = (
    "Docker socket not reachable from inside the Agent Zero container. "
    "Mount it (-v /var/run/docker.sock:/var/run/docker.sock) and ensure the "
    "container user can access it, then retry."
)


def _docker_access_setup() -> dict:
    return {
        "title": "Docker Access Setup",
        "summary": (
            "A0 can discover sibling Agent Zero containers after the host Docker "
            "socket is mounted into this container."
        ),
        "mac_steps": [
            "Open Docker Desktop.",
            "Go to Settings > Advanced.",
            "Enable Allow the default Docker socket to be used.",
            "Restart Docker Desktop if prompted, then restart the Agent Zero container.",
        ],
        "compose_snippet": (
            "services:\n"
            "  agent-zero:\n"
            "    volumes:\n"
            "      - /var/run/docker.sock:/var/run/docker.sock\n"
        ),
        "docker_run_flag": "-v /var/run/docker.sock:/var/run/docker.sock",
        "compose_restart": "docker compose down && docker compose up -d",
        "manual_fallback": (
            "If Docker access is not available, add each remote A0 instance "
            "manually with its A2A base URL and auth token."
        ),
    }


def _socket_error_response() -> dict:
    return {
        "ok": False,
        "error": _SOCKET_HINT,
        "setup": _docker_access_setup(),
        "candidates": [],
    }


def _match_a0(image: str, name: str) -> bool:
    hay = f"{image} {name}".lower()
    return "agent-zero" in hay or "agent0" in hay or "a0" in hay


def _guess_base_url(name: str, ports: dict) -> str:
    # Sibling A0 containers on the same Docker network are reachable by
    # container name. If the container exposes A0's default 55000, propose it.
    for container_port in (ports or {}):
        if str(container_port).startswith("55000"):
            return f"http://{name}:55000"
    return ""


class SwarmDiscoverDocker(ApiHandler):
    async def process(self, input: dict, request: Request):
        try:
            import docker  # framework dependency (docker==7.1.0)
            from docker.errors import DockerException
        except ImportError:
            return {
                "ok": False,
                "error": "Docker SDK not available in this Agent Zero build.",
                "candidates": [],
            }

        try:
            client = docker.from_env(timeout=5)
        except DockerException:
            return _socket_error_response()

        try:
            try:
                containers = client.containers.list()
            except DockerException:
                return _socket_error_response()

            candidates = []
            for c in containers:
                name = c.name or ""
                tags = []
                try:
                    tags = list(getattr(c.image, "tags", []) or [])
                except DockerException:
                    tags = []
                image = tags[0] if tags else (c.attrs.get("Config", {}).get("Image") or "")
                if not _match_a0(image, name):
                    continue
                ports = (c.attrs.get("NetworkSettings", {}) or {}).get("Ports", {}) or {}
                ports_text = ", ".join(sorted(p for p in ports if p)) or ""
                candidates.append({
                    "label": name or image,
                    "container": name,
                    "image": image,
                    "ports": ports_text,
                    "base_url": _guess_base_url(name, ports),
                })

            return {"ok": True, "error": "", "candidates": candidates}
        finally:
            try:
                client.close()
            except Exception:
                pass
