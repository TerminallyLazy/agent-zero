"""Canary token management for Prompt Stomper.

Generates a per-process canary token that is injected into the system
prompt and monitored in LLM output. If the token leaks, it indicates
the system prompt was exposed.
"""

import secrets
import string

# Per-process canary token (regenerated on server restart)
_canary_token: str | None = None


def get_canary_token() -> str:
    """Get or generate the per-process canary token."""
    global _canary_token
    if _canary_token is None:
        chars = string.ascii_letters + string.digits
        random_part = ''.join(secrets.choice(chars) for _ in range(12))
        _canary_token = f"STOMPER-{random_part}-VERIFY"
    return _canary_token
