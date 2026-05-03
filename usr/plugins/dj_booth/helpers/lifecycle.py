"""Lifecycle orchestration: start_stack, stop_stack, _health_loop."""
from __future__ import annotations

import asyncio
import logging
import os
import signal
import socket
from pathlib import Path
from typing import Optional

from usr.plugins.dj_booth.helpers import state as _state
from usr.plugins.dj_booth.helpers.icecast import IcecastManager, PIDFILE as ICECAST_PIDFILE
from usr.plugins.dj_booth.helpers.engine import (
    StreamEngine, select_engine, LIQ_SCRIPT_PATH,
)


log = logging.getLogger(__name__)


REQUIRED_FIELDS = (
    "icecast_port", "icecast_source_password", "icecast_admin_password", "music_dir",
)

PIDFILES_TO_SWEEP = (
    ICECAST_PIDFILE,
)

_engine: Optional[StreamEngine] = None
_health_task: Optional[asyncio.Task] = None


def _get_icecast() -> IcecastManager:
    return IcecastManager.get()


def _make_engine() -> StreamEngine:
    return select_engine()


def validate_config(cfg: dict) -> None:
    for f in REQUIRED_FIELDS:
        if f not in cfg or cfg[f] in (None, ""):
            raise ValueError(f"dj_booth config missing required field: {f}")
    try:
        port = int(cfg["icecast_port"])
    except (TypeError, ValueError):
        raise ValueError("icecast_port must be an integer")
    if not (1 <= port <= 65535):
        raise ValueError(f"icecast_port {port} out of range")


def _port_bind_probe(port: int) -> None:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind(("0.0.0.0", port))
    finally:
        s.close()


def _sweep_stale_pidfiles() -> None:
    for path in PIDFILES_TO_SWEEP:
        try:
            content = Path(path).read_text().strip()
            pid = int(content)
        except (FileNotFoundError, ValueError):
            try:
                Path(path).unlink()
            except FileNotFoundError:
                pass
            continue
        try:
            os.kill(pid, 0)
            os.kill(pid, signal.SIGTERM)
            log.info("dj_booth: cleaned up stale pid %d from %s", pid, path)
        except ProcessLookupError:
            pass
        except PermissionError:
            log.warning("dj_booth: pid %d from %s not killable", pid, path)
        try:
            Path(path).unlink()
        except FileNotFoundError:
            pass


async def start_stack(cfg: dict, initial_tracks: Optional[list[str]] = None) -> None:
    global _engine, _health_task
    s = _state.get_state()
    lock = _state.get_lifecycle_lock()
    async with lock:
        if s.is_running:
            log.info("dj_booth: start requested but already running — no-op")
            return
        try:
            validate_config(cfg)
            _sweep_stale_pidfiles()
            _port_bind_probe(int(cfg["icecast_port"]))
        except (ValueError, OSError) as e:
            s.error = str(e) if isinstance(e, ValueError) else f"Port {cfg.get('icecast_port')} in use"
            s.is_running = False
            raise RuntimeError(s.error) from e

        ice = _get_icecast()
        await ice.start(cfg)

        _engine = _make_engine()
        try:
            await _engine.start(cfg, initial_tracks or [])
        except Exception as e:
            s.error = f"engine start failed: {e}"
            await ice.stop()
            _engine = None
            s.is_running = False
            raise

        s.is_running = True
        s.error = ""
        s.engine = _engine.name
        s.mount = cfg.get("mount", "/stream")
        s.stream_url = f"http://localhost:{cfg['icecast_port']}{s.mount}"
        s.icecast_pid = ice.process.pid if ice.process else 0

        _health_task = asyncio.create_task(_health_loop(cfg))


async def stop_stack() -> None:
    global _engine, _health_task
    s = _state.get_state()
    lock = _state.get_lifecycle_lock()
    async with lock:
        if _health_task:
            _health_task.cancel()
            try:
                await _health_task
            except asyncio.CancelledError:
                pass
            _health_task = None
        if _engine is not None:
            try:
                await _engine.stop()
            except Exception:
                log.exception("dj_booth: engine stop error")
            _engine = None
        try:
            await IcecastManager.get().stop()
        except Exception:
            log.exception("dj_booth: icecast stop error")
        _state.reset_state(keep_library=True, keep_error=False)


async def queue_track(path: str) -> None:
    s = _state.get_state()
    if not s.is_running or _engine is None:
        raise RuntimeError("stream not running")
    await _engine.queue_track(path)
    s.queue.append(path)


async def skip_current() -> None:
    if _engine is None:
        raise RuntimeError("stream not running")
    await _engine.skip()


async def clear_queue() -> None:
    s = _state.get_state()
    if _engine is None:
        return
    await _engine.clear_queue()
    s.queue.clear()


async def _health_loop(cfg: dict) -> None:
    s = _state.get_state()
    ice = IcecastManager.get()
    while True:
        try:
            await asyncio.sleep(5.0)
            if not await ice.is_alive():
                s.error = "icecast died"
                s.is_running = False
                log.error("dj_booth: icecast died — health loop exiting")
                return
            if _engine is not None and not await _engine.is_alive():
                s.error = "engine died"
                s.is_running = False
                log.error("dj_booth: engine died — health loop exiting")
                return
            s.listener_count = await ice.get_listener_count()
            if _engine is not None:
                cur = await _engine.get_current()
                if cur:
                    s.current_track = cur
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("dj_booth: health loop error")
