"""Smoke each plugin webui extension HTML loads + its store registers cleanly."""
import pytest

EXTENSIONS = [
    ("ext:sidebar-quick-actions-main-start/jcode_quick.html", "jcodeQuick"),
    ("ext:welcome-banners-start/jcode_login_required.html", "jcodeLoginBanner"),
    ("ext:right-canvas-panels/jcode_panel.html", "jcodePanel"),
]


@pytest.mark.parametrize("surface,store_name", EXTENSIONS)
def test_extension_loads_and_registers_store(
    http_server, browser_context, surface, store_name,
):
    page = browser_context.new_page()
    page.goto(f"{http_server}/?surface={surface}")
    page.wait_for_function("window.__rootLoaded === true", timeout=5000)
    # Wait for store registration
    page.wait_for_function(
        f"window.Alpine && window.Alpine.store('{store_name}') !== undefined",
        timeout=3000,
    )
    errs = page.evaluate("window.__alpineErrors || []")
    plugin_errs = [
        e for e in errs if store_name in e or "is not defined" in e
    ]
    assert plugin_errs == [], f"{store_name} runtime errors: {plugin_errs}"
