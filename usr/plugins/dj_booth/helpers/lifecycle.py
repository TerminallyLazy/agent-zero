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

        # Self-test: confirm the streaming server is actually answering on
        # the configured port from inside this process. If it isn't, mark the
        # stream as not-running and surface a clear error — better than the
        # user finding out via a 502 when they click Share Online.
        ok, detail = await _self_check_origin(int(cfg["icecast_port"]), s.mount)
        if not ok:
            log.error("dj_booth: origin self-check failed: %s", detail)
            s.error = f"Stream started but the server isn't responding: {detail}"
            s.is_running = False
            try:
                await _engine.stop()
            except Exception:
                pass
            try:
                await ice.stop()
            except Exception:
                pass
            _engine = None
            raise RuntimeError(s.error)

        _health_task = asyncio.create_task(_health_loop(cfg))

        from usr.plugins.dj_booth.helpers.spectrum import spectrum_loop

        def _on_spectrum(bands: list[float]):
            _state.get_state().spectrum = bands

        _spectrum_task = asyncio.create_task(spectrum_loop(s.stream_url, _on_spectrum))


async def _self_check_origin(port: int, mount: str) -> tuple[bool, str]:
    """HTTP GET our own status endpoint to confirm the server is actually serving.
    Returns (ok, message). Used right after start_stack to catch silent failures."""
    import urllib.error
    import urllib.request

    def _check():
        url = f"http://localhost:{port}/status-json.xsl"
        try:
            with urllib.request.urlopen(url, timeout=3.0) as resp:
                return (resp.status == 200, f"status-json returned {resp.status}")
        except urllib.error.URLError as e:
            return (False, f"could not reach {url}: {e.reason}")
        except Exception as e:
            return (False, f"self-check error: {e}")

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _check)


async def connectivity_check() -> dict:
    """Manual diagnostic: report whether the origin server, mount, and engine
    are healthy. Wired to api/dj_control.py action='connectivity_check' for
    the UI 'Diagnose' button."""
    s = _state.get_state()
    if not s.is_running:
        return {
            "ok": False,
            "is_running": False,
            "stream_url": s.stream_url,
            "detail": "Stream is off. Click Start in the DJ Booth.",
        }
    import urllib.error
    import urllib.request

    def _probe(path):
        url = f"http://localhost:{int(s.stream_url.split(':')[2].split('/')[0])}{path}"
        try:
            with urllib.request.urlopen(url, timeout=3.0) as r:
                return (True, r.status, "")
        except urllib.error.URLError as e:
            return (False, 0, str(e.reason))
        except Exception as e:
            return (False, 0, str(e))

    loop = asyncio.get_event_loop()
    status_ok, status_code, status_err = await loop.run_in_executor(None, _probe, "/status-json.xsl")
    mount_ok, mount_code, mount_err = await loop.run_in_executor(None, _probe, s.mount)

    engine_alive = False
    try:
        engine_alive = (_engine is not None) and await _engine.is_alive()
    except Exception:
        pass

    # Are audio bytes actually flowing? Definitive answer for "is the
    # engine pushing data?" — independent of the engine's task being alive.
    bytes_pushed = 0
    last_chunk_age = -1.0
    try:
        ice = IcecastManager.get()
        if getattr(ice, "python_server", None) is not None:
            bytes_pushed = ice.python_server.bytes_pushed
            import time as _time
            if ice.python_server.last_chunk_at > 0:
                last_chunk_age = _time.time() - ice.python_server.last_chunk_at
    except Exception:
        pass

    has_audio_flow = bytes_pushed > 0 and (last_chunk_age < 0 or last_chunk_age < 30)

    return {
        "ok": status_ok and mount_ok and engine_alive,
        "is_running": s.is_running,
        "stream_url": s.stream_url,
        "status_endpoint_ok": status_ok,
        "status_endpoint_code": status_code,
        "status_endpoint_error": status_err,
        "mount_ok": mount_ok,
        "mount_code": mount_code,
        "mount_error": mount_err,
        "engine_alive": engine_alive,
        "engine_name": s.engine,
        "listener_count": s.listener_count,
        "queue_length": len(s.deck_a.queue) + len(s.deck_b.queue),
        "bytes_pushed": bytes_pushed,
        "last_chunk_age_seconds": round(last_chunk_age, 1) if last_chunk_age >= 0 else None,
        "audio_flowing": has_audio_flow,
    }


async def _cancel_task(task: Optional[asyncio.Task], name: str, timeout: float = 2.0) -> None:
    """Cancel a task, await its completion with a hard timeout, swallow ALL errors.
    Used by stop_stack so a misbehaving task can never block the stream from
    being marked off."""
    if task is None:
        return
    try:
        task.cancel()
    except Exception:
        pass
    try:
        await asyncio.wait_for(task, timeout=timeout)
    except (asyncio.CancelledError, asyncio.TimeoutError):
        pass
    except BaseException:
        log.exception("dj_booth: error awaiting task '%s'", name)


