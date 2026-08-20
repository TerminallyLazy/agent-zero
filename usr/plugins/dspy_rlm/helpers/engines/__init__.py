"""Candidate-engine contracts for the DSPy RLM optimizer.

Engines return a validated :class:`GuidanceArtifact` only after their own declared
work has succeeded.  The common result intentionally carries reproducibility data
outside the artifact because prompt-renderable artifacts have a strict schema.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from ..guidance import GuidanceArtifact


@dataclass(frozen=True)
class EngineBudget:
    """Hard, local limits for a single candidate-engine invocation."""

    max_examples: int = 32
    max_compile_seconds: float = 60.0
    max_cost_usd: float = 0.0
    max_steps: int = 3
    num_threads: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.max_examples, int) or isinstance(self.max_examples, bool) or self.max_examples < 1:
            raise ValueError("max_examples must be a positive integer")
        if not isinstance(self.max_compile_seconds, (int, float)) or isinstance(self.max_compile_seconds, bool) or self.max_compile_seconds <= 0:
            raise ValueError("max_compile_seconds must be positive")
        if not isinstance(self.max_cost_usd, (int, float)) or isinstance(self.max_cost_usd, bool) or self.max_cost_usd < 0:
            raise ValueError("max_cost_usd must be non-negative")
        if not isinstance(self.max_steps, int) or isinstance(self.max_steps, bool) or self.max_steps < 1:
            raise ValueError("max_steps must be a positive integer")
        if not isinstance(self.num_threads, int) or isinstance(self.num_threads, bool) or self.num_threads < 1:
            raise ValueError("num_threads must be a positive integer")

    def to_mapping(self) -> dict[str, Any]:
        return {
            "max_examples": self.max_examples,
            "max_compile_seconds": float(self.max_compile_seconds),
            "max_cost_usd": float(self.max_cost_usd),
            "max_steps": self.max_steps,
            "num_threads": self.num_threads,
        }


@dataclass(frozen=True)
class EngineResult:
    """Outcome of one bounded engine attempt.

    ``artifact`` is present only for ``succeeded``.  Consequently callers cannot
    accidentally persist or promote a failed/unavailable GEPA attempt as a GEPA
    candidate.
    """

    status: str
    engine_kind: str
    artifact: GuidanceArtifact | None = None
    reproducibility: Mapping[str, Any] = field(default_factory=dict)
    error: str = ""
    compiled_program: Any = None

    @property
    def succeeded(self) -> bool:
        return self.status == "succeeded" and self.artifact is not None

    def to_mapping(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "engine": self.engine_kind,
            "artifact": self.artifact.to_mapping() if self.artifact else None,
            "reproducibility": dict(self.reproducibility),
            "error": self.error,
        }


from .heuristic import HeuristicEngine
from .gepa import GepaEngine

__all__ = ["EngineBudget", "EngineResult", "GepaEngine", "HeuristicEngine"]
