"""Playwright fixture: spin up a tiny Flask shim serving:
- /plugins/jcode_harness/<path>  -> real plugin static files
- /js/AlpineStore.js             -> minimal createStore stub
- /alpine.js                     -> real Alpine.js v3 from CDN-cached copy
- /api/plugins/jcode_harness/*   -> mocked JSON responses
- /                              -> page shell loading any plugin HTML by ?surface= query

Tests navigate to /?surface=<name> and assert no console errors + key DOM bits.
"""
from __future__ import annotations

import json
import socket
import threading
import urllib.request
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def alpine_js_bytes():
    """Cache Alpine.js v3 once per session.
    If the cache file exists locally, use it; otherwise fetch from unpkg.
    Skip the whole webui suite if both fail -- environment isn't ready."""
    cache = Path("/tmp/alpine-3.13.5.js")
    if not cache.exists():
        try:
            with urllib.request.urlopen(
                "https://unpkg.com/alpinejs@3.13.5/dist/cdn.min.js",
                timeout=10,
            ) as r:
                cache.write_bytes(r.read())
        except Exception as e:
            pytest.skip(f"alpine.js unavailable, webui tests skipped: {e}")
    return cache.read_bytes()


@pytest.fixture(scope="session")
def http_server(alpine_js_bytes):
    """Tiny stdlib HTTP server. Returns base URL."""
    import http.server

    plugin_root = PLUGIN_ROOT
    api_responses = {
        "/api/plugins/jcode_harness/daemon_status": {
            "running": False,
            "error": "binary not installed",
        },
        "/api/plugins/jcode_harness/list_sessions": {"sessions": []},
        "/api/plugins/jcode_harness/resume_session": {
            "ok": True,
            "session_id": "fake",
        },
        "/api/plugins/jcode_harness/login_provider": {
            "ok": True,
            "auth_url": "https://example.com/auth",
        },
        "/api/plugins/jcode_harness/purge_imported_profiles": {
            "ok": True,
            "purged": [],
        },
        "/api/plugins/jcode_harness/complete_login": {"ok": True},
    }

    SHELL_HTML = b"""<!doctype html>
<html><head>
<script>window.__consoleErrors = [];
const origErr = console.error.bind(console);
console.error = (...a) => { window.__consoleErrors.push(a.map(String).join(' ')); origErr(...a); };
window.__alpineErrors = [];
window.addEventListener('error', e => { window.__alpineErrors.push(String(e.message || e)); });
window.addEventListener('unhandledrejection', e => { window.__alpineErrors.push(String(e.reason || e)); });
</script>
</head><body>
<div id="root"></div>
<script type="module">
// Pre-register A0 framework stores that surface-extensions guard against.
// Done via alpine:init listener so registration happens at start time.
document.addEventListener('alpine:init', () => {
  if (window.Alpine && !window.Alpine.store('rightCanvas')) {
    window.Alpine.store('rightCanvas', {
      isSurfaceActive(_id) { return true; },
      activeSurface: 'jcode',
    });
  }
  if (window.Alpine && !window.Alpine.store('notificationStore')) {
    window.Alpine.store('notificationStore', {
      frontendError() {}, frontendSuccess() {},
      frontendWarning() {}, frontendInfo() {},
    });
  }
});
</script>
<script type="module">
const params = new URLSearchParams(location.search);
const surface = params.get('surface') || 'main';
const url = surface.startsWith('ext:')
  ? `/plugins/jcode_harness/extensions/webui/${surface.slice(4)}`
  : `/plugins/jcode_harness/webui/${surface}.html`;
const r = await fetch(url);
let html = await r.text();
const root = document.getElementById('root');

// `webui/config.html` is a binding shell that A0 wraps in a parent x-data
// providing `config`. Mirror that here so the `<template x-if="config">`
// guard renders during smoke tests. Production A0 supplies the same shape.
if (surface === 'config') {
  const DEFAULT_CFG = JSON.stringify({
    binary: { path: '', auto_update: true },
    daemon: { mode: 'per_project', socket_path: '' },
    features: {
      swarm: true, self_dev: false,
      cross_harness_resume: true, cross_harness_import: false,
    },
    providers: { auto_import_a0_keys: true, oauth_subscriptions: [] },
    ui: { side_panel: true, mermaid: true, notifications: true },
    safety_mode: 'default',
    min_jcode_version: '0.11.4',
  });
  html = `<div x-data='{ config: ${DEFAULT_CFG} }'>${html}</div>`;
}
root.innerHTML = html;

// innerHTML does not execute <script>; re-create + append so module imports run.
// Also descend into <template> contents (which are inert DocumentFragments)
// because surface extensions sometimes guard their content with <template x-if>.
function collectScripts(scope) {
  const out = Array.from(scope.querySelectorAll('script'));
  for (const tpl of scope.querySelectorAll('template')) {
    out.push(...collectScripts(tpl.content));
  }
  return out;
}
const scripts = collectScripts(root);
for (const oldScript of scripts) {
  const ns = document.createElement('script');
  for (const a of oldScript.attributes) ns.setAttribute(a.name, a.value);
  ns.textContent = oldScript.textContent;
  // Hoist to <body> so the script always executes, even if its template guard
  // never renders (it would otherwise live inside an inert template fragment).
  document.body.appendChild(ns);
  oldScript.remove();
}
// Wait for inline `<script type="module">` to load + execute its imports
// (which call createStore -> populates window.__registeredStores). Inline
// modules don't fire load events reliably, so poll up to 2s.
const settleStart = Date.now();
const expected = scripts.filter(s => s.type === 'module').length;
while (Date.now() - settleStart < 2000) {
  const got = Object.keys(window.__registeredStores || {}).length;
  if (got >= expected && got > 0) break;
  await new Promise(r => setTimeout(r, 25));
}
// Now load Alpine.js. v3 auto-starts on DOMContentLoaded (already fired) or
// immediately if the script is added later -- so on script-load, Alpine sees
// the populated DOM AND queued createStore listeners (alpine:init) fire to
// register stores BEFORE the first reactive render.
await new Promise((res, rej) => {
  const s = document.createElement('script');
  s.src = '/alpine.js';
  s.onload = res;
  s.onerror = rej;
  document.head.appendChild(s);
});
// Give Alpine a microtask + small delay to evaluate initial bindings.
await new Promise(r => setTimeout(r, 50));
window.__rootLoaded = true;
</script>
</body></html>
"""

    ALPINE_STORE_JS = b"""
// Minimal createStore for testing the plugin's stores.
window.__pendingStores = window.__pendingStores || [];
window.__registeredStores = window.__registeredStores || {};
export function createStore(name, initialState) {
  window.__pendingStores.push(name);
  window.__registeredStores[name] = initialState;
  const register = () => {
    window.Alpine.store(name, initialState);
    const i = window.__pendingStores.indexOf(name);
    if (i >= 0) window.__pendingStores.splice(i, 1);
  };
  if (window.Alpine && window.Alpine.store) {
    register();
  } else {
    document.addEventListener('alpine:init', register);
  }
  return initialState;
}
export function getStore(name) { return window.Alpine && window.Alpine.store(name); }
"""

    NOTIFICATION_STORE_JS = b"""
// Stub for /components/notifications/notification-store.js
export const toastFrontendError = (m, t) => console.log('toastErr', t, m);
export const toastFrontendSuccess = (m, t) => console.log('toastOk', t, m);
export const toastFrontendWarning = (m, t) => console.log('toastWarn', t, m);
export const toastFrontendInfo = (m, t) => console.log('toastInfo', t, m);
"""

    class Handler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a, **kw):
            pass

        def do_GET(self):
            if self.path == "/" or self.path.startswith("/?"):
                return self._send(SHELL_HTML, "text/html")
            if self.path == "/alpine.js":
                return self._send(alpine_js_bytes, "application/javascript")
            if self.path == "/js/AlpineStore.js":
                return self._send(ALPINE_STORE_JS, "application/javascript")
            if self.path == "/components/notifications/notification-store.js":
                return self._send(NOTIFICATION_STORE_JS, "application/javascript")
            if self.path.startswith("/plugins/jcode_harness/"):
                rel = self.path[len("/plugins/jcode_harness/"):]
                rel = rel.split("?", 1)[0]
                fp = plugin_root / rel
                if fp.is_file():
                    ctype = (
                        "text/html"
                        if fp.suffix in (".html",)
                        else "application/javascript"
                        if fp.suffix in (".js",)
                        else "text/yaml"
                        if fp.suffix in (".yaml",)
                        else "text/plain"
                    )
                    return self._send(fp.read_bytes(), ctype)
            if self.path in api_responses:
                return self._send(
                    json.dumps(api_responses[self.path]).encode(),
                    "application/json",
                )
            self.send_error(404)

        def do_POST(self):
            path = self.path.split("?", 1)[0]
            if path in api_responses:
                # Drain request body if any so connection closes cleanly
                length = int(self.headers.get("content-length") or 0)
                if length:
                    try:
                        self.rfile.read(length)
                    except Exception:
                        pass
                return self._send(
                    json.dumps(api_responses[path]).encode(),
                    "application/json",
                )
            self.send_error(404)

        def _send(self, body, ctype):
            self.send_response(200)
            self.send_header("content-type", ctype)
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


@pytest.fixture(scope="session")
def browser_context():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        pytest.skip("playwright not installed")
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as e:
            pytest.skip(f"playwright chromium not available: {e}")
        ctx = browser.new_context()
        yield ctx
        ctx.close()
        browser.close()
