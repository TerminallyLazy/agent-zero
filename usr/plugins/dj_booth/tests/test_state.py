import asyncio
import pytest
from usr.plugins.dj_booth.helpers.state import (
    StreamState, get_state, get_lifecycle_lock, reset_state,
)


def test_get_state_returns_singleton():
    s1 = get_state()
    s2 = get_state()
    assert s1 is s2


def test_default_state_values():
    reset_state()
    s = get_state()
    assert s.is_running is False
    assert s.engine == ""
    assert s.listener_count == 0
    assert s.queue == []
    assert s.error == ""


def test_lifecycle_lock_is_singleton():
    l1 = get_lifecycle_lock()
    l2 = get_lifecycle_lock()
    assert l1 is l2
    assert isinstance(l1, asyncio.Lock)


def test_reset_state_clears_runtime_fields_keeps_library_count():
    reset_state()
    s = get_state()
    s.is_running = True
    s.listener_count = 5
    s.library_count = 42
    s.error = "old"
    reset_state(keep_library=True, keep_error=False)
    s = get_state()
    assert s.is_running is False
    assert s.listener_count == 0
    assert s.library_count == 42
    assert s.error == ""


def test_deck_state_defaults():
    from usr.plugins.dj_booth.helpers.state import DeckState
    d = DeckState()
    assert d.queue == []
    assert d.current_track == ""
    assert d.volume == 1.0
    assert d.eq_low == 0.0 and d.eq_mid == 0.0 and d.eq_high == 0.0


def test_mixer_state_defaults():
    from usr.plugins.dj_booth.helpers.state import MixerState
    m = MixerState()
    assert m.crossfader == 0.5
    assert m.master_volume == 0.8


def test_stream_state_has_decks():
    reset_state()
    s = get_state()
    assert hasattr(s, "deck_a") and hasattr(s, "deck_b")
    assert s.deck_a.volume == 1.0
    assert s.mixer.crossfader == 0.5


def test_reset_state_restores_decks():
    reset_state()
    s = get_state()
    s.deck_a.volume = 0.3
    s.mixer.crossfader = 0.9
    reset_state()
    assert s.deck_a.volume == 1.0
    assert s.mixer.crossfader == 0.5


def test_deck_state_has_pitch():
    from usr.plugins.dj_booth.helpers.state import DeckState
    d = DeckState()
    assert hasattr(d, "pitch")
    assert d.pitch == 0.0


def test_efx_state_defaults():
    from usr.plugins.dj_booth.helpers.state import EFXState
    e = EFXState()
    assert e.reverb_wet == 0.0
    assert e.delay_wet == 0.0
    assert e.delay_time == 0.3
    assert e.filter_freq == 20000.0
    assert e.filter_type == "lowpass"


def test_stream_state_has_efx():
    reset_state()
    s = get_state()
    assert hasattr(s, "efx")
    assert s.efx.reverb_wet == 0.0


def test_reset_state_resets_efx():
    reset_state()
    s = get_state()
    s.efx.reverb_wet = 0.7
    s.efx.delay_time = 0.9
    s.deck_a.pitch = 3.5
    reset_state()
    assert s.efx.reverb_wet == 0.0
    assert s.efx.delay_time == 0.3
    assert s.deck_a.pitch == 0.0


def test_stream_state_has_listener_hint_fields():
    """New non-technical-friendly hint fields default to safe 'unknown' values."""
    reset_state()
    s = get_state()
    assert hasattr(s, "port_forwarded")
    assert s.port_forwarded is None  # None = unknown
    assert hasattr(s, "ever_had_listener")
    assert s.ever_had_listener is False
    assert hasattr(s, "started_at")
    assert s.started_at == 0.0


def test_reset_state_resets_listener_hint_fields():
    reset_state()
    s = get_state()
    s.port_forwarded = True
    s.ever_had_listener = True
    s.started_at = 12345.6
    reset_state()
    assert s.port_forwarded is None
    assert s.ever_had_listener is False
    assert s.started_at == 0.0
