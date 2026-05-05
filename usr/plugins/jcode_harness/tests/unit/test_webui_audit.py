"""Audit tests for jcode_harness webui surfaces.

Confirms compliance with AGENTS.plugins.md §3: no inline error UI anywhere
in plugin webui — all user feedback must route through $store.notificationStore.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
WEBUI = PLUGIN_ROOT / "webui"
EXT_WEBUI = PLUGIN_ROOT / "extensions" / "webui"
BANNER_DIR = EXT_WEBUI / "welcome-banners-start"
BANNER_HTML = BANNER_DIR / "jcode_login_required.html"
BANNER_JS = BANNER_DIR / "jcode_login_required.js"

# Patterns that indicate inline error UI, which we forbid.
INLINE_ERROR_PATTERNS = (
    'class="error"',
    'class="error-box"',
    '<div class="error',
)


def _scan_dir(root: Path):
    """Yield (path, text) pairs for every .html and .js file under root."""
    for p in root.rglob("*"):
        if p.suffix in (".html", ".js") and p.is_file():
            yield p, p.read_text(encoding="utf-8")


def test_banner_html_exists_and_gates_on_needsLogin():
    assert BANNER_HTML.exists(), f"missing {BANNER_HTML}"
    text = BANNER_HTML.read_text(encoding="utf-8")
    # Alpine store pattern: bare x-data + module import + $store-gated visibility.
    assert "<div x-data" in text
    # Named import `{ store }` required — components.js only rewrites that form.
    assert (
        'import { store } from "/plugins/jcode_harness/extensions/webui/'
        'welcome-banners-start/jcode_login_required.js"'
    ) in text
    # Bare side-effect imports break in blob URL context.
    assert (
        'import "/plugins/jcode_harness/extensions/webui/'
        'welcome-banners-start/jcode_login_required.js"'
    ) not in text
    assert 'x-show="$store.jcodeLoginBanner.needsLogin"' in text
    assert 'x-data="jcodeLoginBanner()"' not in text


def test_banner_js_exists_and_exports_jcodeLoginBanner_store():
    assert BANNER_JS.exists(), f"missing {BANNER_JS}"
    text = BANNER_JS.read_text(encoding="utf-8")
    assert 'createStore("jcodeLoginBanner"' in text
    assert "export const store" in text
    assert 'import { createStore } from "/js/AlpineStore.js"' in text
    assert "window.jcodeLoginBanner" not in text


def test_banner_js_uses_notification_store_for_open_settings():
    text = BANNER_JS.read_text(encoding="utf-8")
    assert "$store?.notificationStore?.frontendInfo" in text


def test_no_inline_error_divs_anywhere_in_plugin_webui():
    """Scan plugin webui surfaces for inline error markup. None allowed."""
    offenders = []
    for root in (WEBUI, EXT_WEBUI):
        if not root.exists():
            continue
        for path, text in _scan_dir(root):
            for pat in INLINE_ERROR_PATTERNS:
                if pat in text:
                    offenders.append(f"{path}: {pat}")
    assert not offenders, "inline error UI found:\n" + "\n".join(offenders)


def test_all_webui_files_use_notification_store_or_have_no_user_messages():
    """Any JS that surfaces user messages must use $store.notificationStore.

    Heuristic: if the file calls alert() or builds an error <div>, that's a
    failure. We don't require every file to *have* a notification call —
    panel.js for example just renders content.
    """
    offenders = []
    for root in (WEBUI, EXT_WEBUI):
        if not root.exists():
            continue
        for path, text in _scan_dir(root):
            if path.suffix != ".js":
                continue
            if re.search(r"\balert\s*\(", text):
                offenders.append(f"{path}: alert() forbidden")
            # Don't allow building <div class="error"> via string concat.
            if re.search(r'["\']\s*<div\s+class\s*=\s*["\']error', text):
                offenders.append(f"{path}: builds inline error <div>")
    assert not offenders, "\n".join(offenders)


@pytest.mark.skipif(shutil.which("node") is None, reason="node not on PATH")
def test_banner_js_parses_with_node():
    r = subprocess.run(
        ["node", "--check", str(BANNER_JS)],
        capture_output=True, text=True, timeout=10,
    )
    assert r.returncode == 0, f"node --check failed:\n{r.stderr}"
