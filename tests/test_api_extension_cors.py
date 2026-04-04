from __future__ import annotations

import sys
import threading
from pathlib import Path
from unittest.mock import patch

from flask import Flask

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from helpers.api import register_api_route


def _make_app() -> Flask:
    app = Flask("test_api_extension_cors")
    app.secret_key = "test-secret"
    register_api_route(app, threading.RLock())
    return app


def test_extension_preflight_returns_cors_headers() -> None:
    client = _make_app().test_client()

    response = client.open(
        "/api/api_log_get",
        method="OPTIONS",
        headers={
            "Origin": "chrome-extension://abcdefghijklmnop",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type, X-API-KEY",
        },
    )

    assert response.status_code == 204
    assert response.headers.get("Access-Control-Allow-Origin") == "chrome-extension://abcdefghijklmnop"
    assert "OPTIONS" in response.headers.get("Access-Control-Allow-Methods", "")
    assert "X-API-KEY" in response.headers.get("Access-Control-Allow-Headers", "")


def test_non_extension_origin_does_not_get_extension_cors_headers() -> None:
    client = _make_app().test_client()

    response = client.open(
        "/api/api_log_get",
        method="OPTIONS",
        headers={"Origin": "https://example.com"},
    )

    assert response.status_code == 204
    assert response.headers.get("Access-Control-Allow-Origin") is None


@patch("helpers.settings.get_settings", return_value={"mcp_server_token": "secret-key"})
def test_plugin_session_upsert_requires_valid_api_key(_mock) -> None:
    client = _make_app().test_client()
    payload = {
        "browser_session_id": "browser-test-1",
        "context_id": "ctx-test-1",
        "active_tab_id": 11,
        "tabs": [
            {
                "tab_id": 11,
                "window_id": 1,
                "url": "https://example.com",
                "title": "Example",
                "active": True,
                "focused": True,
            }
        ],
        "capabilities": {"bridge": "mv3"},
    }

    missing = client.post("/api/plugins/chrome_extension/session_upsert", json=payload)
    assert missing.status_code == 401

    wrong = client.post(
        "/api/plugins/chrome_extension/session_upsert",
        json=payload,
        headers={"X-API-KEY": "wrong-key"},
    )
    assert wrong.status_code == 401

    ok = client.post(
        "/api/plugins/chrome_extension/session_upsert",
        json=payload,
        headers={"X-API-KEY": "secret-key"},
    )

    assert ok.status_code == 200
    body = ok.get_json()
    assert body["ok"] is True
    assert body["session"]["browser_session_id"] == "browser-test-1"
    assert body["session"]["context_id"] == "ctx-test-1"
    assert body["session"]["active_tab_id"] == 11
    assert body["session"]["tabs"][0]["tab_id"] == 11
