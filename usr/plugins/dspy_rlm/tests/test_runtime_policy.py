"""Contract tests for the DSPy RLM configuration safety boundary.

These tests deliberately exercise the public policy instead of extension hooks: capture,
automatic enqueueing, manual optimization, and prompt injection must remain separately
controlled capabilities.
"""

from __future__ import annotations

import inspect
from copy import deepcopy
from typing import Any

import pytest

from usr.plugins.dspy_rlm.helpers import config as config_module
from usr.plugins.dspy_rlm.helpers.runtime_policy import RuntimePolicy


# The v2 migration may retain compatibility mirrors while callers transition.  Read
# canonical fields first, but accept a mirror when asserting the contract so this test
# continues to describe behaviour rather than an incidental representation.
_PATHS = {
    "capture": (
        ("instrumentation", "enabled"),
        ("instrumentation_enabled",),
        ("trace_enabled",),
    ),
    "enqueue": (
        ("optimization", "auto_enqueue"),
        ("optimization", "auto_optimize"),
        ("auto_enqueue_enabled",),
        ("auto_optimize_enabled",),
    ),
    "optimize": (("optimization", "enabled"),),
    "inject": (
        ("prompt", "inject_guidance"),
        ("prompt", "enabled"),
        ("inject_guidance",),
    ),
}


def _get_path(config: dict[str, Any], path: tuple[str, ...]) -> Any:
    value: Any = config
    for key in path:
        if not isinstance(value, dict) or key not in value:
            return None
        value = value[key]
    return value


def _configured_value(config: dict[str, Any], capability: str) -> Any:
    for path in _PATHS[capability]:
        value = _get_path(config, path)
        if value is not None:
            return value
    return None


def _policy(config: dict[str, Any]) -> RuntimePolicy:
    factory = getattr(RuntimePolicy, "from_config", None)
    assert callable(factory), "RuntimePolicy must expose RuntimePolicy.from_config(config)"
    return factory(config)


def _allowed(policy: RuntimePolicy, gate: str, *, force: bool | None = None) -> bool:
    """Call a policy gate whether its implementation is a property or a method.

    `force` is supplied only when the gate declares it.  This keeps the contract
    focused on the result and permits an implementation to keep force at the API
    layer for gates where it has no valid meaning.
    """
    member = getattr(policy, gate, None)
    assert member is not None, f"RuntimePolicy must expose {gate}"
    if not callable(member):
        # A property-style gate has no parameter surface; force therefore cannot
        # change its result.
        return bool(member)

    parameters = inspect.signature(member).parameters
    kwargs: dict[str, Any] = {}
    if force is not None and "force" in parameters:
        kwargs["force"] = force
    result = member(**kwargs)
    if hasattr(result, "allowed"):
        result = result.allowed
    assert isinstance(result, bool), f"{gate} must return bool (or an object with bool .allowed)"
    return result


def _enabled_config(
    *,
    capture: bool = True,
    enqueue: bool = True,
    optimize: bool = True,
    inject: bool = True,
) -> dict[str, Any]:
    """Return one unambiguous config that enables the four independent gates.

    Matching compatibility aliases are intentional.  They prove aliases can coexist
    when they agree, while separate tests below prove disagreement fails closed.
    """
    return {
        "enabled": True,
        "instrumentation": {"enabled": capture},
        "instrumentation_enabled": capture,
        "trace_enabled": capture,
        "optimization": {
            "enabled": optimize,
            "auto_enqueue": enqueue,
            "auto_optimize": enqueue,
        },
        "auto_enqueue_enabled": enqueue,
        "auto_optimize_enabled": enqueue,
        "prompt": {"inject_guidance": inject},
        "inject_guidance": inject,
    }


def _normalize(raw: dict[str, Any] | None) -> dict[str, Any]:
    normalized = config_module.normalize_config(deepcopy(raw))
    assert isinstance(normalized, dict)
    return normalized


def test_defaults_are_fail_closed_for_every_runtime_capability() -> None:
    cfg = _normalize(None)
    policy = _policy(cfg)

    # Do not let a master plugin switch hide unsafe effective defaults.  Each
    # capability must be explicitly disabled in normalized configuration as well.
    assert _configured_value(cfg, "capture") is False
    assert _configured_value(cfg, "enqueue") is False
    assert _configured_value(cfg, "optimize") is False
    assert _configured_value(cfg, "inject") is False
    assert _allowed(policy, "can_capture") is False
    assert _allowed(policy, "can_enqueue") is False
    assert _allowed(policy, "can_optimize") is False
    assert _allowed(policy, "can_inject") is False
    assert _allowed(policy, "can_auto_promote") is False


