"""Pattern registry for Prompt Stomper.

Loads built-in patterns from data/default_patterns.json and custom
patterns from usr/prompt_stomper/custom_patterns.json.
Patterns are compiled once and cached.
"""

import json
import os
import re
from dataclasses import dataclass, field
from typing import Optional

from python.helpers import files


PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_PATTERNS_FILE = os.path.join(PLUGIN_DIR, "data", "default_patterns.json")
CUSTOM_PATTERNS_FILE = files.get_abs_path("usr", "prompt_stomper", "custom_patterns.json")


@dataclass
class Pattern:
    name: str
    category: str
    attack_type: str  # "direct" or "indirect"
    regex: str
    weight: float
    enabled: bool
    builtin: bool
    _compiled: Optional[re.Pattern] = field(default=None, repr=False, compare=False)

    @property
    def compiled(self) -> re.Pattern:
        if self._compiled is None:
            self._compiled = re.compile(self.regex)
        return self._compiled


class PatternRegistry:
    def __init__(self):
        self._patterns: list[Pattern] = []
        self._loaded = False

    def load(self):
        """Load built-in and custom patterns."""
        self._patterns = []

        # Load built-in patterns
        if os.path.exists(DEFAULT_PATTERNS_FILE):
            with open(DEFAULT_PATTERNS_FILE, "r") as f:
                data = json.load(f)
            for p in data.get("patterns", []):
                self._patterns.append(Pattern(
                    name=p["name"],
                    category=p["category"],
                    attack_type=p.get("attack_type", "direct"),
                    regex=p["regex"],
                    weight=p.get("weight", 0.5),
                    enabled=p.get("enabled", True),
                    builtin=True,
                ))

        # Load custom patterns
        if os.path.exists(CUSTOM_PATTERNS_FILE):
            with open(CUSTOM_PATTERNS_FILE, "r") as f:
                data = json.load(f)
            for p in data.get("patterns", []):
                self._patterns.append(Pattern(
                    name=p["name"],
                    category=p["category"],
                    attack_type=p.get("attack_type", "direct"),
                    regex=p["regex"],
                    weight=p.get("weight", 0.5),
                    enabled=p.get("enabled", True),
                    builtin=False,
                ))

        self._loaded = True

    def ensure_loaded(self):
        if not self._loaded:
            self.load()

    def get_patterns(self, attack_type: str | None = None, enabled_only: bool = True) -> list[Pattern]:
        self.ensure_loaded()
        patterns = self._patterns
        if enabled_only:
            patterns = [p for p in patterns if p.enabled]
        if attack_type:
            patterns = [p for p in patterns if p.attack_type == attack_type]
        return patterns

    def get_all_patterns(self) -> list[Pattern]:
        """Return all patterns including disabled, for the pattern editor."""
        self.ensure_loaded()
        return list(self._patterns)

    def add_custom_pattern(self, name: str, category: str, attack_type: str, regex: str, weight: float) -> Pattern:
        """Add a custom pattern and persist to disk."""
        # Validate regex compiles
        re.compile(regex)

        pattern = Pattern(
            name=name, category=category, attack_type=attack_type,
            regex=regex, weight=weight, enabled=True, builtin=False,
        )
        self._patterns.append(pattern)
        self._save_custom_patterns()
        return pattern

    def remove_custom_pattern(self, name: str) -> bool:
        """Remove a custom pattern by name. Returns True if found and removed."""
        before = len(self._patterns)
        self._patterns = [p for p in self._patterns if not (p.name == name and not p.builtin)]
        removed = len(self._patterns) < before
        if removed:
            self._save_custom_patterns()
        return removed

    def toggle_pattern(self, name: str, enabled: bool) -> bool:
        """Toggle a pattern's enabled state. Returns True if found."""
        self.ensure_loaded()
        for p in self._patterns:
            if p.name == name:
                p.enabled = enabled
                if not p.builtin:
                    self._save_custom_patterns()
                return True
        return False

    def _save_custom_patterns(self):
        """Persist custom patterns to disk."""
        custom = [p for p in self._patterns if not p.builtin]
        data = {
            "patterns": [
                {
                    "name": p.name,
                    "category": p.category,
                    "attack_type": p.attack_type,
                    "regex": p.regex,
                    "weight": p.weight,
                    "enabled": p.enabled,
                }
                for p in custom
            ]
        }
        os.makedirs(os.path.dirname(CUSTOM_PATTERNS_FILE), exist_ok=True)
        with open(CUSTOM_PATTERNS_FILE, "w") as f:
            json.dump(data, f, indent=2)

    def reload(self):
        """Force reload of all patterns."""
        self._loaded = False
        self.load()
