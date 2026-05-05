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
