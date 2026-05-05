"""Structural tests for jcode_harness webui/main.html and main.js."""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
WEBUI = PLUGIN_ROOT / "webui"


def test_main_html_exists_and_has_alpine_data():
    p = WEBUI / "main.html"
    assert p.exists(), f"missing {p}"
    text = p.read_text(encoding="utf-8")
    # Alpine store pattern: bare x-data scope marker + module import +
    # $store.jcodeMain refs. Attributes (class, etc.) may follow x-data.
    assert re.search(r"<div\s+x-data(?:\s|>)", text), "missing <div x-data> scope"
    # Named import `{ store }` is required — A0's components.js only rewrites
    # `import X from "..."` syntax; bare side-effect imports fail to resolve
    # absolute paths in the blob URL context (regression caught 2026-05-05).
    assert 'import { store } from "/plugins/jcode_harness/webui/main.js"' in text
    assert 'import "/plugins/jcode_harness/webui/main.js"' not in text  # bare-import banned
    assert "$store.jcodeMain" in text
    # Old broken global pattern must be gone.
    assert 'x-data="jcodeMain()"' not in text


def test_main_html_uses_notification_store_not_inline_errors():
    p = WEBUI / "main.html"
    text = p.read_text(encoding="utf-8")
    assert 'class="error"' not in text
    assert 'class="error-box"' not in text
    assert '<div class="error' not in text


def test_main_html_uses_a0_styling_primitives():
    """Main page must use A0's themed primitives (.section-title, .button,
    .material-symbols-outlined) and avoid raw <h2>/<h3> headings + bare
    <button> elements that render with browser defaults (white background,
    serif font, no theme awareness).

    Regression: 2026-05-05 — initial main.html shipped with raw <h2><h3>
    + unstyled <button>, looking like a 1995 form on top of A0's dark theme.
    """
    p = WEBUI / "main.html"
    text = p.read_text(encoding="utf-8")
    # No raw heading tags.
    assert "<h2" not in text, "use .section-title div, not <h2>"
    assert "<h3" not in text, "use .section-title div, not <h3>"
    # No unstyled <ul><li> session list.
    assert "<ul" not in text, "session list should be card-based, not <ul>"
    # A0 primitives present.
    assert "section-title" in text, "missing .section-title heading class"
    assert 'class="button"' in text, (
        "buttons must use A0's .button class, not bare <button>"
    )
    # Material icons in use, not text-only buttons.
    assert "material-symbols-outlined" in text


def test_main_html_has_modal_title():
    """Modal renders <title> in its header bar instead of showing the raw
    file path. Without <title>, A0 falls back to the .html path which looks
    unprofessional (caught visually 2026-05-05)."""
    p = WEBUI / "main.html"
    text = p.read_text(encoding="utf-8")
    assert re.search(r"<title>[^<]+</title>", text), (
        "main.html needs a <title> so the modal header doesn't show the raw path"
    )


def test_main_js_exports_jcodeMain_store():
    p = WEBUI / "main.js"
    assert p.exists(), f"missing {p}"
    text = p.read_text(encoding="utf-8")
    assert 'createStore("jcodeMain"' in text
    assert "export const store" in text
    assert 'import { createStore } from "/js/AlpineStore.js"' in text
    # Old broken global pattern must be gone.
    assert "window.jcodeMain" not in text


def test_main_js_calls_correct_api_endpoints():
    p = WEBUI / "main.js"
    text = p.read_text(encoding="utf-8")
    for endpoint in (
        "/api/plugins/jcode_harness/daemon_status",
        "/api/plugins/jcode_harness/list_sessions",
        "/api/plugins/jcode_harness/resume_session",
        "/api/plugins/jcode_harness/login_provider",
        "/api/plugins/jcode_harness/purge_imported_profiles",
    ):
        assert endpoint in text, f"missing endpoint: {endpoint}"


def test_main_js_uses_notification_store_for_toasts():
    p = WEBUI / "main.js"
    text = p.read_text(encoding="utf-8")
    # Confirm we route through $store.notificationStore (compliance with §3).
    assert "$store?.notificationStore?.frontendSuccess" in text
    assert "$store?.notificationStore?.frontendError" in text
    assert "$store?.notificationStore?.frontendInfo" in text


@pytest.mark.skipif(shutil.which("node") is None, reason="node not on PATH")
def test_main_js_parses_with_node():
    p = WEBUI / "main.js"
    r = subprocess.run(
        ["node", "--check", str(p)],
        capture_output=True, text=True, timeout=10,
    )
    assert r.returncode == 0, f"node --check failed:\n{r.stderr}"
