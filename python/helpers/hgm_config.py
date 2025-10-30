# python/helpers/hgm_config.py
"""
HGM Configuration System

Provides configuration management for the Hierarchical Genetic Memory
self-improvement system with validation, defaults, and persistence.
"""
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional
import json
import os


@dataclass
class HGMConfig:
    """
    Configuration for HGM self-improvement system.

    This configuration controls all aspects of the self-improvement loop
    including exploration parameters, evaluation limits, and strategy selection.
    """

    # Core Parameters
    max_task_evals: int = 1000
    """Maximum number of task evaluations before stopping"""

    max_workers: int = 4
    """Maximum number of parallel workers for evaluation"""

    alpha: float = 0.5
    """Alpha parameter for expand/evaluate decision rule (n_task_evals**alpha)"""

    beta: float = 1.0
    """Beta parameter for Thompson Sampling"""

    cool_down: int = 5
    """Number of pseudo-counts for Thompson Sampling regularization"""

    # Strategy Selection Parameters
    strategy_weights: Dict[str, float] = field(default_factory=lambda: {
        'solve_empty_patches': 0.25,
        'solve_stochasticity': 0.25,
        'solve_contextlength': 0.25,
        'random_task': 0.25
    })
    """Weights for different diagnostic strategies"""

    empty_patch_threshold: float = 0.10
    """Minimum ratio of empty patches before triggering solve_empty_patches"""

    # Evaluation Parameters
    max_attempts_per_child: int = 3
    """Maximum attempts to generate a valid child node"""

    require_changes: bool = True
    """Whether to require actual git changes before accepting child"""

    timeout_seconds: int = 300
    """Timeout for subordinate agent execution (seconds)"""

    # Task Management
    tasks_per_evaluation: int = 1
    """Number of tasks to evaluate per evaluation operation"""

    min_evals_per_node: int = 3
    """Minimum evaluations before considering a node for expansion"""

    # Output and Logging
    save_logs: bool = True
    """Whether to save detailed logs"""

    log_level: str = "INFO"
    """Logging level: DEBUG, INFO, WARNING, ERROR"""

    checkpoint_frequency: int = 10
    """Save checkpoint every N iterations"""

    # Repository Configuration
    git_user_name: str = "HGM Agent"
    """Git user name for commits"""

    git_user_email: str = "hgm@agent-zero.local"
    """Git user email for commits"""

    # Advanced Parameters
    enable_pruning: bool = False
    """Whether to prune unpromising branches"""

    pruning_threshold: float = 0.1
    """Minimum mean utility to avoid pruning"""

    max_tree_depth: int = 20
    """Maximum tree depth before limiting expansion"""

    def __post_init__(self):
        """Validate configuration after initialization"""
        self.validate()

    def validate(self) -> None:
        """Validate configuration parameters"""
        errors = []

        # Validate ranges
        if self.max_task_evals <= 0:
            errors.append("max_task_evals must be positive")

        if self.max_workers <= 0:
            errors.append("max_workers must be positive")

        if not 0 <= self.alpha <= 2:
            errors.append("alpha must be between 0 and 2")

        if self.beta <= 0:
            errors.append("beta must be positive")

        if self.cool_down < 0:
            errors.append("cool_down must be non-negative")

        if not 0 <= self.empty_patch_threshold <= 1:
            errors.append("empty_patch_threshold must be between 0 and 1")

        if self.max_attempts_per_child <= 0:
            errors.append("max_attempts_per_child must be positive")

        if self.timeout_seconds <= 0:
            errors.append("timeout_seconds must be positive")

        if self.tasks_per_evaluation <= 0:
            errors.append("tasks_per_evaluation must be positive")

        # Validate strategy weights
        if abs(sum(self.strategy_weights.values()) - 1.0) > 0.01:
            errors.append(f"strategy_weights must sum to 1.0 (currently: {sum(self.strategy_weights.values())})")

        if errors:
            raise ValueError(f"Invalid HGM configuration:\n  " + "\n  ".join(errors))

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary"""
        return asdict(self)

    def save(self, filepath: str) -> None:
        """Save configuration to JSON file"""
        with open(filepath, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'HGMConfig':
        """Create configuration from dictionary"""
        # Filter out unknown fields
        valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered_data = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered_data)

    @classmethod
    def load(cls, filepath: str) -> 'HGMConfig':
        """Load configuration from JSON file"""
        with open(filepath, 'r') as f:
            data = json.load(f)
        return cls.from_dict(data)

    @classmethod
    def create_default(cls) -> 'HGMConfig':
        """Create configuration with default values"""
        return cls()

    @classmethod
    def create_fast(cls) -> 'HGMConfig':
        """Create configuration optimized for fast iteration"""
        return cls(
            max_task_evals=100,
            max_workers=1,
            alpha=0.3,  # Favor evaluation
            max_attempts_per_child=2,
            timeout_seconds=120,
            checkpoint_frequency=5
        )

    @classmethod
    def create_thorough(cls) -> 'HGMConfig':
        """Create configuration optimized for thorough exploration"""
        return cls(
            max_task_evals=5000,
            max_workers=8,
            alpha=0.7,  # Favor expansion
            cool_down=10,
            min_evals_per_node=5,
            max_attempts_per_child=5,
            enable_pruning=True
        )

    def update(self, **kwargs) -> 'HGMConfig':
        """Create new configuration with updated values"""
        current = self.to_dict()
        current.update(kwargs)
        return HGMConfig.from_dict(current)

    def __str__(self) -> str:
        """String representation"""
        return f"""HGMConfig:
  Core: max_evals={self.max_task_evals}, workers={self.max_workers}, alpha={self.alpha}
  Sampling: beta={self.beta}, cool_down={self.cool_down}
  Strategies: {self.strategy_weights}
  Evaluation: min_evals={self.min_evals_per_node}, tasks_per_eval={self.tasks_per_evaluation}
  Constraints: max_depth={self.max_tree_depth}, pruning={'enabled' if self.enable_pruning else 'disabled'}"""


def get_default_config() -> HGMConfig:
    """Get default HGM configuration"""
    return HGMConfig.create_default()


def load_config_from_env() -> HGMConfig:
    """Load configuration from environment variables"""
    config = HGMConfig.create_default()

    # Override with environment variables if present
    env_mappings = {
        'HGM_MAX_TASK_EVALS': ('max_task_evals', int),
        'HGM_MAX_WORKERS': ('max_workers', int),
        'HGM_ALPHA': ('alpha', float),
        'HGM_BETA': ('beta', float),
        'HGM_COOL_DOWN': ('cool_down', int),
        'HGM_TIMEOUT': ('timeout_seconds', int),
        'HGM_LOG_LEVEL': ('log_level', str),
    }

    updates = {}
    for env_var, (field_name, field_type) in env_mappings.items():
        value = os.environ.get(env_var)
        if value is not None:
            try:
                updates[field_name] = field_type(value)
            except ValueError:
                print(f"Warning: Invalid value for {env_var}: {value}")

    if updates:
        config = config.update(**updates)

    return config
