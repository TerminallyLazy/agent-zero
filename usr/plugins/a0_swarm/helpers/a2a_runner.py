"""
Run a delegate_parallel task on a remote A0 instance via FastA2A.
"""
from __future__ import annotations

import logging
from typing import Tuple, TYPE_CHECKING

from usr.plugins.a0_swarm.helpers.remotes import RemoteEndpoint

if TYPE_CHECKING:  # pragma: no cover
    from helpers.fasta2a_client import AgentConnection

logger = logging.getLogger(__name__)


def _client_module():
    # Lazy import so the rest of the plugin doesn't depend on the FastA2A
    # client at module-load time. Tests stub or skip this path entirely.
    from helpers import fasta2a_client as _m
    return _m


def _is_client_available(mod) -> bool:
    checker = getattr(mod, "is_client_available", None)
    if checker is None:
        checker = getattr(mod, "is_a2a_available", None)
    if checker is not None:
        return bool(checker())
    return bool(getattr(mod, "FASTA2A_CLIENT_AVAILABLE", False))


DEFAULT_POLL_INTERVAL_S = 2
DEFAULT_MAX_WAIT_S = 60 * 30   # 30 minutes per remote task


def is_available() -> bool:
    try:
        return _is_client_available(_client_module())
    except Exception:
        return False


async def open_connection(remote: RemoteEndpoint) -> "AgentConnection":
    mod = _client_module()
    if not _is_client_available(mod):
        raise RuntimeError("FastA2A client not available in this Agent Zero build.")
    return mod.AgentConnection(
        agent_url=remote.base_url,
        token=remote.auth_token or None,
    )


async def submit_task(remote: RemoteEndpoint, content: str) -> Tuple["AgentConnection", str, str]:
    """Send the task to the remote A0 and return (connection, task_id, context_id).

    The caller owns the connection and is responsible for closing it once
    polling/cancelling is no longer needed.
    """
    conn = await open_connection(remote)
    response = await conn.send_message(message=content)
    # Response shape: {"result": {"id": "<task_id>", "context_id": "...", ...}}
    result = (response or {}).get("result") or {}
    task_id = str(result.get("id") or "")
    context_id = str(result.get("context_id") or "")
    return conn, task_id, context_id


async def wait_for_result(conn: "AgentConnection", task_id: str,
                          poll_interval_s: int = DEFAULT_POLL_INTERVAL_S,
                          max_wait_s: int = DEFAULT_MAX_WAIT_S) -> Tuple[str, str]:
    """Poll the remote task until terminal. Return (state, result_text).

    state is one of "completed", "failed", "canceled", "timeout".
    """
    try:
        task_info = await conn.wait_for_completion(
            task_id=task_id,
            poll_interval=poll_interval_s,
            max_wait=max_wait_s,
        )
    except TimeoutError:
        return ("timeout", "")
    except Exception as e:
        logger.exception("A2A poll failed for task %s", task_id)
        return ("failed", str(e))

    task = (task_info or {}).get("result") or {}
    state = (task.get("status") or {}).get("state") or "unknown"
    artifacts = task.get("artifacts") or []
    text_parts: list[str] = []
    for art in artifacts:
        for p in art.get("parts") or []:
            if p.get("kind") == "text" and isinstance(p.get("text"), str):
                text_parts.append(p["text"])
    if not text_parts:
        msg = (task.get("status") or {}).get("message") or {}
        for p in (msg.get("parts") if isinstance(msg, dict) else []) or []:
            if p.get("kind") == "text" and isinstance(p.get("text"), str):
                text_parts.append(p["text"])
    return (state, "\n\n".join(text_parts).strip())


async def cancel_task(remote: RemoteEndpoint, task_id: str) -> bool:
    """Best-effort cancel of a remote task. Returns True if the call succeeded."""
    if not task_id:
        return False
    try:
        conn = await open_connection(remote)
    except Exception:
        return False
    try:
        await conn._a2a_client.cancel_task(task_id)  # type: ignore[attr-defined]
        return True
    except Exception as e:
        logger.warning("A2A cancel failed for task %s on %s: %s", task_id, remote.base_url, e)
        return False
    finally:
        try:
            await conn.close()
        except Exception:
            pass


async def send_intervention(remote: RemoteEndpoint, content: str, context_id: str = "") -> bool:
    """Send an additional message to a remote agent's existing context."""
    try:
        conn = await open_connection(remote)
    except Exception:
        return False
    try:
        await conn.send_message(message=content, context_id=context_id or None)
        return True
    except Exception as e:
        logger.warning("A2A intervention failed on %s: %s", remote.base_url, e)
        return False
    finally:
        try:
            await conn.close()
        except Exception:
            pass
