"""Singleton stream state for the dj_booth plugin (Slice 1+3)."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DeckState:
    queue: list[str] = field(default_factory=list)
    current_track: str = ""
    volume: float = 1.0
    eq_low: float = 0.0
    eq_mid: float = 0.0
    eq_high: float = 0.0
    pitch: float = 0.0  # semitones, -6..+6


@dataclass
class MixerState:
    crossfader: float = 0.5
    master_volume: float = 0.8


@dataclass
class EFXState:
    reverb_wet: float = 0.0
    delay_wet: float = 0.0
    delay_time: float = 0.3
    filter_freq: float = 20000.0
    filter_type: str = "lowpass"  # lowpass | highpass | bandpass


@dataclass
class StreamState:
    is_running: bool = False
    engine: str = ""              # "liquidsoap" | "ffmpeg" | ""
    stream_url: str = ""          # full URL incl. mount
    mount: str = "/stream"
    listener_count: int = 0
    current_track: str = ""       # Slice 1 back-compat: mirrors deck A
    queue: list[str] = field(default_factory=list)  # Slice 1 back-compat: mirrors deck A
    library_count: int = 0
    error: str = ""
    icecast_pid: int = 0
    engine_pid: int = 0
    deck_a: DeckState = field(default_factory=DeckState)
    deck_b: DeckState = field(default_factory=DeckState)
    mixer: MixerState = field(default_factory=MixerState)
    efx: EFXState = field(default_factory=EFXState)
    spectrum: list[float] = field(default_factory=list)

    # Non-technical-friendly hint fields. These never gate functionality —
    # they only feed plain-language UI cues for users sharing the stream.
    # port_forwarded: None = unknown (default), True = a listener has reached us,
    # False = warning shown after grace period with no connections.
    port_forwarded: Optional[bool] = None
    # ever_had_listener latches True the first time listener_count > 0.
    # The most reliable signal that someone could actually reach the port.
    ever_had_listener: bool = False
    # started_at is unix epoch seconds when start_stack succeeded; 0.0 = not started.
    # UI uses this to decide when enough time has passed to show a "no listener" hint.
    started_at: float = 0.0
    # Public Cloudflare quick-tunnel URL when "Share Online" is active. Empty when off.
    public_url: str = ""
    public_url_starting: bool = False
    public_url_error: str = ""


_instance: Optional[StreamState] = None
_lock: Optional[asyncio.Lock] = None


def get_state() -> StreamState:
    global _instance
    if _instance is None:
        _instance = StreamState()
    return _instance


def get_lifecycle_lock() -> asyncio.Lock:
    global _lock
    if _lock is None:
        _lock = asyncio.Lock()
    return _lock


def reset_state(keep_library: bool = True, keep_error: bool = False) -> None:
    """Reset to defaults. Used after stop() and at module reload."""
    s = get_state()
    library_count = s.library_count if keep_library else 0
    error = s.error if keep_error else ""
    fresh = StreamState()
    fresh.library_count = library_count
    fresh.error = error
    # in-place replace fields so other holders of the singleton see updates.
    # Dataclass-typed fields (deck_a/deck_b/mixer) get fresh instances from the
    # newly-constructed `fresh`, so external holders see proper resets too.
    for f in fresh.__dataclass_fields__:
        setattr(s, f, getattr(fresh, f))
