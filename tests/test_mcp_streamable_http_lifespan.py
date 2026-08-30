import asyncio

import httpx
from starlette.applications import Starlette
from starlette.routing import Mount

from helpers import mcp_server as mcp_server_module
from helpers.mcp_server import DynamicMcpProxy
from helpers.server_startup import StartupMonitor
from helpers.ui_server import compose_server_lifespan


def test_streamable_http_lifespan_supports_tools_list(monkeypatch):
    monkeypatch.setattr(
        mcp_server_module.settings,
        "get_settings",
        lambda: {
            "mcp_server_enabled": True,
            "mcp_server_token": "test-token",
        },
    )

    proxy = DynamicMcpProxy()
    startup_monitor = StartupMonitor(
        bind_host="127.0.0.1",
        probe_host="127.0.0.1",
        port=0,
        attempt=1,
        max_attempts=1,
        timeout_seconds=15,
    )
    app = Starlette(
        routes=[Mount("/mcp", app=proxy)],
        lifespan=compose_server_lifespan(startup_monitor, proxy),
    )

    async def exercise_mcp() -> None:
        path = "/mcp/t-test-token/http"
        headers = {
            "accept": "application/json, text/event-stream",
            "content-type": "application/json",
        }
        transport = httpx.ASGITransport(app=app)

        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://test",
            ) as client:
                initialized = await client.post(
                    path,
                    headers=headers,
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                        "params": {
                            "protocolVersion": "2025-06-18",
                            "capabilities": {},
                            "clientInfo": {
                                "name": "agent-zero-regression",
                                "version": "1.0",
                            },
                        },
                    },
                )

                assert initialized.status_code == 200
                session_id = initialized.headers["mcp-session-id"]
                session_headers = {
                    **headers,
                    "mcp-session-id": session_id,
                }

                acknowledged = await client.post(
                    path,
                    headers=session_headers,
                    json={
                        "jsonrpc": "2.0",
                        "method": "notifications/initialized",
                    },
                )
                assert acknowledged.status_code == 202

                tools = await client.post(
                    path,
                    headers=session_headers,
                    json={
                        "jsonrpc": "2.0",
                        "id": 2,
                        "method": "tools/list",
                        "params": {},
                    },
                )

                assert tools.status_code == 200
                assert {
                    tool["name"] for tool in tools.json()["result"]["tools"]
                } == {"send_message", "finish_chat"}

                closed = await client.delete(path, headers=session_headers)
                assert closed.status_code == 200

    asyncio.run(exercise_mcp())
