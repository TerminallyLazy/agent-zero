from __future__ import annotations
import asyncio
from helpers.extension import Extension
from usr.plugins.a0_swarm.helpers.registry import SwarmRegistry

_subs: dict[str, tuple] = {}


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

            async def push_cb():
                snap = SwarmRegistry.get().snapshot(parent_ctx_id=parent or None)
                try:
                    await instance.emit_to(sid, "swarm_push", {"agents": snap})
                except Exception:
                    pass

            old = _subs.pop(sid, None)
            if old:
                SwarmRegistry.get().remove_subscriber(old[2])

            _subs[sid] = (loop, parent, push_cb)
            SwarmRegistry.get().add_subscriber(loop, push_cb)
            response_data["agents"] = SwarmRegistry.get().snapshot(parent_ctx_id=parent or None)

        elif event_type == "swarm_unsubscribe":
            entry = _subs.pop(sid, None)
            if entry:
                SwarmRegistry.get().remove_subscriber(entry[2])
            response_data["ok"] = True
