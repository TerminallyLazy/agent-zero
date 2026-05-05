"""Structural tests for jcode_harness webui/config.html."""
from __future__ import annotations

from pathlib import Path

import yaml

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
CONFIG_HTML = PLUGIN_ROOT / "webui" / "config.html"
DEFAULT_CFG = PLUGIN_ROOT / "default_config.yaml"


def test_config_html_exists():
    assert CONFIG_HTML.exists(), f"missing {CONFIG_HTML}"


def test_config_html_has_alpine_data_scope():
    text = CONFIG_HTML.read_text(encoding="utf-8")
    assert "x-data" in text


def _walk_keys(node, prefix=""):
    """Yield dotted paths for every leaf key in a YAML mapping."""
    if isinstance(node, dict):
        for k, v in node.items():
            path = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict):
                yield from _walk_keys(v, path)
            else:
                yield path


def test_config_html_binds_all_default_config_keys():
    cfg = yaml.safe_load(DEFAULT_CFG.read_text(encoding="utf-8"))
    text = CONFIG_HTML.read_text(encoding="utf-8")
    missing = []
    for path in _walk_keys(cfg):
        # Each top-level key tree should be reachable via config.<path>.
        # We assert the top-level key path appears in the HTML; nested leaves
        # can be inferred from the same prefix.
        top = path.split(".")[0]
        if f"config.{top}" not in text:
            missing.append(top)
    # Allow oauth_subscriptions (list) and similar leaves to be unbound for v1,
    # but every top-level config.* key must be referenced at least once.
    unique_missing = sorted(set(missing))
    assert not unique_missing, f"top-level config keys not bound: {unique_missing}"


def test_config_html_no_inline_error_divs():
    text = CONFIG_HTML.read_text(encoding="utf-8")
    assert 'class="error"' not in text
    assert 'class="error-box"' not in text
    assert '<div class="error' not in text


def test_config_html_uses_a0_settings_convention():
    """Use A0's `section-title` + `field` + `toggle` pattern, not <fieldset>.

    Regression: <fieldset><legend> rendered with hard white borders that
    clashed with A0's dark theme (caught visually 2026-05-05). The canonical
    A0 convention is verified in plugins/_error_retry/webui/config.html and
    plugins/_skills/webui/config.html.
    """
    text = CONFIG_HTML.read_text(encoding="utf-8")
    # Forbidden: native fieldset-with-legend grouping.
    assert "<fieldset" not in text, (
        "config.html must not use <fieldset>; A0's settings modal expects "
        ".section-title + .field rows for theme-aware layout"
    )
    assert "<legend" not in text
    # Required: A0 settings primitives.
    assert "section-title" in text, "missing .section-title heading class"
    assert "field-label" in text, "missing .field-label structure"
    assert "field-control" in text, "missing .field-control structure"
    assert 'class="toggle"' in text, "checkboxes should use the .toggle switch"
    assert "toggler" in text, "toggle switch needs the .toggler track span"


def test_config_html_template_guards_on_config():
    """Wrap with `<template x-if="config">` so reads on null config don't error.
    Matches the convention in plugins/_error_retry/webui/config.html."""
    text = CONFIG_HTML.read_text(encoding="utf-8")
    assert '<template x-if="config">' in text
