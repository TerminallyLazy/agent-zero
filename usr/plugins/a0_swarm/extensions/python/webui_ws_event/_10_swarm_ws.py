from __future__ import annotations
import asyncio
import weakref
from helpers.extension import Extension
from usr.plugins.a0_swarm.helpers.registry import SwarmRegistry

# sid -> (loop, parent_ctx_id, push_cb)
_subs: dict[str, tuple] = {}


def _make_push_cb(instance, sid: str, parent: str):
    """Build push_cb that uses a weakref to the WsWebui instance, so the
    callback self-evicts from the registry if the instance is garbage-collected
    (e.g. on dev-reload or handler re-instantiation). Without this the
    SwarmRegistry._subscribers list would grow unbounded with stale closures.
    """
    inst_ref = weakref.ref(instance) if not isinstance(instance, type(None)) else None

    async def push_cb():
        inst = inst_ref() if inst_ref is not None else None
        if inst is None:
            SwarmRegistry.get().remove_subscriber(push_cb)
            _subs.pop(sid, None)
            return
        snap = SwarmRegistry.get().snapshot(parent_ctx_id=parent or None)
        try:
            await inst.emit_to(sid, "swarm_push", {"agents": snap})
        except Exception:
            pass

    return push_cb


class SwarmWsEvent(Extension):
    async def execute(
        self, instance=None, sid: str = "",
        event_type: str = "", data: dict | None = None,
        response_data: dict | None = None, **kwargs,
    ):
        data = data or {}
        response_data = response_data if response_data is not None else {}

        if event_type == "swarm_subscribe":
            parent = data.get("parent_context_id", "") or ""
            loop = asyncio.get_running_loop()

            old = _subs.pop(sid, None)
            if old:
                SwarmRegistry.get().remove_subscriber(old[2])

            push_cb = _make_push_cb(instance, sid, parent)
            _subs[sid] = (loop, parent, push_cb)
            SwarmRegistry.get().add_subscriber(loop, push_cb)
            response_data["agents"] = SwarmRegistry.get().snapshot(parent_ctx_id=parent or None)

        elif event_type == "swarm_unsubscribe":
            entry = _subs.pop(sid, None)
            if entry:
                SwarmRegistry.get().remove_subscriber(entry[2])
            response_data["ok"] = True
