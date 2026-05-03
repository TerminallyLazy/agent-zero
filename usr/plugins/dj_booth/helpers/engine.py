"""StreamEngine: protocol + FfmpegEngine (fallback) + LiquidsoapEngine (preferred).

Engine selection is one-shot at start() — no mid-session auto-swap.
See spec section 4.4 for failure semantics.

Slice 3: 2-deck architecture with crossfader, per-deck volume + 3-band EQ.
"""
from __future__ import annotations

import asyncio
import logging
import shutil
from typing import Optional, Protocol


log = logging.getLogger(__name__)


LIQ_TELNET_HOST = "localhost"
LIQ_TELNET_PORT = 1234
LIQ_SCRIPT_PATH = "/tmp/dj_booth.liq"


LIQ_SCRIPT_TEMPLATE = '''# dj_booth — generated, do not edit
set("server.telnet", true)
set("server.telnet.port", {telnet_port})
set("log.file", false)
set("log.stdout", true)

# Decks
deck_a_q = request.queue(id="deck_a")
deck_b_q = request.queue(id="deck_b")

deck_a = audio_to_stereo(deck_a_q)
deck_b = audio_to_stereo(deck_b_q)

# 3-band EQ per deck (server-controlled refs)
eq_low_a  = interactive.float("deck_a.eq_low",  0.0)
eq_mid_a  = interactive.float("deck_a.eq_mid",  0.0)
eq_high_a = interactive.float("deck_a.eq_high", 0.0)
eq_low_b  = interactive.float("deck_b.eq_low",  0.0)
eq_mid_b  = interactive.float("deck_b.eq_mid",  0.0)
eq_high_b = interactive.float("deck_b.eq_high", 0.0)

deck_a = ladspa.tap_equalizer(deck_a, low={{eq_low_a}}, mid={{eq_mid_a}}, high={{eq_high_a}})
deck_b = ladspa.tap_equalizer(deck_b, low={{eq_low_b}}, mid={{eq_mid_b}}, high={{eq_high_b}})

# Pitch (rate-based) per deck
pitch_a = interactive.float("deck_a.pitch", 1.0)
pitch_b = interactive.float("deck_b.pitch", 1.0)
deck_a = stretch(ratio=!pitch_a, deck_a)
deck_b = stretch(ratio=!pitch_b, deck_b)

# Channel volumes (server-controlled)
vol_a = interactive.float("deck_a.volume", 1.0)
vol_b = interactive.float("deck_b.volume", 1.0)
deck_a = amplify({{vol_a}}, deck_a)
deck_b = amplify({{vol_b}}, deck_b)

# Crossfader: 0=A, 1=B
xf = interactive.float("mixer.crossfader", 0.5)
mix = add([
  amplify({{1.0 - !xf}}, deck_a),
  amplify({{!xf}}, deck_b)
])

# Master
master_v = interactive.float("mixer.master_volume", 0.8)
mix = amplify({{master_v}}, mix)
mix = mksafe(mix)

# EFX
reverb_wet = interactive.float("efx.reverb_wet", 0.0)
delay_wet  = interactive.float("efx.delay_wet", 0.0)
delay_time = interactive.float("efx.delay_time", 0.3)
filter_freq = interactive.float("efx.filter_freq", 20000.0)
mix = ladspa.plate_2x2(mix, dry=!reverb_wet, wet=!reverb_wet)
mix = echo(delay=!delay_time, feedback=0.4, ping_pong=false, mix)
mix = filter.iir.butter.low(frequency=!filter_freq, mix)

# TTS injection queue (fallback source — TTS interrupts when present)
tts_queue = request.queue(id="tts")
mix = fallback(track_sensitive=false, [tts_queue, mix])

output.icecast(
  %mp3(bitrate={bitrate}),
  host="localhost",
  port={icecast_port},
  password="{source_password}",
  mount="{mount}",
  name="{stream_name}",
  description="{stream_description}",
  genre="{stream_genre}",
  url="{stream_url}",
  public={public_int},
  mix
)
'''


