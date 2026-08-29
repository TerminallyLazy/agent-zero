from __future__ import annotations

import json
from pathlib import Path

import yaml


PLUGIN_ROOT = Path(__file__).resolve().parents[1]


def _checked_in_configs() -> tuple[dict, dict]:
    defaults = yaml.safe_load((PLUGIN_ROOT / "default_config.yaml").read_text(encoding="utf-8"))
    runtime = json.loads((PLUGIN_ROOT / "config.json").read_text(encoding="utf-8"))
    return defaults, runtime


def _assert_inert_v2_defaults(config: dict) -> None:
    assert config["config_version"] == 2
    assert config["enabled"] is False
    assert config["instrumentation_enabled"] is False
    assert config["optimization"]["enabled"] is False
    assert config["optimization"]["auto_optimize"] is False
    assert config["prompt"]["inject_guidance"] is False
    assert config["rlm"]["enabled"] is True
    assert config["prompt_optimization"]["enabled"] is False
    assert config["prompt_optimization"]["allow_prompt_capture"] is False
    assert config["prompt_optimization"]["automatic_requires_canary"] is True
    assert config["dependencies"]["install_mode"] == "isolated_worker"
    assert config["dependencies"]["ensure_at_startup"] is True
    assert config["engine"] == "heuristic"
    assert config["worker"]["backend"] == "sqlite_local"
    assert config["worker"]["max_workers"] == 1


def test_checked_in_default_config_is_inert_v2() -> None:
    defaults, _ = _checked_in_configs()

    _assert_inert_v2_defaults(defaults)


def test_checked_in_runtime_config_matches_inert_v2_defaults() -> None:
    defaults, runtime = _checked_in_configs()

    _assert_inert_v2_defaults(runtime)
    assert runtime == defaults


def test_checked_in_runtime_config_has_no_conflicting_legacy_aliases() -> None:
    _, runtime = _checked_in_configs()

    forbidden_legacy_keys = {
        "auto_optimize_enabled",
        "optimization_interval_messages",
        "optimization_min_samples",
        "optimization_trace_window",
        "optimization_cooldown_hours",
        "enable_dspy_optimizer",
        "gepa_steps",
        "gepa_threads",
        "trace_enabled",
        "trace_retention_limit",
        "auto_optimize",
        "scheduler_max_workers",
    }
    assert forbidden_legacy_keys.isdisjoint(runtime)
