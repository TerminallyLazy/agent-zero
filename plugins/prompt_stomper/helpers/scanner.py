"""Core detection engine for Prompt Stomper.

Scans text using regex patterns, structural heuristics, and keyword
density analysis. Returns a ScanResult with severity classification.
"""

import json
import os
import re
from dataclasses import dataclass, field

from plugins.prompt_stomper.helpers.patterns import PatternRegistry, Pattern


PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEVERITY_FILE = os.path.join(PLUGIN_DIR, "data", "severity_levels.json")

# Default severity thresholds
DEFAULT_THRESHOLDS = [
    {"level": 0, "name": "safe",   "min_score": 0.0, "max_score": 0.2, "action": "pass"},
    {"level": 1, "name": "low",    "min_score": 0.2, "max_score": 0.5, "action": "log"},
    {"level": 2, "name": "medium", "min_score": 0.5, "max_score": 0.8, "action": "warn"},
    {"level": 3, "name": "high",   "min_score": 0.8, "max_score": 1.0, "action": "block"},
]

# Heuristic: keywords that indicate injection attempts
INJECTION_KEYWORDS = [
    "ignore", "disregard", "forget", "override", "bypass", "pretend",
    "jailbreak", "dan ", "system prompt", "unrestricted", "unfiltered",
    "no rules", "no restrictions", "no limits", "no censorship",
    "sudo", "admin mode", "developer mode", "god mode",
]


@dataclass
class MatchDetail:
    pattern_name: str
    category: str
    weight: float
    matched_text: str


@dataclass
class ScanResult:
    is_attack: bool
    severity: int            # 0-3
    severity_name: str       # "safe", "low", "medium", "high"
    score: float             # 0.0-1.0
    action: str              # "pass", "log", "warn", "block"
    attack_type: str | None  # "direct", "indirect", or None
    categories: list[str] = field(default_factory=list)
    matched_patterns: list[MatchDetail] = field(default_factory=list)
    text_snippet: str = ""

    def to_dict(self) -> dict:
        return {
            "is_attack": self.is_attack,
            "severity": self.severity,
            "severity_name": self.severity_name,
            "score": round(self.score, 3),
            "action": self.action,
            "attack_type": self.attack_type,
            "categories": self.categories,
            "matched_patterns": [
                {"name": m.pattern_name, "category": m.category, "weight": m.weight, "match": m.matched_text[:100]}
                for m in self.matched_patterns
            ],
            "text_snippet": self.text_snippet[:200],
        }


