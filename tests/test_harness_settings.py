from __future__ import annotations
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def test_load_default_settings_returns_expected_keys():
    from usr.plugins.agent_harness.helpers.settings import load_default_settings
    defaults = load_default_settings()
    assert defaults["ambient_assist_enabled"] is True
    assert defaults["default_deep_mode"] == "build"
    assert "mode_policies" in defaults
    assert "build" in defaults["mode_policies"]


def test_get_mode_policy_returns_limits():
    from usr.plugins.agent_harness.helpers.settings import (
        load_default_settings, get_mode_policy,
    )
    defaults = load_default_settings()
    policy = get_mode_policy(defaults, "build")
    assert policy == {"subagent_limit": 2, "repair_limit": 1}


def test_deep_merge_settings_merges_nested_dicts():
    from usr.plugins.agent_harness.helpers.settings import _deep_merge_settings
    base = {"a": 1, "nested": {"x": 10, "y": 20}}
    override = {"nested": {"y": 99, "z": 30}}
    result = _deep_merge_settings(base, override)
    assert result == {"a": 1, "nested": {"x": 10, "y": 99, "z": 30}}


def test_deep_merge_settings_deduplicates_accepted_rules():
    from usr.plugins.agent_harness.helpers.settings import _deep_merge_settings
    base = {"accepted_rules": [{"rule_text": "Use rg"}]}
    override = {"accepted_rules": [{"rule_text": "Use rg"}, {"rule_text": "New rule"}]}
    result = _deep_merge_settings(base, override)
    texts = [r["rule_text"] for r in result["accepted_rules"]]
    assert texts == ["Use rg", "New rule"]


def test_get_default_mode_falls_back_to_build():
    from usr.plugins.agent_harness.helpers.settings import get_default_mode
    assert get_default_mode({"default_deep_mode": "surge"}) == "surge"
    assert get_default_mode({"default_deep_mode": "invalid"}) == "build"
    assert get_default_mode({}) == "build"


def test_dashboard_settings_extracts_ui_keys():
    from usr.plugins.agent_harness.helpers.settings import dashboard_settings
    settings = {
        "show_status_ui": False,
        "default_deep_mode": "surge",
        "memory_curation_enabled": True,
        "unrelated_key": 42,
    }
    result = dashboard_settings(settings)
    assert result == {
        "show_status_ui": False,
        "default_deep_mode": "surge",
        "memory_curation_enabled": True,
    }


def test_check_config_version_detects_outdated():
    from usr.plugins.agent_harness.helpers.settings import (
        check_config_version, CURRENT_CONFIG_VERSION,
    )
    assert check_config_version({"config_version": CURRENT_CONFIG_VERSION}) is True
    assert check_config_version({"config_version": 0}) is False
    assert check_config_version({}) is False


def test_auto_upgrade_config_adds_missing_fields():
    from usr.plugins.agent_harness.helpers.settings import auto_upgrade_config
    old_config = {"ambient_assist_enabled": False, "config_version": 1}
    upgraded = auto_upgrade_config(old_config)
    assert upgraded["ambient_assist_enabled"] is False  # preserved
    assert "context_pressure_threshold" in upgraded
    assert "workspace_enabled" in upgraded
