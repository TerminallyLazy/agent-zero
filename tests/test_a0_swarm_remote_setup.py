import sys
import types
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
async def test_swarm_test_remote_success(monkeypatch):
    from usr.plugins.a0_swarm.api import swarm_test_remote as mod

    fake_conn = MagicMock()
    fake_conn.get_agent_card = AsyncMock(return_value={"name": "Agent Zero"})
    fake_conn.close = AsyncMock()
    monkeypatch.setattr(mod.a2a_runner, "open_connection", AsyncMock(return_value=fake_conn))

    handler = mod.SwarmTestRemote(app=MagicMock(), thread_lock=MagicMock())
    out = await handler.process({"label": "rig", "base_url": "http://rig:55000/a2a/t-token"}, MagicMock())

    assert out["ok"] is True
    assert out["checks"]["agent_card"]["ok"] is True
    assert out["endpoint"] == "rig"


@pytest.mark.asyncio
async def test_swarm_test_remote_connect_failure(monkeypatch):
    from usr.plugins.a0_swarm.api import swarm_test_remote as mod

    monkeypatch.setattr(mod.a2a_runner, "open_connection", AsyncMock(side_effect=RuntimeError("401 Unauthorized")))

    handler = mod.SwarmTestRemote(app=MagicMock(), thread_lock=MagicMock())
    out = await handler.process({"label": "rig", "base_url": "http://rig:55000/a2a/t-token"}, MagicMock())

    assert out["ok"] is False
    assert out["checks"]["agent_card"]["ok"] is False
    assert "401 Unauthorized" in out["checks"]["agent_card"]["error"]


@pytest.mark.asyncio
async def test_swarm_discover_docker_handles_missing_docker(monkeypatch):
    from usr.plugins.a0_swarm.api import swarm_discover_docker as mod

    monkeypatch.setattr(mod.subprocess, "run", MagicMock(side_effect=FileNotFoundError("docker")))

    handler = mod.SwarmDiscoverDocker(app=MagicMock(), thread_lock=MagicMock())
    out = await handler.process({}, MagicMock())

    assert out["ok"] is False
    assert out["candidates"] == []
    assert "docker command not found" in out["error"]
