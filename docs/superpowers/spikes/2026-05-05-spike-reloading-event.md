# Spike 0.1: `Reloading { new_socket }` event semantics

**Date:** 2026-05-05
**Spec ref:** §7.1, §11
**Status:** Deferred to integration phase

## Why deferred

Triggering the `Reloading` event reliably requires:

1. Spawning a `jcode serve` daemon with a connected client (this is doable)
2. Triggering jcode's self-update or hot-reload mechanism mid-stream (this requires either
   `jcode update` to find a newer version on GitHub releases, OR `jcode self-dev` to rebuild
   in-place — which requires Rust toolchain + active selfdev session)
3. Observing the exact event JSON the daemon emits to the connected client before swap
4. Verifying the field name (`new_socket` vs `socket`) and reconnect timing

Without an existing newer release than v0.11.10 and without Rust+selfdev set up, this can't be
empirically verified in this session.

## Plan path forward

Defer to **integration testing phase** (plan Chunk 12). Add an integration test
`tests/integration/test_reload_event.py` that:

1. Spawns daemon at v0.11.10
2. Connects a JcodeClient
3. Modifies `~/.jcode/builds/stable/jcode` symlink to point at a different binary (or builds a
   v0.11.11 placeholder)
4. Triggers reload via debug socket or `kill -HUP`
5. Captures the event the client receives
6. Asserts the field name and timing

Until then, **plugin reconnect logic uses defensive fallback**: when ANY event of type starting
with `reloading` arrives, attempt to read `new_socket` field if present, else read `socket`,
else fall back to existing socket path. This is forward-compatible with whichever exact name
turns out to be correct.

```python
# usr/plugins/jcode_harness/helpers/jcode_client.py
async def _maybe_follow_reloading(self, ev) -> bool:
    if ev.type == "reloading":
        new_path = (
            getattr(ev, "new_socket", None)
            or getattr(ev, "socket", None)
            or ev.raw.get("new_socket")
            or ev.raw.get("socket")
            or self._socket_path  # fall back to existing
        )
        await self.close()
        await asyncio.sleep(0.1)
        self._socket_path = new_path
        await self._reconnect_loop(...)
        return True
    return False
```

## Plan impact

- Update plan Task 3.7 to describe the defensive field-name lookup pattern.
- Add `tests/integration/test_reload_event.py` to plan Chunk 12 with skip-if-no-newer-version
  marker.
- Mark UnknownEvent codec dispatch (Task 2.1) as the safety net so new variant names don't
  crash the client.