def render_liq_script(cfg: dict) -> str:
    return LIQ_SCRIPT_TEMPLATE.format(
        telnet_port=LIQ_TELNET_PORT,
        bitrate=int(cfg.get("bitrate", 192)),
        icecast_port=int(cfg["icecast_port"]),
        source_password=cfg["icecast_source_password"],
        mount=cfg.get("mount", "/stream"),
        stream_name=cfg.get("stream_name", "Stream"),
        stream_description=cfg.get("stream_description", ""),
        stream_genre=cfg.get("stream_genre", ""),
        stream_url=cfg.get("stream_url", ""),
        public_int="true" if cfg.get("public_listing") else "false",
    )


class StreamEngine(Protocol):
    name: str
    async def start(self, config: dict, initial_tracks: list[str]) -> None: ...
    async def stop(self) -> None: ...
    async def queue_track(self, path: str, deck: str = "a") -> None: ...
    async def skip(self, deck: str = "a") -> None: ...
    async def clear_queue(self, deck: str = "a") -> None: ...
    async def is_alive(self) -> bool: ...
    async def get_current(self, deck: str = "a") -> Optional[str]: ...
    async def set_crossfader(self, value: float) -> None: ...
    async def set_volume(self, target: str, value: float) -> None: ...
    async def set_eq(self, deck: str, low: float, mid: float, high: float) -> None: ...
    async def set_pitch(self, deck: str, semitones: float) -> None: ...
    async def set_efx(self, effect: str, param: str, value) -> None: ...
    async def inject_tts(self, wav_path: str) -> None: ...


def select_engine() -> StreamEngine:
    if shutil.which("liquidsoap"):
        return LiquidsoapEngine()
    if shutil.which("ffmpeg"):
        return FfmpegEngine()
    raise RuntimeError("dj_booth: neither liquidsoap nor ffmpeg is installed")


