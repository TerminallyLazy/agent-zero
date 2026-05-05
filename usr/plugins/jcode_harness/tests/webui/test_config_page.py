"""Smoke: config.html renders A0-canonical sections without runtime errors.

Real A0 wraps plugin config.html in a parent scope that provides `config`
(see plugins/_error_retry/webui/config.html — same `<template x-if="config">`
guard). The test injects an equivalent default config before asserting
visibility so the conditional template renders.
"""


def test_config_loads_with_a0_settings_sections(http_server, browser_context):
    """The conftest shell wraps `surface=config` in a parent x-data providing
    `config` (mirroring A0's plugin settings modal scope), so the
    `<template x-if="config">` guard inside config.html renders here."""
    page = browser_context.new_page()
    page.goto(f"{http_server}/?surface=config")
    page.wait_for_function("window.__rootLoaded === true", timeout=5000)
    page.wait_for_timeout(300)

    assert page.locator("text=Binary").first.is_visible()
    assert page.locator("text=Features").first.is_visible()
    assert page.locator("text=Safety").first.is_visible()
    # A0 settings convention present: section heading + at least one toggle.
    assert page.locator(".section-title").first.is_visible()
    assert page.locator(".toggle .toggler").count() > 0
    # Old fieldset-with-legend pattern must not render.
    assert page.locator("fieldset").count() == 0
    assert page.locator("legend").count() == 0

    errs = page.evaluate("window.__alpineErrors || []")
    unexpected = [e for e in errs if "is not defined" in e]
    assert unexpected == [], f"unexpected plugin errors: {unexpected}"