async def stop_stack() -> None:
    """Tear everything down. Bulletproof: state.is_running flips to False
    immediately, every cleanup step is wrapped in a timeout, and reset_state
    runs in a finally block so no individual failure can leave the booth
    in a permanently 'running' state."""
    global _engine, _health_task, _spectrum_task, _share_task
    s = _state.get_state()

    # Flip is_running off FIRST so the UI sees 'stopped' the moment Stop is
    # clicked, even if the cleanup below is slow or partially fails.
    s.is_running = False
    s.spectrum = []

    lock = _state.get_lifecycle_lock()
    try:
        await asyncio.wait_for(lock.acquire(), timeout=10.0)
    except asyncio.TimeoutError:
        log.error("dj_booth: stop_stack could not acquire lifecycle lock — forcing reset")
        _state.reset_state(keep_library=True, keep_error=False)
        return

    try:
        # Cancel background tasks (catch ALL — never let a hung task block stop).
        await _cancel_task(_spectrum_task, "spectrum_task")
        _spectrum_task = None
        await _cancel_task(_health_task, "health_task")
        _health_task = None
        await _cancel_task(_share_task, "share_task")
        _share_task = None

        # Stop the audio engine (ffmpeg / liquidsoap).
        if _engine is not None:
            try:
                await asyncio.wait_for(_engine.stop(), timeout=5.0)
            except (asyncio.TimeoutError, Exception):
                log.exception("dj_booth: engine stop did not complete cleanly")
            _engine = None

        # Stop the streaming server (icecast2 subprocess OR in-process IcyServer).
        try:
            await asyncio.wait_for(IcecastManager.get().stop(), timeout=5.0)
        except (asyncio.TimeoutError, Exception):
            log.exception("dj_booth: icecast/icy server stop did not complete cleanly")

        # Tear down the public Cloudflare tunnel if it's up. Sync method —
        # run in executor so a slow cloudflared shutdown can't block us.
        try:
            from usr.plugins.dj_booth.helpers.stream_tunnel import StreamTunnel
            tunnel = StreamTunnel.get()
            loop = asyncio.get_event_loop()
            await asyncio.wait_for(loop.run_in_executor(None, tunnel.stop), timeout=5.0)
        except (asyncio.TimeoutError, Exception):
            log.exception("dj_booth: tunnel stop did not complete cleanly")
    finally:
        # Always reset state so the UI never sees 'running' after a Stop click.
        _state.reset_state(keep_library=True, keep_error=False)
        try:
            lock.release()
        except RuntimeError:
            pass


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



_share_task: Optional[asyncio.Task] = None


# Public-share (Cloudflare quick tunnel) wrappers
async def start_public_share(timeout: float = 60.0) -> str:
    """
    Kick off a Cloudflare quick tunnel for the stream port. Non-blocking:
    returns immediately with public_url_starting=True. The frontend polls
    /stream_status every second and will pick up public_url when the tunnel
    is ready (typically 5-15 seconds), or public_url_error if it failed.
    """
    global _share_task
    s = _state.get_state()
    if not s.is_running:
        raise RuntimeError("Start the stream first, then click Share Online.")

    # Idempotent: if a tunnel is already running or starting, don't kick off another
    if s.public_url:
        return s.public_url
    if s.public_url_starting:
        return ""

    from helpers.plugins import get_plugin_config
    cfg = get_plugin_config("dj_booth") or {}
    port = int(cfg.get("icecast_port", 8000))
    mount = cfg.get("mount", "/stream")

    s.public_url_starting = True
    s.public_url_error = ""
    s.public_url = ""

    async def _runner():
        from usr.plugins.dj_booth.helpers.stream_tunnel import StreamTunnel
        tunnel = StreamTunnel.get()
        loop = asyncio.get_event_loop()
        try:
            url = await loop.run_in_executor(None, tunnel.start, port, timeout)
            st = _state.get_state()
            if url:
                st.public_url = f"{url}{mount}"
                st.public_url_error = ""
                log.info("dj_booth: public share live at %s", st.public_url)
            else:
                st.public_url = ""
                st.public_url_error = tunnel.last_error or "Tunnel could not be created."
                log.warning("dj_booth: public share failed: %s", st.public_url_error)
        except Exception as e:
            log.exception("dj_booth: public share error")
            _state.get_state().public_url_error = f"unexpected error: {e}"
        finally:
            _state.get_state().public_url_starting = False

    _share_task = asyncio.create_task(_runner())
    return ""


async def stop_public_share() -> None:
    global _share_task
    s = _state.get_state()
    if _share_task and not _share_task.done():
        _share_task.cancel()
        try:
            await _share_task
        except (asyncio.CancelledError, Exception):
            pass
        _share_task = None

    from usr.plugins.dj_booth.helpers.stream_tunnel import StreamTunnel
    loop = asyncio.get_event_loop()
    try:
        await loop.run_in_executor(None, StreamTunnel.get().stop)
    except Exception:
        log.exception("dj_booth: tunnel stop error")

    s.public_url = ""
    s.public_url_error = ""
    s.public_url_starting = False
