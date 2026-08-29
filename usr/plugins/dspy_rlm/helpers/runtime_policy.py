"""Independent, fail-closed runtime gates for the DSPy RLM plugin.

This module has no storage, scheduler, or framework side effects.  Callers may
use it on an already-normalized config or a sparse configuration mapping.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class RuntimePolicy:
    """Effective gates and diagnostic reasons for a single configuration.

    The plugin enablement switch is a common prerequisite.  Beyond that, capture,
    automatic enqueueing, manual optimization, prompt injection, and automatic
    promotion have independent settings.  In particular, `force` does not bypass
    any enablement or safety gate; it only skips sample/cooldown checks.
    """

    enabled: bool
    instrumentation_enabled: bool
    optimization_enabled: bool
    auto_enqueue_enabled: bool
    manual_optimization_enabled: bool
    injection_enabled: bool
    auto_promotion_enabled: bool
    prompt_optimization_enabled: bool
    prompt_capture_enabled: bool
    prompt_target_mode: str
    prompt_activation_mode: str
    dry_run_mode: bool
    dry_run_promote_only: bool
    min_samples_for_promotion: int
    diagnostics: tuple[str, ...] = ()

    @classmethod
    def from_config(cls, config: Mapping[str, Any] | None) -> "RuntimePolicy":
        # Import lazily to avoid a config -> policy import cycle and to make this
        # small policy object usable from isolated tooling.
        from usr.plugins.dspy_rlm.helpers.config import normalize_config

        normalized = normalize_config(dict(config) if isinstance(config, Mapping) else None)
        optimization = normalized.get("optimization", {})
        prompt = normalized.get("prompt", {})
        prompt_optimization = normalized.get("prompt_optimization", {})
        if not isinstance(optimization, dict):
            optimization = {}
        if not isinstance(prompt, dict):
            prompt = {}
        if not isinstance(prompt_optimization, dict):
            prompt_optimization = {}

        return cls(
            enabled=bool(normalized.get("enabled", False)),
            instrumentation_enabled=bool(normalized.get("instrumentation_enabled", False)),
            optimization_enabled=bool(optimization.get("enabled", False)),
            auto_enqueue_enabled=bool(optimization.get("auto_optimize", False)),
            manual_optimization_enabled=bool(optimization.get("manual_optimize", True)),
            injection_enabled=bool(prompt.get("inject_guidance", False)),
            auto_promotion_enabled=bool(optimization.get("auto_promote", False)),
            prompt_optimization_enabled=bool(prompt_optimization.get("enabled", False)),
            prompt_capture_enabled=bool(prompt_optimization.get("allow_prompt_capture", False)),
            prompt_target_mode=str(prompt_optimization.get("target_mode") or "guidance_overlay"),
            prompt_activation_mode=str(prompt_optimization.get("activation_mode") or "manual"),
            dry_run_mode=bool(optimization.get("dry_run_mode", False)),
            dry_run_promote_only=bool(optimization.get("dry_run_promote_only", False)),
            min_samples_for_promotion=int(optimization.get("min_samples_for_promotion", 1)),
            diagnostics=tuple(str(item) for item in normalized.get("diagnostics", []) if str(item)),
        )

    def reasons_for(
        self,
        capability: str,
        *,
        force: bool = False,
        sample_count: int | None = None,
        cooldown_elapsed: bool | None = None,
    ) -> tuple[str, ...]:
        """Return stable deny reasons for a capability.

        Supported capabilities are ``capture``, ``enqueue``, ``optimize``,
        ``inject``, ``optimize_prompt``, and ``auto_promote``. Unknown
        capabilities fail closed.
        """
        # Diagnostics describe migration/coercion problems.  The migration
        # already closes the affected gate, so they must not couple otherwise
        # independent capabilities such as capture and prompt injection.
        reasons: list[str] = []
        if not self.enabled:
            reasons.append("plugin_disabled")

        if capability == "capture":
            if not self.instrumentation_enabled:
                reasons.append("instrumentation_disabled")
        elif capability == "enqueue":
            if not self.optimization_enabled:
                reasons.append("optimization_disabled")
            if not self.auto_enqueue_enabled:
                reasons.append("auto_enqueue_disabled")
        elif capability == "optimize":
            if not self.optimization_enabled:
                reasons.append("optimization_disabled")
            if not self.manual_optimization_enabled:
                reasons.append("manual_optimization_disabled")
            if not force:
                if sample_count is not None and sample_count < self.min_samples_for_promotion:
                    reasons.append("insufficient_samples")
                if cooldown_elapsed is False:
                    reasons.append("cooldown_active")
        elif capability == "inject":
            if not self.injection_enabled:
                reasons.append("prompt_injection_disabled")
        elif capability == "auto_promote":
            if not self.optimization_enabled:
                reasons.append("optimization_disabled")
            if not self.auto_promotion_enabled:
                reasons.append("auto_promotion_disabled")
            if self.dry_run_mode or self.dry_run_promote_only:
                reasons.append("dry_run_promotion_blocked")
        elif capability == "optimize_prompt":
            if not self.optimization_enabled:
                reasons.append("optimization_disabled")
            if not self.prompt_optimization_enabled:
                reasons.append("prompt_optimization_disabled")
            if self.prompt_target_mode != "guidance_overlay" and not self.prompt_capture_enabled:
                reasons.append("prompt_capture_not_approved")
        else:
            reasons.append("unknown_capability")
        return tuple(dict.fromkeys(reasons))

    def can_capture(self) -> bool:
        return not self.reasons_for("capture")

    def can_enqueue(self) -> bool:
        return not self.reasons_for("enqueue")

    def can_optimize(
        self,
        *,
        force: bool = False,
        sample_count: int | None = None,
        cooldown_elapsed: bool | None = None,
    ) -> bool:
        return not self.reasons_for(
            "optimize",
            force=force,
            sample_count=sample_count,
            cooldown_elapsed=cooldown_elapsed,
        )

    def can_inject(self) -> bool:
        return not self.reasons_for("inject")

    def can_auto_promote(self) -> bool:
        return not self.reasons_for("auto_promote")
