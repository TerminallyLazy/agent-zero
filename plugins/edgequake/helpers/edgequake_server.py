"""
EdgeQuake server lifecycle helpers.

Provides API key generation, health-based status checks (HTTP), and Docker
management when available. Since Agent Zero typically runs inside a Docker
container WITHOUT access to the host Docker daemon, server status is always
checked via the HTTP /health endpoint. Docker start/stop is offered only when
the Docker SDK is importable and the daemon is reachable.
"""

import os
import uuid
from typing import Any

import requests

from python.helpers.files import get_abs_path
from python.helpers.print_style import PrintStyle

# Docker resource names (used when Docker is available)
NETWORK_NAME = "edgequake-net"
POSTGRES_CONTAINER = "edgequake-postgres"
POSTGRES_VOLUME = "edgequake-pgdata"
EDGEQUAKE_CONTAINER = "edgequake"
EDGEQUAKE_IMAGE = "edgequake:latest"
POSTGRES_TAG = "edgequake-postgres:latest"

DOCKER_DIR = get_abs_path("plugins/edgequake/docker")


def generate_api_key() -> str:
    """Generate a random API key (32-char hex string)."""
    return uuid.uuid4().hex


# ---------------------------------------------------------------------------
# Docker availability
# ---------------------------------------------------------------------------

def _get_docker_client():
    """Get a Docker client. Returns None if Docker SDK or daemon is unavailable."""
    try:
        import docker
        client = docker.from_env()
        client.ping()
        return client
    except Exception:
        return None


def is_docker_available() -> bool:
    """Check whether the Docker daemon is reachable."""
    return _get_docker_client() is not None


# ---------------------------------------------------------------------------
# HTTP-based health check (always works, no Docker needed)
# ---------------------------------------------------------------------------

def _check_health(base_url: str, api_key: str = "", timeout: int = 5) -> dict[str, Any] | None:
    """
    Ping the EdgeQuake /health endpoint.

    Returns the parsed JSON on success, or None on failure.
    """
    base_url = base_url.rstrip("/")
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        resp = requests.get(f"{base_url}/health", headers=headers, timeout=timeout)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Server status (HTTP-based, always available)
# ---------------------------------------------------------------------------

def server_status() -> dict[str, Any]:
    """
    Check EdgeQuake server status by pinging the /health endpoint.

    This works regardless of Docker availability — if the server is reachable
    over HTTP, it's running.
    """
    from plugins.edgequake.helpers.edgequake_client import get_edgequake_settings

    settings = get_edgequake_settings()
    base_url = settings.get("base_url", "http://host.docker.internal:8080")
    api_key = settings.get("api_key", "")

    health = _check_health(base_url, api_key)
    docker_ok = is_docker_available()

    return {
        "docker_available": docker_ok,
        "running": health is not None,
        "health": health,
    }


# ---------------------------------------------------------------------------
# Docker start/stop (only when Docker SDK is available)
# ---------------------------------------------------------------------------

def _ensure_network(client) -> None:
    """Create the EdgeQuake bridge network if it doesn't exist."""
    try:
        client.networks.get(NETWORK_NAME)
    except Exception:
        client.networks.create(NETWORK_NAME, driver="bridge")


def _ensure_volume(client) -> None:
    """Create the PostgreSQL data volume if it doesn't exist."""
    try:
        client.volumes.get(POSTGRES_VOLUME)
    except Exception:
        client.volumes.create(POSTGRES_VOLUME)


def _get_container(client, name: str):
    """Get a container by name, or None if it doesn't exist."""
    try:
        return client.containers.get(name)
    except Exception:
        return None


def _remove_container(client, name: str) -> None:
    """Stop and remove a container if it exists."""
    container = _get_container(client, name)
    if container:
        try:
            container.stop(timeout=10)
        except Exception:
            pass
        try:
            container.remove(force=True)
        except Exception:
            pass


