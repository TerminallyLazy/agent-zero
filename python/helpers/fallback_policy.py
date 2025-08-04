from enum import Enum
from typing import Dict, Any

class ErrorCategory(Enum):
    TRANSIENT = "transient"
    CAPABILITY_MISMATCH = "capability_mismatch"
    CONTEXT_MISSING = "context_missing"
    PERMANENT = "permanent"

DEFAULT_POLICIES = {
    ErrorCategory.TRANSIENT: ["retry"],
    ErrorCategory.CAPABILITY_MISMATCH: ["alternative_agent", "escalate"],
    ErrorCategory.CONTEXT_MISSING: ["clarify", "augment_context"],
    ErrorCategory.PERMANENT: ["fail", "human_notify"],
}

def decide_fallback(error_type: ErrorCategory, task: Dict[str, Any]) -> str:
    options = DEFAULT_POLICIES.get(error_type, [])
    return options[0] if options else "fail"