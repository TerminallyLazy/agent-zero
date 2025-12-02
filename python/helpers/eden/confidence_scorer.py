"""
Eden Clinical Inboxologist - Confidence Scorer

Calculates confidence scores for auto-handling inbox tasks.
Uses multiple weighted factors to determine if Eden should
handle a task autonomously or escalate to the physician.
"""

from dataclasses import dataclass
from typing import Optional
import re

from .models import (
    EdenTask,
    TaskCategory,
    TaskStatus,
    Patient,
    ConfidenceFactor,
    ConfidenceResult,
    Policy,
)


# Keywords that indicate higher risk
CRITICAL_KEYWORDS = [
    "malignancy", "cancer", "tumor", "metastatic", "biopsy positive",
    "critical", "urgent", "emergency", "stat", "abnormal",
    "chest pain", "shortness of breath", "suicidal", "overdose",
    "stroke", "heart attack", "MI", "CVA", "PE", "DVT",
]

# Keywords that suggest routine/low-risk
ROUTINE_KEYWORDS = [
    "normal", "within range", "stable", "routine", "annual",
    "follow-up", "refill", "records request", "scheduling",
]

# Controlled substances require extra scrutiny
CONTROLLED_SUBSTANCES = [
    "oxycodone", "hydrocodone", "morphine", "fentanyl", "codeine",
    "alprazolam", "xanax", "diazepam", "valium", "lorazepam", "ativan",
    "clonazepam", "klonopin", "adderall", "ritalin", "concerta",
    "vyvanse", "ambien", "zolpidem", "lunesta", "tramadol",
]


@dataclass
class PatientContext:
    """Context about a patient for scoring."""
    patient: Patient
    visit_count: int = 0
    last_visit_days_ago: Optional[int] = None
    has_flags: bool = False
    conditions: list[str] = None
    medications: list[str] = None
    age: Optional[int] = None

    def __post_init__(self):
        if self.conditions is None:
            self.conditions = []
        if self.medications is None:
            self.medications = []


