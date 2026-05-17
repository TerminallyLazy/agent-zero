import sys
import types
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if "helpers.api" not in sys.modules:
    _api_stub = types.ModuleType("helpers.api")

    class _ApiHandler:
        def __init__(self, app=None, thread_lock=None):
            self.app = app
            self.thread_lock = thread_lock

    _api_stub.ApiHandler = _ApiHandler
    _api_stub.Request = object
    sys.modules["helpers.api"] = _api_stub

import pytest


@pytest.mark.asyncio
async def test_a2a_runner_accepts_current_framework_client_availability_name(monkeypatch):
    from usr.plugins.a0_swarm.helpers import a2a_runner

    fake_conn = MagicMock()
    calls = []

    def agent_connection(**kwargs):
        calls.append(kwargs)
        return fake_conn

    fake_client_module = SimpleNamespace(
        is_client_available=lambda: True,
        AgentConnection=agent_connection,
    )
    monkeypatch.setattr(a2a_runner, "_client_module", lambda: fake_client_module)

    from usr.plugins.a0_swarm.helpers.remotes import RemoteEndpoint

    remote = RemoteEndpoint(label="rig", base_url="http://rig:55000/a2a/t-token", auth_token="tok")

    assert a2a_runner.is_available() is True
    assert await a2a_runner.open_connection(remote) is fake_conn
    assert calls == [{"agent_url": "http://rig:55000/a2a/t-token", "token": "tok"}]


@pytest.mark.asyncio
async def test_swarm_test_remote_success(monkeypatch):
    from usr.plugins.a0_swarm.api import swarm_test_remote as mod

    fake_conn = MagicMock()
    fake_conn.get_agent_card = AsyncMock(return_value={
        "name": "Agent Zero",
        "description": "Remote A0 worker",
        "version": "1.0.0",
        "capabilities": {"streaming": False},
        "defaultInputModes": ["text/plain"],
        "defaultOutputModes": ["text/plain", "application/json"],
        "skills": [
            {"id": "general_assistance", "name": "General AI Assistant", "tags": ["code", "files"]},
        ],
    })
    fake_conn.close = AsyncMock()
    monkeypatch.setattr(mod.a2a_runner, "open_connection", AsyncMock(return_value=fake_conn))

    handler = mod.SwarmTestRemote(app=MagicMock(), thread_lock=MagicMock())
    out = await handler.process({"label": "rig", "base_url": "http://rig:55000/a2a/t-token"}, MagicMock())

    assert out["ok"] is True
    assert out["checks"]["agent_card"]["ok"] is True
    assert out["checks"]["submit"]["ok"] is True
    assert out["checks"]["continuation"]["ok"] is True
    assert out["checks"]["cancel"]["ok"] is True
    assert out["endpoint"] == "rig"
    assert out["remote"]["base_url"] == "http://rig:55000/a2a/t-token"
    assert out["discovery"]["name"] == "Agent Zero"
    assert out["discovery"]["skills"][0]["id"] == "general_assistance"
    assert out["discovery"]["communication"]["context_continuation"] == "available_via_context_id"


@pytest.mark.asyncio
async def test_swarm_test_remote_connect_failure(monkeypatch):
    from usr.plugins.a0_swarm.api import swarm_test_remote as mod

    monkeypatch.setattr(mod.a2a_runner, "open_connection", AsyncMock(side_effect=RuntimeError("401 Unauthorized")))

    handler = mod.SwarmTestRemote(app=MagicMock(), thread_lock=MagicMock())
    out = await handler.process({"label": "rig", "base_url": "http://rig:55000/a2a/t-token"}, MagicMock())

    assert out["ok"] is False
    assert out["checks"]["agent_card"]["ok"] is False
    assert "401 Unauthorized" in out["checks"]["agent_card"]["error"]


class _DockerException(Exception):
    pass