@pytest.mark.parametrize(
    ("override", "expected"),
    [
        ({"capture": False}, (False, True, True, True)),
        ({"enqueue": False}, (True, False, True, True)),
        ({"optimize": False}, (True, False, False, True)),
        ({"inject": False}, (True, True, True, False)),
    ],
    ids=("capture", "enqueue", "optimization", "injection"),
)
def test_runtime_capabilities_are_independently_gated(
    override: dict[str, bool], expected: tuple[bool, bool, bool, bool]
) -> None:
    cfg = _normalize(_enabled_config(**override))
    policy = _policy(cfg)

    actual = (
        _allowed(policy, "can_capture"),
        _allowed(policy, "can_enqueue"),
        _allowed(policy, "can_optimize"),
        _allowed(policy, "can_inject"),
    )
    assert actual == expected


def test_force_only_bypasses_runtime_thresholds_not_safety_gates() -> None:
    # A manual request may bypass cooldown/sample admission downstream, but it must
    # not turn a disabled optimizer into an enabled one.
    disabled = _policy(_normalize(_enabled_config(optimize=False, enqueue=False)))
    assert _allowed(disabled, "can_optimize", force=True) is False
    assert _allowed(disabled, "can_enqueue", force=True) is False

    # Force has no authority to enable unrelated capture or prompt-injection paths.
    unrelated_disabled = _policy(_normalize(_enabled_config(capture=False, inject=False)))
    assert _allowed(unrelated_disabled, "can_capture") is False
    assert _allowed(unrelated_disabled, "can_inject") is False


def test_sparse_config_is_deep_merged_and_does_not_enable_omitted_capabilities() -> None:
    cfg = _normalize({"optimization": {"enabled": True}})
    policy = _policy(cfg)

    assert _configured_value(cfg, "optimize") is True
    # Omitted safety-sensitive controls must be present after the merge and false,
    # rather than inheriting an unsafe default or disappearing into truthy fallbacks.
    assert _configured_value(cfg, "capture") is False
    assert _configured_value(cfg, "enqueue") is False
    assert _configured_value(cfg, "inject") is False
    assert _allowed(policy, "can_capture") is False
    assert _allowed(policy, "can_enqueue") is False
    assert _allowed(policy, "can_inject") is False


def test_legacy_aliases_migrate_to_matching_canonical_controls() -> None:
    cfg = _normalize(
        {
            "enabled": True,
            "trace_enabled": True,
            "auto_optimize_enabled": True,
            "optimization": {"enabled": True},
            "gepa_steps": 7,
            "gepa_threads": 3,
            "prompt": {"inject_guidance": True},
        }
    )
    policy = _policy(cfg)

    assert _configured_value(cfg, "capture") is True
    assert _configured_value(cfg, "enqueue") is True
    assert _configured_value(cfg, "optimize") is True
    assert _configured_value(cfg, "inject") is True
    assert _get_path(cfg, ("optimization", "ge_pa_steps")) == 7
    assert _get_path(cfg, ("optimization", "ge_pa_threads")) == 3
    assert _allowed(policy, "can_capture") is True
    assert _allowed(policy, "can_enqueue") is True
    assert _allowed(policy, "can_optimize") is True
    assert _allowed(policy, "can_inject") is True


@pytest.mark.parametrize(
    "conflict",
    [
        {"instrumentation_enabled": True, "trace_enabled": False},
        {
            "optimization": {"enabled": True, "auto_enqueue": True},
            "auto_optimize_enabled": False,
        },
    ],
    ids=("instrumentation", "auto_enqueue"),
)
def test_conflicting_enablement_aliases_fail_closed(conflict: dict[str, Any]) -> None:
    raw = _enabled_config()
    for key, value in conflict.items():
        if isinstance(value, dict) and isinstance(raw.get(key), dict):
            raw[key].update(value)
        else:
            raw[key] = value

    policy = _policy(_normalize(raw))
    if "trace_enabled" in conflict:
        assert _allowed(policy, "can_capture") is False
    else:
        assert _allowed(policy, "can_enqueue") is False
