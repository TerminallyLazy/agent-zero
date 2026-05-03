"""Lifecycle orchestration: start_stack, stop_stack, _health_loop."""
from __future__ import annotations

import asyncio
import logging
import os
import signal
import socket
import time
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
_spectrum_task: Optional[asyncio.Task] = None


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
    global _engine, _health_task, _spectrum_task
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
        # Reset non-technical-friendly hint fields at every fresh start.
        # These feed the UI's "Listener Help" panel — see webui/dj-booth.html.
        s.started_at = time.time()
        s.ever_had_listener = False
        s.port_forwarded = None  # unknown until someone actually connects

        _health_task = asyncio.create_task(_health_loop(cfg))

        from usr.plugins.dj_booth.helpers.spectrum import spectrum_loop

        def _on_spectrum(bands: list[float]):
            _state.get_state().spectrum = bands

        _spectrum_task = asyncio.create_task(spectrum_loop(s.stream_url, _on_spectrum))


async def stop_stack() -> None:
    global _engine, _health_task, _spectrum_task
    s = _state.get_state()
    lock = _state.get_lifecycle_lock()
    async with lock:
        if _spectrum_task:
            _spectrum_task.cancel()
            try:
                await _spectrum_task
            except asyncio.CancelledError:
                pass
            _spectrum_task = None
        _state.get_state().spectrum = []
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
        # Auto-close any active public-share tunnel when the stream stops
        try:
            from usr.plugins.dj_booth.helpers.stream_tunnel import StreamTunnel
            StreamTunnel.get().stop()
        except Exception:
            log.exception("dj_booth: tunnel stop error")
        _state.reset_state(keep_library=True, keep_error=False)


async def queue_track(path: str, deck: str = "a") -> None:
    s = _state.get_state()
    if not s.is_running or _engine is None:
        raise RuntimeError("stream not running")
    if deck not in ("a", "b"):
        raise ValueError(f"invalid deck: {deck}")
    await _engine.queue_track(path, deck)
    target = s.deck_a if deck == "a" else s.deck_b
    target.queue.append(path)
    if deck == "a":
        s.queue.append(path)  # back-compat mirror


async def skip_current(deck: str = "a") -> None:
    if _engine is None:
        raise RuntimeError("stream not running")
    if deck not in ("a", "b"):
        raise ValueError(f"invalid deck: {deck}")
    await _engine.skip(deck)


async def clear_queue(deck: str = "a") -> None:
    s = _state.get_state()
    if _engine is None:
        return
    if deck not in ("a", "b"):
        raise ValueError(f"invalid deck: {deck}")
    await _engine.clear_queue(deck)
    target = s.deck_a if deck == "a" else s.deck_b
    target.queue.clear()
    if deck == "a":
        s.queue.clear()


async def set_crossfader(value: float) -> None:
    if _engine is None:
        return
    await _engine.set_crossfader(value)
    _state.get_state().mixer.crossfader = max(0.0, min(1.0, float(value)))


async def set_volume(target: str, value: float) -> None:
    if _engine is None:
        return
    await _engine.set_volume(target, value)
    s = _state.get_state()
    v = max(0.0, min(2.0, float(value)))
    if target == "deck_a":
        s.deck_a.volume = v
    elif target == "deck_b":
        s.deck_b.volume = v
    elif target == "master":
        s.mixer.master_volume = v


async def set_eq(deck: str, low: float, mid: float, high: float) -> None:
    if _engine is None:
        return
    if deck not in ("a", "b"):
        raise ValueError(f"invalid deck: {deck}")
    await _engine.set_eq(deck, low, mid, high)
    s = _state.get_state()
    target = s.deck_a if deck == "a" else s.deck_b
    target.eq_low = max(-12.0, min(12.0, float(low)))
    target.eq_mid = max(-12.0, min(12.0, float(mid)))
    target.eq_high = max(-12.0, min(12.0, float(high)))


async def set_pitch(deck: str, semitones: float) -> None:
    if _engine is None:
        return
    if deck not in ("a", "b"):
        raise ValueError(f"invalid deck: {deck}")
    s = max(-6.0, min(6.0, float(semitones)))
    await _engine.set_pitch(deck, s)
    target = _state.get_state().deck_a if deck == "a" else _state.get_state().deck_b
    target.pitch = s


async def set_efx(effect: str, param: str, value) -> None:
    if _engine is None:
        return
    await _engine.set_efx(effect, param, value)
    s = _state.get_state().efx
    attr = f"{effect}_{param}" if param != "type" else "filter_type"
    if hasattr(s, attr):
        setattr(s, attr, value)


async def announce(text: str) -> None:
    if _engine is None or not text.strip():
        return
    from usr.plugins.dj_booth.helpers.tts import generate_tts_wav
    path = await generate_tts_wav(text)
    if path:
        await _engine.inject_tts(path)


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
            # Latch ever_had_listener the first time anyone connects. This is
            # our most reliable hint that the port is actually reachable from
            # wherever this user is sharing the stream. It is informational
            # only — never used to gate functionality.
            if s.listener_count > 0 and not s.ever_had_listener:
                s.ever_had_listener = True
                s.port_forwarded = True
            if _engine is not None:
                cur_a = await _engine.get_current("a")
                cur_b = await _engine.get_current("b")
                s.deck_a.current_track = cur_a or ""
                s.deck_b.current_track = cur_b or ""
                if cur_a:
                    s.current_track = cur_a  # back-compat mirror of deck A
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("dj_booth: health loop error")



# Public-share (Cloudflare quick tunnel) wrappers
async def start_public_share(timeout: float = 30.0) -> str:
    """Start a Cloudflare quick tunnel for the stream port. Returns public URL or ""."""
    s = _state.get_state()
    if not s.is_running:
        raise RuntimeError("Start the stream first, then click Share Online.")
    from usr.plugins.dj_booth.helpers.stream_tunnel import StreamTunnel
    from helpers.plugins import get_plugin_config
    cfg = get_plugin_config("dj_booth") or {}
    port = int(cfg.get("icecast_port", 8000))
    tunnel = StreamTunnel.get()

    s.public_url_starting = True
    s.public_url_error = ""

    # Run blocking start in a thread so we don't block the event loop
    loop = asyncio.get_event_loop()
    url = await loop.run_in_executor(None, tunnel.start, port, timeout)

    s.public_url = url or ""
    s.public_url_error = tunnel.last_error or ""
    s.public_url_starting = False
    if url:
        mount = cfg.get("mount", "/stream")
        s.public_url = f"{url}{mount}"
    return s.public_url


async def stop_public_share() -> None:
    s = _state.get_state()
    from usr.plugins.dj_booth.helpers.stream_tunnel import StreamTunnel
    StreamTunnel.get().stop()
    s.public_url = ""
    s.public_url_error = ""
    s.public_url_starting = False
