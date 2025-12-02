"""
Eden Clinical Inboxologist - Policy Engine

Parses natural language policies into executable rules.
Learns and suggests refinements based on feedback patterns.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Any
import uuid
import json

from .models import Policy, EdenTask, TaskCategory


@dataclass
class PolicyCondition:
    """A single condition in a compiled policy rule."""
    field: str  # e.g., "test_name", "value", "category"
    operator: str  # e.g., "equals", "contains", "greater_than"
    value: Any
    negate: bool = False


@dataclass
class CompiledPolicy:
    """A policy compiled into executable form."""
    id: str
    original_text: str
    trigger: Optional[str]  # Task category that triggers this policy
    conditions: list[PolicyCondition]
    action: str  # "escalate", "auto_handle", "draft", "block"
    confidence_override: Optional[float] = None  # If set, overrides calculated confidence
    priority: int = 100  # Lower = higher priority

    def matches(self, task: EdenTask, context: dict = None) -> bool:
        """Check if this policy matches the given task."""
        context = context or {}

        # Check trigger (category match)
        if self.trigger and self.trigger != task.category.value:
            return False

        # Check all conditions
        for condition in self.conditions:
            if not self._check_condition(condition, task, context):
                return False

        return True

    def _check_condition(
        self,
        condition: PolicyCondition,
        task: EdenTask,
        context: dict,
    ) -> bool:
        """Check a single condition."""
        # Get the value to compare
        value = self._get_field_value(condition.field, task, context)
        if value is None:
            return condition.negate  # If field doesn't exist, condition fails

        # Apply operator
        result = self._apply_operator(condition.operator, value, condition.value)

        return not result if condition.negate else result

    def _get_field_value(
        self,
        field: str,
        task: EdenTask,
        context: dict,
    ) -> Any:
        """Extract field value from task or context."""
        # Task fields
        if field == "category":
            return task.category.value
        elif field == "title":
            return task.title.lower()
        elif field == "summary":
            return task.summary.lower()
        elif field == "content":
            return f"{task.title} {task.summary}".lower()
        elif field == "confidence":
            return task.confidence

        # Context fields
        elif field.startswith("patient."):
            subfield = field[8:]
            if subfield == "age":
                return context.get("patient_age")
            elif subfield == "visit_count":
                return context.get("visit_count")

        # Metadata fields (from raw_content)
        elif field.startswith("metadata."):
            subfield = field[9:]
            return task.raw_content.get(subfield)

        # Lab-specific
        elif field == "test_name":
            return task.raw_content.get("test_name", "").lower()
        elif field == "test_value":
            return task.raw_content.get("value")
        elif field == "abnormal":
            return task.raw_content.get("abnormal", False)

        # Medication-specific
        elif field == "medication_name":
            return task.raw_content.get("medication_name", "").lower()

        return context.get(field)

    def _apply_operator(self, operator: str, actual: Any, expected: Any) -> bool:
        """Apply comparison operator."""
        if operator == "equals":
            return actual == expected
        elif operator == "not_equals":
            return actual != expected
        elif operator == "contains":
            return str(expected).lower() in str(actual).lower()
        elif operator == "not_contains":
            return str(expected).lower() not in str(actual).lower()
        elif operator == "greater_than":
            try:
                return float(actual) > float(expected)
            except (ValueError, TypeError):
                return False
        elif operator == "less_than":
            try:
                return float(actual) < float(expected)
            except (ValueError, TypeError):
                return False
        elif operator == "matches":
            return bool(re.search(expected, str(actual), re.IGNORECASE))
        elif operator == "in_list":
            return actual in expected
        elif operator == "true":
            return bool(actual)
        elif operator == "false":
            return not bool(actual)

        return False


class PolicyParser:
    """Parse natural language policies into compiled rules."""

    # Patterns for extracting policy components
    PATTERNS = {
        # "always escalate X" / "escalate X always"
        "escalate": [
            r"(?:always\s+)?escalate\s+(?:if\s+)?(.+)",
            r"(.+)\s+(?:should|must)\s+(?:be\s+)?escalate[d]?",
            r"never\s+auto.+\s+(.+)",
        ],
        # "auto-send X" / "automatically handle X"
        "auto_handle": [
            r"auto(?:matically)?[\s-]+(?:send|handle|approve|process)\s+(.+)",
            r"(.+)\s+(?:can|should)\s+be\s+auto(?:matically)?[\s-]+(?:sent|handled|approved)",
        ],
        # "draft X" / "prepare X for review"
        "draft": [
            r"draft\s+(.+)",
            r"prepare\s+(.+)\s+for\s+review",
        ],
        # "never X" / "block X"
        "block": [
            r"never\s+(?:auto)?[\s-]*(?:send|handle)\s+(.+)",
            r"block\s+(.+)",
            r"(?:always\s+)?require\s+(?:review|approval)\s+for\s+(.+)",
        ],
    }

    # Category keywords
    CATEGORY_KEYWORDS = {
        "lab": ["lab", "result", "test", "a1c", "cholesterol", "cbc", "cmp", "lipid"],
        "refill": ["refill", "medication", "prescription", "rx", "med"],
        "message": ["message", "portal", "patient question", "inquiry"],
        "referral": ["referral", "refer", "specialist"],
        "prior_auth": ["prior auth", "authorization", "pa"],
        "scheduling": ["schedule", "appointment", "visit"],
        "billing": ["billing", "insurance", "claim"],
    }

    # Condition patterns
    CONDITION_PATTERNS = [
        # "if X > Y" / "X above Y" / "X greater than Y"
        (r"(?:if\s+)?(\w+)\s*(?:>|above|over|greater\s+than|exceeds?)\s*(\d+(?:\.\d+)?)",
         lambda m: PolicyCondition(m.group(1).lower(), "greater_than", float(m.group(2)))),

        # "if X < Y" / "X below Y"
        (r"(?:if\s+)?(\w+)\s*(?:<|below|under|less\s+than)\s*(\d+(?:\.\d+)?)",
         lambda m: PolicyCondition(m.group(1).lower(), "less_than", float(m.group(2)))),

        # "contains X" / "mentioning X"
        (r"(?:containing?|mentioning?|with)\s+['\"]?(\w+)['\"]?",
         lambda m: PolicyCondition("content", "contains", m.group(1))),

        # "normal X" / "X is normal"
        (r"normal\s+(\w+)|(\w+)\s+(?:is|are)\s+normal",
         lambda m: PolicyCondition("content", "contains", "normal")),

        # "abnormal X"
        (r"abnormal\s+(\w+)|(\w+)\s+(?:is|are)\s+abnormal",
         lambda m: PolicyCondition("abnormal", "true", True)),

        # "for stable patients"
        (r"(?:for\s+)?stable\s+patients?",
         lambda m: PolicyCondition("content", "not_contains", "unstable")),

        # "who have had a visit in the last X months"
        (r"(?:who\s+)?(?:have\s+)?(?:had\s+)?(?:a\s+)?visit\s+in\s+(?:the\s+)?last\s+(\d+)\s+months?",
         lambda m: PolicyCondition("patient.last_visit_months", "less_than", int(m.group(1)))),

        # Controlled substances
        (r"controlled\s+substance",
         lambda m: PolicyCondition("metadata.is_controlled", "true", True)),
    ]

    def parse(self, text: str) -> Optional[CompiledPolicy]:
        """
        Parse a natural language policy into a compiled rule.

        Args:
            text: Natural language policy text

        Returns:
            CompiledPolicy if parsing successful, None otherwise
        """
        text_lower = text.lower().strip()

        # Determine action
        action = None
        matched_text = None

        for action_type, patterns in self.PATTERNS.items():
            for pattern in patterns:
                match = re.search(pattern, text_lower)
                if match:
                    action = action_type
                    matched_text = match.group(1) if match.groups() else text_lower
                    break
            if action:
                break

        if not action:
            # Default to draft if no clear action
            action = "draft"
            matched_text = text_lower

        # Determine trigger category
        trigger = None
        for category, keywords in self.CATEGORY_KEYWORDS.items():
            for keyword in keywords:
                if keyword in text_lower:
                    trigger = category
                    break
            if trigger:
                break

        # Extract conditions
        conditions = []
        for pattern, builder in self.CONDITION_PATTERNS:
            match = re.search(pattern, text_lower)
            if match:
                try:
                    condition = builder(match)
                    conditions.append(condition)
                except:
                    pass

        # Set confidence override based on action
        confidence_override = None
        if action == "escalate":
            confidence_override = 0.0
        elif action == "auto_handle":
            confidence_override = 0.95
        elif action == "block":
            confidence_override = 0.0

        return CompiledPolicy(
            id=str(uuid.uuid4()),
            original_text=text,
            trigger=trigger,
            conditions=conditions,
            action=action,
            confidence_override=confidence_override,
        )


class PolicyEngine:
    """
    Engine for evaluating and managing policies.

    Features:
    - Parse natural language policies
    - Evaluate policies against tasks
    - Track feedback and suggest refinements
    """

    def __init__(self):
        self.parser = PolicyParser()
        self.policies: list[CompiledPolicy] = []
        self.feedback_log: list[dict] = []

    def add_policy(self, text: str) -> Optional[CompiledPolicy]:
        """Add a policy from natural language text."""
        policy = self.parser.parse(text)
        if policy:
            self.policies.append(policy)
        return policy

    def add_policies(self, texts: list[str]) -> list[CompiledPolicy]:
        """Add multiple policies."""
        return [p for text in texts if (p := self.add_policy(text))]

    def remove_policy(self, policy_id: str) -> bool:
        """Remove a policy by ID."""
        for i, policy in enumerate(self.policies):
            if policy.id == policy_id:
                self.policies.pop(i)
                return True
        return False

    def evaluate(
        self,
        task: EdenTask,
        context: dict = None,
    ) -> tuple[Optional[str], Optional[float], Optional[str]]:
        """
        Evaluate policies for a task.

        Args:
            task: The task to evaluate
            context: Additional context (patient info, etc.)

        Returns:
            Tuple of (action, confidence_override, matched_policy_text)
        """
        context = context or {}

        # Sort by priority (lower = higher priority)
        sorted_policies = sorted(self.policies, key=lambda p: p.priority)

        for policy in sorted_policies:
            if policy.matches(task, context):
                return (
                    policy.action,
                    policy.confidence_override,
                    policy.original_text,
                )

        return None, None, None

    def record_feedback(
        self,
        task_id: str,
        matched_policy_id: Optional[str],
        action_taken: str,
        physician_action: str,
        timestamp: datetime = None,
    ):
        """
        Record feedback on policy application.

        Args:
            task_id: ID of the task
            matched_policy_id: ID of policy that matched (if any)
            action_taken: What Eden did
            physician_action: What physician did (approve, reject, edit)
            timestamp: When this happened
        """
        self.feedback_log.append({
            "task_id": task_id,
            "policy_id": matched_policy_id,
            "eden_action": action_taken,
            "physician_action": physician_action,
            "timestamp": (timestamp or datetime.now()).isoformat(),
            "agreed": action_taken == physician_action,
        })

    def suggest_refinements(self) -> list[str]:
        """
        Analyze feedback and suggest policy refinements.

        Returns:
            List of suggested policy changes in natural language
        """
        suggestions = []

        if len(self.feedback_log) < 10:
            return ["Not enough feedback to suggest refinements (need 10+ interactions)"]

        # Count disagreements per policy
        policy_disagreements = {}
        total_disagreements = 0

        for entry in self.feedback_log:
            if not entry["agreed"]:
                total_disagreements += 1
                policy_id = entry.get("policy_id", "no_policy")
                policy_disagreements[policy_id] = policy_disagreements.get(policy_id, 0) + 1

        if total_disagreements == 0:
            suggestions.append("Policies are performing well - no refinements needed")
            return suggestions

        # Find problematic policies
        for policy_id, count in policy_disagreements.items():
            if policy_id == "no_policy":
                if count >= 3:
                    suggestions.append(
                        f"Consider adding a policy: {count} tasks without policy match "
                        "were overridden by physician"
                    )
            else:
                policy = next((p for p in self.policies if p.id == policy_id), None)
                if policy and count >= 2:
                    suggestions.append(
                        f'Policy "{policy.original_text}" has been overridden {count} times. '
                        "Consider revising or removing it."
                    )

        # Check for patterns in overrides
        override_patterns = {}
        for entry in self.feedback_log:
            if not entry["agreed"]:
                key = (entry["eden_action"], entry["physician_action"])
                override_patterns[key] = override_patterns.get(key, 0) + 1

        for (eden, physician), count in override_patterns.items():
            if count >= 3:
                suggestions.append(
                    f"Eden {eden}s but physician {physician}s in {count} cases. "
                    f"Consider adding a policy to handle this pattern."
                )

        return suggestions

    def export_policies(self) -> list[dict]:
        """Export policies for persistence."""
        return [
            {
                "id": p.id,
                "text": p.original_text,
                "trigger": p.trigger,
                "action": p.action,
                "confidence_override": p.confidence_override,
                "conditions": [
                    {"field": c.field, "operator": c.operator, "value": c.value}
                    for c in p.conditions
                ],
            }
            for p in self.policies
        ]

    def import_policies(self, data: list[dict]):
        """Import policies from persistence."""
        self.policies = []
        for item in data:
            policy = CompiledPolicy(
                id=item["id"],
                original_text=item["text"],
                trigger=item.get("trigger"),
                conditions=[
                    PolicyCondition(
                        field=c["field"],
                        operator=c["operator"],
                        value=c["value"],
                    )
                    for c in item.get("conditions", [])
                ],
                action=item["action"],
                confidence_override=item.get("confidence_override"),
            )
            self.policies.append(policy)


# Default engine instance
_default_engine: Optional[PolicyEngine] = None


def get_engine() -> PolicyEngine:
    """Get or create the default policy engine."""
    global _default_engine
    if _default_engine is None:
        _default_engine = PolicyEngine()
    return _default_engine
