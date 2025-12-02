"""
Eden Clinical Inboxologist - Data Models
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class TaskCategory(Enum):
    """Categories of clinical inbox tasks."""
    LAB = "lab"
    MESSAGE = "message"
    REFILL = "refill"
    REFERRAL = "referral"
    PRIOR_AUTH = "prior_auth"
    SCHEDULING = "scheduling"
    BILLING = "billing"
    INTERNAL = "internal"


class TaskStatus(Enum):
    """Status of a task in the Eden workflow."""
    PENDING = "pending"
    AUTO_HANDLED = "auto_handled"
    NEEDS_REVIEW = "needs_review"
    ESCALATED = "escalated"
    COMPLETED = "completed"
    REJECTED = "rejected"


@dataclass
class Patient:
    """Patient information."""
    id: str
    name: str
    dob: str
    initials: str = ""
    mrn: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None

    def __post_init__(self):
        if not self.initials and self.name:
            parts = self.name.split()
            self.initials = "".join(p[0].upper() for p in parts[:2])


@dataclass
class ConfidenceFactor:
    """A factor contributing to confidence score."""
    name: str
    label: str
    score: float  # 0.0 to 1.0
    weight: float = 0.2
    details: Optional[str] = None


@dataclass
class ConfidenceResult:
    """Result of confidence calculation."""
    score: float  # 0.0 to 1.0 (displayed as percentage)
    factors: list[ConfidenceFactor] = field(default_factory=list)
    reasoning: list[str] = field(default_factory=list)

    @property
    def percentage(self) -> int:
        return int(self.score * 100)

    @property
    def should_auto_handle(self) -> bool:
        return self.score >= 0.85

    @property
    def should_escalate(self) -> bool:
        return self.score < 0.60


@dataclass
class EdenTask:
    """A single task in the clinical inbox."""
    id: str
    category: TaskCategory
    status: TaskStatus
    confidence: float  # 0.0 to 1.0

    # Source
    emr_id: str
    patient: Patient
    received_at: datetime

    # Content
    title: str
    summary: str
    raw_content: dict = field(default_factory=dict)

    # Action
    proposed_action: Optional[str] = None
    draft_content: Optional[str] = None
    reasoning: list[str] = field(default_factory=list)
    confidence_factors: list[ConfidenceFactor] = field(default_factory=list)

    # Resolution
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None  # 'eden' | 'physician' | physician_id
    final_action: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "category": self.category.value,
            "status": self.status.value,
            "confidence": int(self.confidence * 100),
            "emr_id": self.emr_id,
            "patient": {
                "id": self.patient.id,
                "name": self.patient.name,
                "initials": self.patient.initials,
            },
            "receivedAt": self.received_at.isoformat() if self.received_at else None,
            "title": self.title,
            "summary": self.summary,
            "proposedAction": self.proposed_action,
            "draftContent": self.draft_content,
            "reasoning": self.reasoning,
            "confidenceFactors": [
                {
                    "name": f.name,
                    "label": f.label,
                    "score": f.score,
                }
                for f in self.confidence_factors
            ],
            "resolvedAt": self.resolved_at.isoformat() if self.resolved_at else None,
            "resolvedBy": self.resolved_by,
        }


@dataclass
class Cluster:
    """A group of tasks related to a single patient."""
    id: str
    patient: Patient
    tasks: list[EdenTask] = field(default_factory=list)
    reasoning: list[str] = field(default_factory=list)

    @property
    def avg_confidence(self) -> float:
        if not self.tasks:
            return 0.0
        return sum(t.confidence for t in self.tasks) / len(self.tasks)

    @property
    def priority(self) -> int:
        """Lower number = higher priority."""
        # Escalated tasks get highest priority
        if any(t.status == TaskStatus.ESCALATED for t in self.tasks):
            return 0
        # Needs review next
        if any(t.status == TaskStatus.NEEDS_REVIEW for t in self.tasks):
            return 1
        # Pending
        if any(t.status == TaskStatus.PENDING for t in self.tasks):
            return 2
        # Auto-handled
        return 3

    @property
    def needs_attention(self) -> bool:
        return any(
            t.status in [TaskStatus.NEEDS_REVIEW, TaskStatus.ESCALATED, TaskStatus.PENDING]
            for t in self.tasks
        )

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "patient": {
                "id": self.patient.id,
                "name": self.patient.name,
                "initials": self.patient.initials,
                "dob": self.patient.dob,
            },
            "tasks": [t.to_dict() for t in self.tasks],
            "avgConfidence": int(self.avg_confidence * 100),
            "priority": self.priority,
            "reasoning": self.reasoning,
            "needsAttention": self.needs_attention,
        }


@dataclass
class Policy:
    """A physician-defined policy for Eden's behavior."""
    id: str
    text: str  # Natural language policy
    created_at: datetime
    enabled: bool = True

    # Compiled rule (parsed from natural language)
    trigger: Optional[str] = None  # e.g., "lab_result", "refill", "message"
    conditions: list[dict] = field(default_factory=list)
    action: Optional[str] = None  # e.g., "escalate", "auto_send", "draft"
    confidence_override: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "text": self.text,
            "createdAt": self.created_at.isoformat(),
            "enabled": self.enabled,
            "trigger": self.trigger,
            "conditions": self.conditions,
            "action": self.action,
        }


@dataclass
class DailySummary:
    """Daily digest of Eden's activity."""
    date: datetime
    auto_handled: int = 0
    pending_review: int = 0
    escalated: int = 0
    completed: int = 0
    total: int = 0

    by_category: dict[str, int] = field(default_factory=dict)
    recent_auto_handled: list[EdenTask] = field(default_factory=list)
    pending_tasks: list[EdenTask] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "date": self.date.isoformat(),
            "stats": {
                "autoHandled": self.auto_handled,
                "pending": self.pending_review,
                "escalated": self.escalated,
                "completed": self.completed,
                "total": self.total,
            },
            "byCategory": self.by_category,
            "recentAutoHandled": [t.to_dict() for t in self.recent_auto_handled],
            "pendingTasks": [t.to_dict() for t in self.pending_tasks],
        }
