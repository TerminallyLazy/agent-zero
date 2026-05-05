"""Persistent ``client_instance_id`` store.

Spec ref: §7.1 — each A0 context owns a stable UUID4 ``client_instance_id``
that is reused across daemon reconnects and persisted under
``<runtime>/sessions/<a0_ctx_id>.json``.
"""

from __future__ import annotations

import json
import sys
import uuid

from usr.plugins.jcode_harness.helpers.paths import client_instance_persist_path


def get_or_create_client_instance_id(
    a0_ctx_id: str, instance_id: str | None = None
) -> str:
    """Return the persisted ``client_instance_id`` for ``a0_ctx_id``.

    If no record exists (or the existing record is corrupt/unreadable), mints
    a fresh UUID4, writes it at 0600, and returns it.
    """
    p = client_instance_persist_path(a0_ctx_id, instance_id)
    if p.exists():
        try:
            data = json.loads(p.read_text())
            cid = data["client_instance_id"]
            if not isinstance(cid, str) or not cid:
                raise ValueError("client_instance_id missing or empty")
            return cid
        except (json.JSONDecodeError, KeyError, ValueError, OSError) as exc:
            # Corrupted persistence file — log and fall through to overwrite.
            # TODO(jcode_harness): wire to A0 logger when integration lands.
            print(
                f"[jcode_harness.persistence] corrupt {p} ({exc!r}); "
                "regenerating client_instance_id",
                file=sys.stderr,
            )
    cid = str(uuid.uuid4())
    p.write_text(json.dumps({"client_instance_id": cid}))
    p.chmod(0o600)
    return cid