class FfmpegEngine:
    """
    Fallback engine. Maintains an asyncio queue of track paths and spawns
    one ffmpeg per track that streams directly to the icecast source.
    No crossfade. Brief silence between tracks is expected.

    Slice 3: deck-aware in signature only — ffmpeg cannot mix two streams,
    so deck arg is treated as advisory metadata. Mixer ops log warnings.
    """
    name = "ffmpeg"

    def __init__(self):
        self.queue: asyncio.Queue[str] = asyncio.Queue()
        self.config: dict = {}
        self._loop_task: Optional[asyncio.Task] = None
        self._current_proc: Optional[asyncio.subprocess.Process] = None
        self._current_path: str = ""
        self._failure_streak: int = 0

    async def start(self, config: dict, initial_tracks: list[str]) -> None:
        self.config = config
        for t in initial_tracks:
            await self.queue.put(t)
        self._loop_task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._loop_task:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass
            self._loop_task = None
        await self._kill_current()
        while not self.queue.empty():
            self.queue.get_nowait()

    async def queue_track(self, path: str, deck: str = "a") -> None:
        await self.queue.put(path)  # deck arg ignored in fallback

    async def skip(self, deck: str = "a") -> None:
        await self._kill_current()

    async def clear_queue(self, deck: str = "a") -> None:
        while not self.queue.empty():
            self.queue.get_nowait()

    async def set_crossfader(self, value: float) -> None:
        log.warning("dj_booth: ffmpeg fallback ignores crossfader")

    async def set_volume(self, target: str, value: float) -> None:
        log.warning("dj_booth: ffmpeg fallback ignores volume")

    async def set_eq(self, deck: str, low: float, mid: float, high: float) -> None:
        log.warning("dj_booth: ffmpeg fallback ignores EQ")

    async def set_pitch(self, deck: str, semitones: float) -> None:
        log.warning("dj_booth: ffmpeg fallback ignores pitch")

    async def set_efx(self, effect: str, param: str, value) -> None:
        log.warning("dj_booth: ffmpeg fallback ignores EFX")

    async def inject_tts(self, wav_path: str) -> None:
        log.warning("dj_booth: ffmpeg fallback ignores TTS injection")

    async def is_alive(self) -> bool:
        return self._loop_task is not None and not self._loop_task.done()

    async def get_current(self, deck: str = "a") -> Optional[str]:
        if deck != "a":
            return None  # ffmpeg only plays one stream
        return self._current_path or None

    async def _kill_current(self) -> None:
        if self._current_proc and self._current_proc.returncode is None:
            try:
                self._current_proc.terminate()
                try:
                    await asyncio.wait_for(self._current_proc.wait(), timeout=2.0)
                except asyncio.TimeoutError:
                    self._current_proc.kill()
                    await self._current_proc.wait()
            except ProcessLookupError:
                pass
        self._current_proc = None
        self._current_path = ""

    async def _loop(self) -> None:
        cfg = self.config
        port = int(cfg.get("icecast_port", 8000))
        bitrate = int(cfg.get("bitrate", 192))
        sample_rate = int(cfg.get("sample_rate", 44100))
        mount = cfg.get("mount", "/stream")
        password = cfg["icecast_source_password"]
        icecast_url = f"icecast://source:{password}@localhost:{port}{mount}"

        while True:
            try:
                path: str
                try:
                    path = self.queue.get_nowait()
                    self._current_path = path
                    cmd = [
                        "ffmpeg", "-hide_banner", "-loglevel", "error",
                        "-re", "-i", path,
                        "-c:a", "libmp3lame", "-b:a", f"{bitrate}k",
                        "-ar", str(sample_rate), "-ac", "2",
                        "-content_type", "audio/mpeg", "-f", "mp3",
                        icecast_url,
                    ]
                except asyncio.QueueEmpty:
                    self._current_path = ""
                    cmd = [
                        "ffmpeg", "-hide_banner", "-loglevel", "error",
                        "-re", "-f", "lavfi",
                        "-i", f"anullsrc=r={sample_rate}:cl=stereo",
                        "-t", "5",
                        "-c:a", "libmp3lame", "-b:a", f"{bitrate}k",
                        "-content_type", "audio/mpeg", "-f", "mp3",
                        icecast_url,
                    ]
                self._current_proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                rc = await self._current_proc.wait()
                if rc != 0 and self._current_path:
                    self._failure_streak += 1
                    log.warning("dj_booth ffmpeg failed for %s rc=%d", self._current_path, rc)
                    if self._failure_streak >= 3:
                        log.error("dj_booth ffmpeg engine: 3 consecutive failures, exiting loop")
                        return
                else:
                    self._failure_streak = 0
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("dj_booth ffmpeg loop error")
                await asyncio.sleep(0.5)