def _install_fake_docker(monkeypatch, from_env):
    """Register a fake `docker` SDK so the handler imports it inside process()."""
    docker_mod = types.ModuleType("docker")
    errors_mod = types.ModuleType("docker.errors")
    errors_mod.DockerException = _DockerException
    docker_mod.errors = errors_mod
    docker_mod.from_env = from_env
    monkeypatch.setitem(sys.modules, "docker", docker_mod)
    monkeypatch.setitem(sys.modules, "docker.errors", errors_mod)


@pytest.mark.asyncio
async def test_swarm_discover_docker_socket_unreachable(monkeypatch):
    from usr.plugins.a0_swarm.api import swarm_discover_docker as mod

    def from_env(**kw):
        raise _DockerException("cannot connect to unix:///var/run/docker.sock")

    _install_fake_docker(monkeypatch, from_env)

    handler = mod.SwarmDiscoverDocker(app=MagicMock(), thread_lock=MagicMock())
    out = await handler.process({}, MagicMock())

    assert out["ok"] is False
    assert out["candidates"] == []
    assert "docker.sock" in out["error"]
    assert out["setup"]["title"] == "Docker Access Setup"
    assert "/var/run/docker.sock:/var/run/docker.sock" in out["setup"]["compose_snippet"]
    assert "-v /var/run/docker.sock:/var/run/docker.sock" in out["setup"]["docker_run_flag"]
    assert any("Docker Desktop" in step for step in out["setup"]["mac_steps"])


def test_plugin_settings_has_docker_access_setup_card():
    config_html = PROJECT_ROOT / "usr" / "plugins" / "a0_swarm" / "webui" / "config.html"
    text = config_html.read_text()

    assert "Docker Access Setup" in text
    assert "context.dockerSetup" in text
    assert "copyDockerSetup" in text
    assert "Recheck Docker access" in text


def test_plugin_settings_has_a2a_discovery_card():
    config_html = PROJECT_ROOT / "usr" / "plugins" / "a0_swarm" / "webui" / "config.html"
    text = config_html.read_text()

    assert "A2A Discovery" in text
    assert "context.discoverA2A" in text
    assert "context.addDiscoveredA2A" in text
    assert "Agent Card" in text


@pytest.mark.asyncio
async def test_swarm_discover_docker_lists_a0_siblings(monkeypatch):
    from usr.plugins.a0_swarm.api import swarm_discover_docker as mod

    a0 = MagicMock()
    a0.name = "agent-zero-research"
    a0.image.tags = ["agent0ai/agent-zero:latest"]
    a0.attrs = {
        "Config": {"Image": "agent0ai/agent-zero:latest"},
        "NetworkSettings": {"Ports": {"55000/tcp": [{"HostPort": "55001"}]}},
    }
    other = MagicMock()
    other.name = "postgres"
    other.image.tags = ["postgres:16"]
    other.attrs = {"Config": {"Image": "postgres:16"}, "NetworkSettings": {"Ports": {}}}

    client = MagicMock()
    client.containers.list.return_value = [a0, other]
    client.close = MagicMock()

    _install_fake_docker(monkeypatch, lambda **kw: client)

    handler = mod.SwarmDiscoverDocker(app=MagicMock(), thread_lock=MagicMock())
    out = await handler.process({}, MagicMock())

    assert out["ok"] is True
    assert len(out["candidates"]) == 1
    cand = out["candidates"][0]
    assert cand["container"] == "agent-zero-research"
    assert cand["base_url"] == "http://agent-zero-research:55000"
    assert "55000/tcp" in cand["ports"]


@pytest.mark.asyncio
async def test_swarm_discover_docker_handles_missing_sdk(monkeypatch):
    from usr.plugins.a0_swarm.api import swarm_discover_docker as mod

    monkeypatch.setitem(sys.modules, "docker", None)  # forces ImportError

    handler = mod.SwarmDiscoverDocker(app=MagicMock(), thread_lock=MagicMock())
    out = await handler.process({}, MagicMock())

    assert out["ok"] is False
    assert out["candidates"] == []
    assert "Docker SDK not available" in out["error"]
