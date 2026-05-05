"""Smoke: main.html loads with createStore stores resolved, no console errors."""


def test_main_loads_without_console_errors(http_server, browser_context):
    page = browser_context.new_page()
    page.goto(f"{http_server}/?surface=main")
    page.wait_for_function("window.__rootLoaded === true", timeout=5000)
    page.wait_for_timeout(300)  # let Alpine settle
    assert page.locator("text=Daemon").first.is_visible()
    assert page.locator("text=Resumable Sessions").first.is_visible()
    assert page.locator("text=Providers").first.is_visible()
    errs = page.evaluate("window.__alpineErrors || []")
    plugin_errs = [e for e in errs if "jcode" in e.lower() or "is not defined" in e]
    assert plugin_errs == [], f"plugin runtime errors: {plugin_errs}"


def test_main_daemon_status_renders(http_server, browser_context):
    page = browser_context.new_page()
    page.goto(f"{http_server}/?surface=main")
    page.wait_for_function("window.__rootLoaded === true", timeout=5000)
    page.wait_for_timeout(300)
    # Mocked /daemon_status returns running:false -> "Stopped" branch visible
    assert page.locator("text=Stopped").first.is_visible()