class Scanner:
    def __init__(self, patterns: PatternRegistry, settings: dict | None = None):
        self.patterns = patterns
        self.settings = settings or {}
        self._thresholds = self._load_thresholds()

    def _load_thresholds(self) -> list[dict]:
        if os.path.exists(SEVERITY_FILE):
            with open(SEVERITY_FILE, "r") as f:
                data = json.load(f)
            return data.get("levels", DEFAULT_THRESHOLDS)
        return DEFAULT_THRESHOLDS

    def scan_user_prompt(self, text: str) -> ScanResult:
        """Scan user-submitted text for direct injection attacks."""
        return self._scan(text, attack_type="direct")

    def scan_document(self, text: str, source: str = "") -> ScanResult:
        """Scan third-party content for indirect injection attacks."""
        return self._scan(text, attack_type="indirect")

    def scan_auto(self, text: str) -> ScanResult:
        """Scan text for both direct and indirect attacks, return worst result."""
        direct = self._scan(text, attack_type="direct")
        indirect = self._scan(text, attack_type="indirect")
        return direct if direct.score >= indirect.score else indirect

    def _scan(self, text: str, attack_type: str) -> ScanResult:
        if not text or not text.strip():
            return self._safe_result()

        matches: list[MatchDetail] = []
        categories_seen: set[str] = set()

        # 1. Pattern matching
        patterns = self.patterns.get_patterns(attack_type=attack_type, enabled_only=True)
        pattern_score = self._match_patterns(text, patterns, matches, categories_seen)

        # 2. Structural heuristics
        heuristic_score = self._structural_heuristics(text, attack_type)

        # 3. Keyword density
        density_score = self._keyword_density(text)

        # Aggregate: weighted combination, clamped to [0.0, 1.0]
        # Pattern matches are the primary signal (60%), heuristics (25%), density (15%)
        raw_score = (pattern_score * 0.6) + (heuristic_score * 0.25) + (density_score * 0.15)
        score = max(0.0, min(1.0, raw_score))

        # Determine severity from score
        severity_info = self._severity_from_score(score)

        # Build snippet
        snippet = ""
        if matches:
            snippet = matches[0].matched_text[:200]
        elif text:
            snippet = text[:200]

        return ScanResult(
            is_attack=severity_info["level"] >= 2,  # medium+ is considered an attack
            severity=severity_info["level"],
            severity_name=severity_info["name"],
            score=score,
            action=severity_info["action"],
            attack_type=attack_type if severity_info["level"] > 0 else None,
            categories=sorted(categories_seen),
            matched_patterns=matches,
            text_snippet=snippet,
        )

    def _match_patterns(
        self, text: str, patterns: list[Pattern],
        matches: list[MatchDetail], categories: set[str]
    ) -> float:
        """Match text against patterns. Returns cumulative score (can exceed 1.0)."""
        total = 0.0
        for pattern in patterns:
            try:
                match = pattern.compiled.search(text)
                if match:
                    matched_text = match.group(0)
                    matches.append(MatchDetail(
                        pattern_name=pattern.name,
                        category=pattern.category,
                        weight=pattern.weight,
                        matched_text=matched_text,
                    ))
                    categories.add(pattern.category)
                    total += pattern.weight
            except re.error:
                continue
        # Normalize: if total > 1.0, cap at 1.0
        return min(1.0, total)

    def _structural_heuristics(self, text: str, attack_type: str) -> float:
        """Detect structural patterns that indicate injection."""
        score = 0.0
        text_lower = text.lower()

        if attack_type == "direct":
            # Check for conversation mockup structure (multiple fake turns)
            turn_pattern = re.compile(r'(?m)^(User|Human|Assistant|AI|System|Bot)\s*:', re.IGNORECASE)
            turn_count = len(turn_pattern.findall(text))
            if turn_count >= 3:
                score += 0.6
            elif turn_count >= 2:
                score += 0.3

            # Check for large base64-looking blocks
            b64_pattern = re.compile(r'[A-Za-z0-9+/]{40,}={0,2}')
            if b64_pattern.search(text):
                score += 0.3

            # Check for instruction delimiters
            if any(delim in text for delim in ["---", "===", "***"]):
                delim_with_instruction = re.compile(
                    r'[-=*]{3,}\s*(new|real|actual|updated|true)\s+(instructions?|prompt|system)',
                    re.IGNORECASE
                )
                if delim_with_instruction.search(text):
                    score += 0.5

        elif attack_type == "indirect":
            # Check for hidden HTML comments with instructions
            if re.search(r'<!--\s*(instruction|system|override|ignore|execute)', text_lower):
                score += 0.5

            # Check for invisible unicode characters (zero-width spaces, etc.)
            invisible_chars = ['\u200b', '\u200c', '\u200d', '\u2060', '\ufeff']
            invisible_count = sum(text.count(c) for c in invisible_chars)
            if invisible_count > 5:
                score += 0.4

            # Check for markdown image exfiltration
            if re.search(r'!\[.*?\]\(https?://.*?\?.*?(prompt|key|secret|password|token)', text_lower):
                score += 0.7

        return min(1.0, score)

    def _keyword_density(self, text: str) -> float:
        """Score based on density of injection-related keywords."""
        if not text:
            return 0.0

        text_lower = text.lower()
        word_count = max(1, len(text_lower.split()))
        keyword_hits = sum(1 for kw in INJECTION_KEYWORDS if kw in text_lower)

        # Density = hits / total words, scaled up
        # Short messages with many keywords score higher
        density = keyword_hits / word_count
        scaled = min(1.0, density * 10)  # 10% keyword density = 1.0

        return scaled

    def _severity_from_score(self, score: float) -> dict:
        for level in reversed(self._thresholds):
            if score >= level["min_score"]:
                return level
        return self._thresholds[0]

    def _safe_result(self) -> ScanResult:
        return ScanResult(
            is_attack=False, severity=0, severity_name="safe",
            score=0.0, action="pass", attack_type=None,
        )


# Module-level singleton
_registry = PatternRegistry()
_scanner = Scanner(_registry)


def get_scanner() -> Scanner:
    """Get the module-level scanner singleton."""
    _registry.ensure_loaded()
    return _scanner


def get_registry() -> PatternRegistry:
    """Get the module-level pattern registry."""
    _registry.ensure_loaded()
    return _registry