class ConfidenceScorer:
    """
    Calculate confidence scores for Eden task handling.

    Scores are based on:
    - Task clarity (how clear-cut the task is)
    - Policy match (does an explicit policy apply?)
    - Patient history (do we know this patient well?)
    - Pattern match (have we seen similar cases?)
    - Risk level (what's the downside of error?)
    """

    def __init__(self, policies: list[Policy] = None):
        self.policies = policies or []

    def score(
        self,
        task: EdenTask,
        context: PatientContext,
    ) -> ConfidenceResult:
        """
        Calculate confidence score for a task.

        Args:
            task: The task to score
            context: Patient context information

        Returns:
            ConfidenceResult with score, factors, and reasoning
        """
        factors = []

        # Task Clarity (25%)
        clarity = self._score_task_clarity(task)
        factors.append(ConfidenceFactor(
            name="task_clarity",
            label="Task Clarity",
            score=clarity,
            weight=0.25,
        ))

        # Policy Match (25%)
        policy_score, matched_policy = self._score_policy_match(task, context)
        factors.append(ConfidenceFactor(
            name="policy_match",
            label="Policy Match",
            score=policy_score,
            weight=0.25,
            details=matched_policy,
        ))

        # Patient History (20%)
        history = self._score_patient_history(context)
        factors.append(ConfidenceFactor(
            name="patient_history",
            label="Patient History",
            score=history,
            weight=0.20,
        ))

        # Pattern Match (15%)
        pattern = self._score_pattern_match(task)
        factors.append(ConfidenceFactor(
            name="pattern_match",
            label="Pattern Match",
            score=pattern,
            weight=0.15,
        ))

        # Risk Level (15%) - inverted: higher risk = lower score
        risk, risk_reason = self._score_risk_level(task, context)
        factors.append(ConfidenceFactor(
            name="risk_level",
            label="Risk Level",
            score=risk,
            weight=0.15,
            details=risk_reason,
        ))

        # Calculate weighted score
        raw_score = sum(f.score * f.weight for f in factors)

        # Apply policy overrides
        final_score, override_reason = self._apply_overrides(raw_score, task, context)

        # Generate reasoning
        reasoning = self._generate_reasoning(
            task, context, factors, final_score,
            matched_policy, risk_reason, override_reason
        )

        return ConfidenceResult(
            score=final_score,
            factors=factors,
            reasoning=reasoning,
        )

    def _score_task_clarity(self, task: EdenTask) -> float:
        """Score how clear-cut the task is."""
        content = f"{task.title} {task.summary}".lower()

        # Category-based base scores
        base_scores = {
            TaskCategory.LAB: 0.85,  # Labs have clear normal/abnormal
            TaskCategory.SCHEDULING: 0.90,  # Scheduling is straightforward
            TaskCategory.BILLING: 0.80,  # Billing can be forwarded
            TaskCategory.REFILL: 0.75,  # Refills need medication check
            TaskCategory.MESSAGE: 0.60,  # Messages vary widely
            TaskCategory.REFERRAL: 0.65,
            TaskCategory.PRIOR_AUTH: 0.60,
            TaskCategory.INTERNAL: 0.70,
        }

        score = base_scores.get(task.category, 0.70)

        # Adjust based on content clarity
        if any(kw in content for kw in ROUTINE_KEYWORDS):
            score = min(1.0, score + 0.10)

        if any(kw in content for kw in CRITICAL_KEYWORDS):
            score = max(0.2, score - 0.30)

        return score

    def _score_policy_match(
        self,
        task: EdenTask,
        context: PatientContext,
    ) -> tuple[float, Optional[str]]:
        """Score policy match and return matched policy text."""
        if not self.policies:
            return 0.5, None  # No policies = neutral

        best_match = None
        best_score = 0.5

        content = f"{task.title} {task.summary}".lower()

        for policy in self.policies:
            if not policy.enabled:
                continue

            # Check if policy applies to this task type
            if policy.trigger and policy.trigger != task.category.value:
                continue

            # Simple keyword matching in policy text
            policy_lower = policy.text.lower()

            # Check for action keywords
            if "escalate" in policy_lower or "always review" in policy_lower:
                # Check if conditions match
                matches = self._check_policy_conditions(policy, task, context, content)
                if matches:
                    return 0.0, policy.text  # Force escalation

            if "auto" in policy_lower or "automatically" in policy_lower:
                matches = self._check_policy_conditions(policy, task, context, content)
                if matches:
                    best_match = policy.text
                    best_score = 0.95

            if "never" in policy_lower:
                matches = self._check_policy_conditions(policy, task, context, content)
                if matches:
                    return 0.0, policy.text  # Force review

        return best_score, best_match

    def _check_policy_conditions(
        self,
        policy: Policy,
        task: EdenTask,
        context: PatientContext,
        content: str,
    ) -> bool:
        """Check if policy conditions match the task."""
        policy_lower = policy.text.lower()

        # Look for specific triggers in policy text
        # "if A1C > 9" type conditions
        if "a1c" in policy_lower and "a1c" in content:
            # Try to extract threshold
            match = re.search(r'a1c\s*(?:>|above|over)\s*(\d+(?:\.\d+)?)', policy_lower)
            if match:
                threshold = float(match.group(1))
                # Try to find A1C value in content
                value_match = re.search(r'a1c[:\s]+(\d+(?:\.\d+)?)', content)
                if value_match:
                    value = float(value_match.group(1))
                    return value > threshold

        # Check for medication-specific policies
        for med in CONTROLLED_SUBSTANCES:
            if med in policy_lower and med in content:
                return True

        # Check for keyword matches
        if "normal" in policy_lower and "normal" in content:
            return True

        if "abnormal" in policy_lower and any(kw in content for kw in ["abnormal", "elevated", "high", "low"]):
            return True

        # Check category match
        category_keywords = {
            "lab": ["lab", "result", "test"],
            "refill": ["refill", "medication", "prescription"],
            "message": ["message", "portal", "patient question"],
        }

        for cat, keywords in category_keywords.items():
            if cat in policy_lower and task.category.value == cat:
                return True

        return False

    def _score_patient_history(self, context: PatientContext) -> float:
        """Score based on patient familiarity."""
        score = 0.5  # Base score

        # More visits = more confidence
        if context.visit_count >= 10:
            score += 0.30
        elif context.visit_count >= 5:
            score += 0.20
        elif context.visit_count >= 2:
            score += 0.10

        # Recent visit is good
        if context.last_visit_days_ago is not None:
            if context.last_visit_days_ago < 30:
                score += 0.15
            elif context.last_visit_days_ago < 90:
                score += 0.10
            elif context.last_visit_days_ago < 180:
                score += 0.05

        # Flags reduce confidence
        if context.has_flags:
            score -= 0.20

        return max(0.0, min(1.0, score))

    def _score_pattern_match(self, task: EdenTask) -> float:
        """Score based on how well this matches known patterns."""
        # This would ideally use ML/embeddings to match similar past tasks
        # For now, use category-based heuristics
        content = f"{task.title} {task.summary}".lower()

        score = 0.70  # Base score

        # Common patterns we've seen
        common_patterns = [
            ("normal", 0.15),
            ("routine", 0.15),
            ("refill", 0.10),
            ("follow up", 0.10),
            ("annual", 0.15),
            ("within range", 0.15),
        ]

        for pattern, boost in common_patterns:
            if pattern in content:
                score += boost

        # Uncommon patterns reduce score
        uncommon_patterns = [
            ("unusual", -0.15),
            ("concerning", -0.20),
            ("never seen", -0.25),
            ("first time", -0.10),
        ]

        for pattern, adjust in uncommon_patterns:
            if pattern in content:
                score += adjust

        return max(0.0, min(1.0, score))

    def _score_risk_level(
        self,
        task: EdenTask,
        context: PatientContext,
    ) -> tuple[float, Optional[str]]:
        """Score risk level (inverted: higher risk = lower score)."""
        content = f"{task.title} {task.summary}".lower()
        risk_factors = []

        # Check for critical keywords
        for keyword in CRITICAL_KEYWORDS:
            if keyword.lower() in content:
                risk_factors.append(f"Contains '{keyword}'")

        # Check for controlled substances in refills
        if task.category == TaskCategory.REFILL:
            for med in CONTROLLED_SUBSTANCES:
                if med.lower() in content:
                    risk_factors.append(f"Controlled substance: {med}")

        # Age-based risk
        if context.age and context.age > 75:
            risk_factors.append("Patient over 75")
        if context.age and context.age < 18:
            risk_factors.append("Pediatric patient")

        # Category-based risk
        if task.category == TaskCategory.PRIOR_AUTH:
            risk_factors.append("Prior auth requires review")

        # Calculate score (more risk factors = lower score)
        if len(risk_factors) >= 3:
            score = 0.20
        elif len(risk_factors) == 2:
            score = 0.40
        elif len(risk_factors) == 1:
            score = 0.60
        else:
            score = 0.95

        reason = "; ".join(risk_factors) if risk_factors else None
        return score, reason

    def _apply_overrides(
        self,
        raw_score: float,
        task: EdenTask,
        context: PatientContext,
    ) -> tuple[float, Optional[str]]:
        """Apply any hard overrides to the score."""
        content = f"{task.title} {task.summary}".lower()

        # Always escalate controlled substance refills
        if task.category == TaskCategory.REFILL:
            for med in CONTROLLED_SUBSTANCES:
                if med.lower() in content:
                    return 0.30, f"Controlled substance ({med}) requires physician review"

        # Always escalate critical keywords
        for keyword in ["malignancy", "cancer", "tumor", "metastatic"]:
            if keyword in content:
                return 0.0, f"'{keyword}' requires physician review"

        # Always escalate if "urgent" or "emergency"
        if "urgent" in content or "emergency" in content:
            return 0.20, "Marked as urgent/emergency"

        return raw_score, None

    def _generate_reasoning(
        self,
        task: EdenTask,
        context: PatientContext,
        factors: list[ConfidenceFactor],
        final_score: float,
        matched_policy: Optional[str],
        risk_reason: Optional[str],
        override_reason: Optional[str],
    ) -> list[str]:
        """Generate human-readable reasoning chain."""
        reasoning = []

        # Task summary
        reasoning.append(f"Task: {task.category.value.upper()} for {context.patient.name}")

        # Factor explanations
        for f in sorted(factors, key=lambda x: x.weight, reverse=True):
            if f.name == "task_clarity":
                if f.score > 0.8:
                    reasoning.append(f"✓ Clear-cut {task.category.value} with standard parameters")
                elif f.score > 0.6:
                    reasoning.append(f"⚠ {task.category.value.title()} requires some interpretation")
                else:
                    reasoning.append(f"⚠ Ambiguous task requiring clinical judgment")

            elif f.name == "policy_match":
                if f.score > 0.9 and matched_policy:
                    reasoning.append(f'✓ Matches policy: "{matched_policy}"')
                elif f.score < 0.3 and matched_policy:
                    reasoning.append(f'⚠ Policy requires review: "{matched_policy}"')
                else:
                    reasoning.append("⚠ No specific policy applies")

            elif f.name == "patient_history":
                if f.score > 0.8:
                    reasoning.append(f"✓ Patient well-known, {context.visit_count} visits, no flags")
                elif f.score > 0.5:
                    reasoning.append(f"⚠ Moderate patient history ({context.visit_count} visits)")
                else:
                    reasoning.append(f"⚠ Limited patient history ({context.visit_count} visits)")

            elif f.name == "risk_level":
                if f.score > 0.8:
                    reasoning.append(f"✓ Low risk: routine {task.category.value}")
                elif f.score > 0.5:
                    reasoning.append(f"⚠ Moderate risk factors present")
                else:
                    if risk_reason:
                        reasoning.append(f"⚠ Elevated risk: {risk_reason}")
                    else:
                        reasoning.append("⚠ High risk factors present")

        # Override explanation
        if override_reason:
            reasoning.append(f"⚠ Override: {override_reason}")

        # Final decision
        percentage = int(final_score * 100)
        if final_score >= 0.85:
            reasoning.append(f"→ Confidence: {percentage}% - Auto-handled")
        elif final_score >= 0.60:
            reasoning.append(f"→ Confidence: {percentage}% - Review recommended")
        else:
            reasoning.append(f"→ Confidence: {percentage}% - Escalated to physician")

        return reasoning


# Default scorer instance
_default_scorer: Optional[ConfidenceScorer] = None


def get_scorer(policies: list[Policy] = None) -> ConfidenceScorer:
    """Get or create the default confidence scorer."""
    global _default_scorer
    if _default_scorer is None or policies:
        _default_scorer = ConfidenceScorer(policies)
    return _default_scorer
