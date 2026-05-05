"""Structural tests for jcode_harness right-canvas extensions (Spike 0.5)."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
EXT = PLUGIN_ROOT / "extensions" / "webui"
SURFACE_JS = EXT / "right-canvas-tabs-start" / "jcode_surface.js"
PANEL_HTML = EXT / "right-canvas-panels" / "jcode_panel.html"
PANEL_JS = EXT / "right-canvas-panels" / "jcode_panel.js"


def test_surface_js_exports_default_async_function():
    assert SURFACE_JS.exists(), f"missing {SURFACE_JS}"
    text = SURFACE_JS.read_text(encoding="utf-8")
    assert "export default async function" in text


def test_surface_js_calls_register_surface_with_jcode_id():
    text = SURFACE_JS.read_text(encoding="utf-8")
    assert "registerSurface" in text
    assert 'id: "jcode"' in text


def test_panel_html_template_uses_isSurfaceActive_jcode_gate():
    assert PANEL_HTML.exists(), f"missing {PANEL_HTML}"
    text = PANEL_HTML.read_text(encoding="utf-8")
    assert "isSurfaceActive('jcode')" in text or 'isSurfaceActive("jcode")' in text


def test_panel_html_renders_pages_with_xfor():
    text = PANEL_HTML.read_text(encoding="utf-8")
    assert 'x-for="page in $store.jcodePanel.pages"' in text


def test_panel_html_uses_alpine_store_pattern():
    text = PANEL_HTML.read_text(encoding="utf-8")
    assert "<div x-data" in text
    assert (
        'import "/plugins/jcode_harness/extensions/webui/'
        'right-canvas-panels/jcode_panel.js"'
    ) in text
    assert 'x-data="jcodePanel()"' not in text


def test_panel_js_exports_jcodePanel_store():
    text = PANEL_JS.read_text(encoding="utf-8")
    assert 'createStore("jcodePanel"' in text
    assert "export const store" in text
    assert 'import { createStore } from "/js/AlpineStore.js"' in text
    assert "window.jcodePanel" not in text


def test_panel_js_listens_for_jcode_side_panel_event():
    assert PANEL_JS.exists(), f"missing {PANEL_JS}"
    text = PANEL_JS.read_text(encoding="utf-8")
    assert 'addEventListener("jcode:side_panel"' in text


def test_panel_js_xss_safety_falls_back_to_pre_when_marked_absent():
    text = PANEL_JS.read_text(encoding="utf-8")
    # Verify the escape sequences exist in the fallback path.
    assert "&amp;" in text
    assert "&lt;" in text
    assert "&gt;" in text
    assert "<pre>" in text


def test_no_inline_error_divs_in_panel_html():
    text = PANEL_HTML.read_text(encoding="utf-8")
    assert 'class="error"' not in text
    assert 'class="error-box"' not in text
    assert '<div class="error' not in text


@pytest.mark.skipif(shutil.which("node") is None, reason="node not on PATH")
def test_surface_js_parses_with_node():
    # Surface uses ES module export; check syntax with --input-type=module.
    text = SURFACE_JS.read_text(encoding="utf-8")
    r = subprocess.run(
        ["node", "--input-type=module", "--check", "-"],
        input=text, capture_output=True, text=True, timeout=10,
    )
    # Node's --check with stdin may not work cross-version; fall back to file
    # check if stdin variant errors out.
    if r.returncode != 0:
        # Try file check (ESM file outside a package may need .mjs extension).
        # Copy to a .mjs temp file.
        import tempfile
        with tempfile.NamedTemporaryFile(
            suffix=".mjs", mode="w", delete=False, encoding="utf-8",
        ) as f:
            f.write(text)
            tmp = f.name
        try:
            r2 = subprocess.run(
                ["node", "--check", tmp],
                capture_output=True, text=True, timeout=10,
            )
            assert r2.returncode == 0, f"node --check failed:\n{r2.stderr}"
        finally:
            Path(tmp).unlink(missing_ok=True)


@pytest.mark.skipif(shutil.which("node") is None, reason="node not on PATH")
def test_panel_js_parses_with_node():
    r = subprocess.run(
        ["node", "--check", str(PANEL_JS)],
        capture_output=True, text=True, timeout=10,
    )
    assert r.returncode == 0, f"node --check failed:\n{r.stderr}"
