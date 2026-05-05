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
    # Store-style invocation, not bare globals.
    assert "$store.jcodeQuick.newSession()" in text
    assert "$store.jcodeQuick.resumeSessionList()" in text


def test_quick_html_uses_alpine_store_pattern():
    text = HTML.read_text(encoding="utf-8")
    # Bare x-data + module import — globals are not loaded by importHtmlExtensions.
    assert "<div x-data" in text
    # Named import `{ store }` required — components.js only rewrites that form.
    assert (
        'import { store } from "/plugins/jcode_harness/extensions/webui/'
        'sidebar-quick-actions-main-start/jcode_quick.js"'
    ) in text
    # Bare side-effect imports break in blob URL context.
    assert (
        'import "/plugins/jcode_harness/extensions/webui/'
        'sidebar-quick-actions-main-start/jcode_quick.js"'
    ) not in text
    assert 'x-data="jcodeQuick()"' not in text


def test_quick_html_uses_material_symbols_icons_only():
    """Per user UX direction: Material Icons only, no text labels, theme-aware bg."""
    text = HTML.read_text(encoding="utf-8")
    # Material Symbols spans for both actions
    assert text.count('class="material-symbols-outlined"') == 2, \
        "both buttons must use material-symbols-outlined span"
    # No literal "New ..." / "Resume" labels in button bodies
    # (Title attribute is fine — that's the tooltip, not a visible label.)
    # Inspect the button INNER content: between <button ...> and </button>
    button_bodies = re.findall(r"<button[^>]*>(.*?)</button>", text, re.DOTALL)
    for body in button_bodies:
        # Strip the icon span; any remaining text content (after whitespace) means text labels
        no_span = re.sub(r"<span[^>]*>[^<]*</span>", "", body)
        no_tags = re.sub(r"<[^>]+>", "", no_span).strip()
        assert no_tags == "", f"button has visible text label: {no_tags!r}"


def test_quick_html_uses_theme_aware_button_class():
    """Reuse A0's .config-button so background follows the theme (no white)."""
    text = HTML.read_text(encoding="utf-8")
    assert 'class="config-button"' in text, \
        "buttons should use A0's .config-button class for theme-aware styling"
    # No inline white backgrounds
    assert "background:white" not in text.lower().replace(" ", "")
    assert "background-color:white" not in text.lower().replace(" ", "")
    assert "background:#fff" not in text.lower().replace(" ", "")


def test_quick_js_exports_jcodeQuick_store():
    assert JS.exists(), f"missing {JS}"
    text = JS.read_text(encoding="utf-8")
    assert 'createStore("jcodeQuick"' in text
    assert "export const store" in text
    assert 'import { createStore } from "/js/AlpineStore.js"' in text
    assert "window.jcodeQuick" not in text


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
