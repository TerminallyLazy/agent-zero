"""Structural tests for jcode_harness sidebar quick actions extension."""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
EXT = PLUGIN_ROOT / "extensions" / "webui" / "sidebar-quick-actions-main-start"
HTML = EXT / "jcode_quick.html"
JS = EXT / "jcode_quick.js"


def test_quick_html_has_two_buttons():
    assert HTML.exists(), f"missing {HTML}"
    text = HTML.read_text(encoding="utf-8")
    buttons = re.findall(r"<button\b", text)
    assert len(buttons) == 2, f"expected 2 buttons, found {len(buttons)}"
    assert "newSession()" in text
    assert "resumeSessionList()" in text


def test_quick_js_exports_jcodeQuick():
    assert JS.exists(), f"missing {JS}"
    text = JS.read_text(encoding="utf-8")
    assert "window.jcodeQuick = function" in text


def test_quick_js_uses_notification_store_for_all_messages():
    text = JS.read_text(encoding="utf-8")
    # No bare alerts or DOM error injections.
    assert re.search(r"\balert\(", text) is None, "alert() forbidden"
    assert "document.body" not in text
    # All user feedback paths route through notificationStore.
    assert "$store?.notificationStore?.frontendSuccess" in text
    assert "$store?.notificationStore?.frontendError" in text
    assert "$store?.notificationStore?.frontendInfo" in text


@pytest.mark.skipif(shutil.which("node") is None, reason="node not on PATH")
def test_quick_js_parses_with_node():
    r = subprocess.run(
        ["node", "--check", str(JS)],
        capture_output=True, text=True, timeout=10,
    )
    assert r.returncode == 0, f"node --check failed:\n{r.stderr}"