class LiquidsoapEngine:
    name = "liquidsoap"

    def __init__(self):
        self.process: Optional[asyncio.subprocess.Process] = None
        self.config: dict = {}

    async def start(self, config: dict, initial_tracks: list[str]) -> None:
        self.config = config
        from pathlib import Path as _P
        _P(LIQ_SCRIPT_PATH).write_text(render_liq_script(config))
        self.process = await asyncio.create_subprocess_exec(
            "liquidsoap", LIQ_SCRIPT_PATH,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        # liquidsoap takes ~1-2s to bind telnet port — retry
        last_err: Optional[Exception] = None
        for _ in range(15):
            await asyncio.sleep(0.2)
            if self.process.returncode is not None:
                raise RuntimeError(f"liquidsoap exited rc={self.process.returncode}")
            try:
                await self._telnet_send("version")
                last_err = None
                break
            except (ConnectionRefusedError, OSError) as e:
                last_err = e
        if last_err is not None:
            await self.stop()
            raise RuntimeError(f"liquidsoap telnet failed: {last_err}")
        for path in initial_tracks:
            await self.queue_track(path)

    async def stop(self) -> None:
        if self.process is None:
            return
        try:
            try:
                await asyncio.wait_for(self._telnet_send("quit"), timeout=1.0)
            except Exception:
                pass
            try:
                await asyncio.wait_for(self.process.wait(), timeout=3.0)
            except asyncio.TimeoutError:
                self.process.terminate()
                try:
                    await asyncio.wait_for(self.process.wait(), timeout=2.0)
                except asyncio.TimeoutError:
                    self.process.kill()
                    await self.process.wait()
        except ProcessLookupError:
            pass
        self.process = None
        try:
            import os as _os
            _os.unlink(LIQ_SCRIPT_PATH)
        except FileNotFoundError:
            pass

    async def queue_track(self, path: str, deck: str = "a") -> None:
        queue_id = "deck_a" if deck == "a" else "deck_b"
        await self._telnet_send(f"{queue_id}.push {path}")

    async def skip(self, deck: str = "a") -> None:
        queue_id = "deck_a" if deck == "a" else "deck_b"
        await self._telnet_send(f"{queue_id}.skip")

    async def clear_queue(self, deck: str = "a") -> None:
        queue_id = "deck_a" if deck == "a" else "deck_b"
        for _ in range(100):
            resp = await self._telnet_send(f"{queue_id}.length")
            try:
                if int(resp.strip()) == 0:
                    return
            except ValueError:
                return
            await self._telnet_send(f"{queue_id}.skip")

    async def is_alive(self) -> bool:
        return self.process is not None and self.process.returncode is None

    async def get_current(self, deck: str = "a") -> Optional[str]:
        # request.on_air returns the on-air rid for whichever queue has audio out;
        # we use the per-queue "remaining" trick: query deck_a.queue for current.
        try:
            rid = (await self._telnet_send(f"{'deck_a' if deck == 'a' else 'deck_b'}.queue")).strip().split("\n")[0].strip()
            if not rid:
                return None
            meta = await self._telnet_send(f"request.metadata {rid}")
            artist = title = ""
            for line in meta.splitlines():
                if line.startswith('artist="'):
                    artist = line.split('"', 2)[1]
                elif line.startswith('title="'):
                    title = line.split('"', 2)[1]
            if artist or title:
                return f"{artist} - {title}".strip(" -")
            return None
        except Exception:
            return None

    async def set_crossfader(self, value: float) -> None:
        v = max(0.0, min(1.0, float(value)))
        await self._telnet_send(f"mixer.crossfader.set {v}")

    async def set_volume(self, target: str, value: float) -> None:
        """target: 'deck_a' | 'deck_b' | 'master'"""
        v = max(0.0, min(2.0, float(value)))
        if target == "master":
            await self._telnet_send(f"mixer.master_volume.set {v}")
        else:
            await self._telnet_send(f"{target}.volume.set {v}")

    async def set_eq(self, deck: str, low: float, mid: float, high: float) -> None:
        deck_q = "deck_a" if deck == "a" else "deck_b"
        for band, val in [("low", low), ("mid", mid), ("high", high)]:
            v = max(-12.0, min(12.0, float(val)))
            await self._telnet_send(f"{deck_q}.eq_{band}.set {v}")

    async def set_pitch(self, deck: str, semitones: float) -> None:
        s = max(-6.0, min(6.0, float(semitones)))
        ratio = 2.0 ** (s / 12.0)
        target = "deck_a" if deck == "a" else "deck_b"
        await self._telnet_send(f"{target}.pitch.set {ratio}")

    async def set_efx(self, effect: str, param: str, value) -> None:
        # filter type change requires script reload — skip in Slice 5
        if param == "type":
            return
        name = f"efx.{effect}_{param}"
        await self._telnet_send(f"{name}.set {float(value)}")

    async def inject_tts(self, wav_path: str) -> None:
        await self._telnet_send(f"tts.push {wav_path}")

    async def _telnet_send(self, command: str) -> str:
        reader, writer = await asyncio.open_connection(LIQ_TELNET_HOST, LIQ_TELNET_PORT)
        try:
            writer.write((command + "\n").encode())
            await writer.drain()
            buf = b""
            while True:
                chunk = await asyncio.wait_for(reader.read(1024), timeout=2.0)
                if not chunk:
                    break
                buf += chunk
                if b"END\r\n" in buf or b"END\n" in buf:
                    break
            text = buf.decode(errors="replace")
            for marker in ("END\r\n", "END\n"):
                if text.endswith(marker):
                    text = text[: -len(marker)]
                    break
            return text
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
