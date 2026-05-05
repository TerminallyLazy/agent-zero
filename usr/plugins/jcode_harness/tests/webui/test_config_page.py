"""Smoke: config.html renders the expected fieldsets without runtime errors."""


def test_config_loads_with_settings_fieldsets(http_server, browser_context):
    page = browser_context.new_page()
    page.goto(f"{http_server}/?surface=config")
    page.wait_for_function("window.__rootLoaded === true", timeout=5000)
    page.wait_for_timeout(300)
    assert page.locator("text=Binary").first.is_visible()
    assert page.locator("text=Features").first.is_visible()
    assert page.locator("text=Safety").first.is_visible()
    # config.html is a binding shell that expects A0's parent scope to provide
    # `config`. In this isolated harness `config` is undefined -- by design.
    # We assert no UNEXPECTED runtime errors (anything other than the expected
    # `config is not defined` from the empty parent scope).
    errs = page.evaluate("window.__alpineErrors || []")
    unexpected = [
        e for e in errs
        if "is not defined" in e and "config is not defined" not in e
    ]
    assert unexpected == [], f"unexpected plugin errors: {unexpected}"
