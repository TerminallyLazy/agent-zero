"""A0 instance-id helper.

Spec ref: §4.1 — stable identifier for this A0 install, derived from the
realpath of the directory containing ``agent.py``.
"""

from __future__ import annotations

import hashlib
import os


def compute_instance_id(process_root: str | None = None) -> str:
    """Return a stable 12-hex-char id for this A0 install.

    Args:
        process_root: Optional path to the A0 process root (the directory
            containing ``agent.py``). When omitted, resolves the repo root
            relative to this file's location.

    Returns:
        First 12 hex characters of the SHA-256 of the realpath of
        ``process_root``.
    """
    if process_root is None:
        # helpers/instance.py lives at <repo>/usr/plugins/jcode_harness/helpers/
        # Four ".." segments climb back to <repo>, which is agent.py's parent.
        agent_py = os.path.realpath(
            os.path.join(
                os.path.dirname(__file__), "..", "..", "..", "..", "agent.py"
            )
        )
        # Sanity-check the depth math so a future refactor doesn't silently
        # change the resolved root and break instance-id stability.
        assert os.path.isfile(agent_py), (
            f"compute_instance_id: expected agent.py at {agent_py!r}; "
            "the relative-walk depth from helpers/instance.py to repo root "
            "may have changed."
        )
        process_root = os.path.dirname(agent_py)
    process_root = os.path.realpath(process_root)
    return hashlib.sha256(process_root.encode()).hexdigest()[:12]