def start_server(settings: dict[str, Any]) -> dict[str, Any]:
    """
    Start the EdgeQuake Docker stack.

    Requires the Docker SDK and a reachable daemon.
    """
    import time

    client = _get_docker_client()
    if client is None:
        return {"error": "Docker is not available from this environment."}

    api_key = settings.get("api_key", "").strip()
    if not api_key:
        return {"error": "API key is required. Generate one first."}

    # Build EdgeQuake image if needed
    try:
        client.images.get(EDGEQUAKE_IMAGE)
    except Exception:
        dockerfile = os.path.join(DOCKER_DIR, "Dockerfile.edgequake")
        if not os.path.exists(dockerfile):
            return {"error": f"Dockerfile not found: {dockerfile}"}
        try:
            PrintStyle.standard("EdgeQuake: Building server image (this may take 10-30 min)...")
            client.images.build(path=DOCKER_DIR, dockerfile="Dockerfile.edgequake", tag=EDGEQUAKE_IMAGE, rm=True)
        except Exception as e:
            return {"error": f"Failed to build EdgeQuake image: {e}"}

    # Build PostgreSQL image if needed
    try:
        client.images.get(POSTGRES_TAG)
    except Exception:
        dockerfile = os.path.join(DOCKER_DIR, "Dockerfile.postgres")
        if not os.path.exists(dockerfile):
            return {"error": f"Dockerfile not found: {dockerfile}"}
        try:
            PrintStyle.standard("EdgeQuake: Building PostgreSQL image...")
            client.images.build(path=DOCKER_DIR, dockerfile="Dockerfile.postgres", tag=POSTGRES_TAG, rm=True)
        except Exception as e:
            return {"error": f"Failed to build PostgreSQL image: {e}"}

    _ensure_network(client)
    _ensure_volume(client)

    db_password = settings.get("db_password", "edgequake")
    port = int(settings.get("port", 8080))

    # Start PostgreSQL
    pg = _get_container(client, POSTGRES_CONTAINER)
    if not (pg and pg.status == "running"):
        _remove_container(client, POSTGRES_CONTAINER)
        try:
            client.containers.run(
                POSTGRES_TAG,
                detach=True,
                name=POSTGRES_CONTAINER,
                network=NETWORK_NAME,
                environment={
                    "POSTGRES_USER": "edgequake",
                    "POSTGRES_PASSWORD": db_password,
                    "POSTGRES_DB": "edgequake",
                },
                volumes={POSTGRES_VOLUME: {"bind": "/var/lib/postgresql/data", "mode": "rw"}},
                healthcheck={
                    "test": ["CMD-SHELL", "pg_isready -U edgequake"],
                    "interval": 5_000_000_000,
                    "timeout": 5_000_000_000,
                    "retries": 5,
                },
                restart_policy={"Name": "unless-stopped"},
            )
        except Exception as e:
            return {"error": f"Failed to start PostgreSQL: {e}"}

        # Wait for health
        for _ in range(30):
            time.sleep(2)
            pg = _get_container(client, POSTGRES_CONTAINER)
            if pg:
                pg.reload()
                h = pg.attrs.get("State", {}).get("Health", {}).get("Status", "")
                if h == "healthy":
                    break
        else:
            return {"error": "PostgreSQL did not become healthy in time."}

    # Start EdgeQuake
    eq = _get_container(client, EDGEQUAKE_CONTAINER)
    if not (eq and eq.status == "running"):
        _remove_container(client, EDGEQUAKE_CONTAINER)
        try:
            client.containers.run(
                EDGEQUAKE_IMAGE,
                detach=True,
                name=EDGEQUAKE_CONTAINER,
                network=NETWORK_NAME,
                environment={
                    "EDGEQUAKE_API_KEY": api_key,
                    "DATABASE_URL": f"postgresql://edgequake:{db_password}@{POSTGRES_CONTAINER}:5432/edgequake",
                    "LLM_PROVIDER": settings.get("llm_provider", "openai"),
                    "LLM_API_KEY": settings.get("llm_api_key", ""),
                    "LLM_MODEL": settings.get("llm_model", ""),
                    "RUST_LOG": settings.get("log_level", "info"),
                },
                ports={"8080/tcp": port},
                restart_policy={"Name": "unless-stopped"},
            )
        except Exception as e:
            return {"error": f"Failed to start EdgeQuake: {e}"}

    return {"success": True, "message": "Server starting..."}


def stop_server() -> dict[str, Any]:
    """
    Stop and remove the EdgeQuake Docker stack.

    Preserves the PostgreSQL data volume.
    """
    client = _get_docker_client()
    if client is None:
        return {"error": "Docker is not available from this environment."}

    errors = []
    for name in [EDGEQUAKE_CONTAINER, POSTGRES_CONTAINER]:
        try:
            _remove_container(client, name)
        except Exception as e:
            errors.append(f"{name}: {e}")

    if errors:
        return {"error": f"Failed to stop: {'; '.join(errors)}"}
    return {"success": True, "message": "Server stopped."}
