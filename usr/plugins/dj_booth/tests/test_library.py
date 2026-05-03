import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock
import pytest
from usr.plugins.dj_booth.helpers.library import LibraryManager, Track


def _async_const(val):
    async def _f(*a, **kw):
        return val
    return _f


def make_dummy_audio(path: Path, content: bytes = b"ID3\x03\x00\x00\x00\x00\x00\x00"):
    path.write_bytes(content + b"\x00" * 1024)


@pytest.fixture
def music_dir():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        make_dummy_audio(root / "song1.mp3")
        make_dummy_audio(root / "song2.flac")
        (root / "subdir").mkdir()
        make_dummy_audio(root / "subdir" / "nested.mp3")
        (root / "ignore.txt").write_text("not audio")
        (root / "broken.mp3").write_bytes(b"")
        yield str(root)


def test_scan_finds_audio_files(music_dir):
    lib = LibraryManager()
    lib.scan(music_dir)
    paths = sorted(t.path for t in lib.tracks)
    assert any(p.endswith("song1.mp3") for p in paths)
    assert any(p.endswith("song2.flac") for p in paths)
    assert any(p.endswith("nested.mp3") for p in paths)
    assert not any(p.endswith("ignore.txt") for p in paths)


def test_scan_falls_back_to_filename_when_tags_missing(music_dir):
    lib = LibraryManager()
    lib.scan(music_dir)
    t = next(t for t in lib.tracks if t.path.endswith("song1.mp3"))
    assert t.title
    assert t.artist


def test_search_case_insensitive(music_dir):
    lib = LibraryManager()
    lib.scan(music_dir)
    results = lib.search("SONG")
    assert len(results) >= 2


def test_get_track_by_path(music_dir):
    lib = LibraryManager()
    lib.scan(music_dir)
    p = lib.tracks[0].path
    assert lib.get_track(p) is not None
    assert lib.get_track("/does/not/exist") is None


def test_scan_handles_unreadable_file_gracefully(music_dir):
    lib = LibraryManager()
    lib.scan(music_dir)


def test_scan_returns_count(music_dir):
    lib = LibraryManager()
    count = lib.scan(music_dir)
    assert count == len(lib.tracks)


def test_compute_waveform_returns_empty_on_ffmpeg_failure(monkeypatch):
    from usr.plugins.dj_booth.helpers import library
    monkeypatch.setattr("subprocess.run",
        lambda *a, **kw: type("R", (), {"returncode": 1, "stdout": b""})())
    assert library.compute_waveform("/x.mp3") == []


def test_track_has_analysis_fields():
    from usr.plugins.dj_booth.helpers.library import Track
    t = Track(path="/x.mp3")
    assert t.bpm == 0.0
    assert t.key == ""
    assert t.waveform_peaks == []


@pytest.mark.asyncio
async def test_library_analyze_populates_track(monkeypatch, tmp_path):
    from usr.plugins.dj_booth.helpers.library import LibraryManager, Track, AUDIO_EXTENSIONS
    from usr.plugins.dj_booth.helpers import bpm_key, library as lib_mod
    p = tmp_path / "x.mp3"
    p.write_bytes(b"\x00" * 1024)
    lib = LibraryManager()
    lib.scan(str(tmp_path))
    monkeypatch.setattr(bpm_key, "detect_bpm",
                        AsyncMock(return_value=120.0) if False else _async_const(120.0))
    monkeypatch.setattr(bpm_key, "detect_key", _async_const("C major"))
    monkeypatch.setattr(lib_mod, "compute_waveform", lambda path, bucket_count=1000: [0.5] * 1000)
    t = await lib.analyze(str(p))
    assert t is not None
    assert t.bpm == 120.0
    assert t.key == "C major"
    assert len(t.waveform_peaks) == 1000


def test_discover_music_dirs_filters_to_existing(tmp_path):
    from usr.plugins.dj_booth.helpers.library import discover_music_dirs
    real = tmp_path / "music"
    real.mkdir()
    (tmp_path / "songs.txt").write_text("not a dir")
    paths = discover_music_dirs(str(real))
    # The configured path should be in the result; the file shouldn't.
    assert str(real) in paths or str(real.resolve()) in paths
    # No duplicates
    assert len(paths) == len(set(paths))


def test_scan_multi_path_dedups_overlapping_roots(tmp_path):
    from usr.plugins.dj_booth.helpers.library import LibraryManager
    a = tmp_path / "a"
    a.mkdir()
    (a / "x.mp3").write_bytes(b"\x00" * 256)
    lib = LibraryManager()
    # Pass the same dir twice — should not double-count
    count = lib.scan([str(a), str(a)])
    assert count == 1
    assert len(lib.tracks) == 1


def test_scan_records_per_path_counts(tmp_path):
    from usr.plugins.dj_booth.helpers.library import LibraryManager
    a = tmp_path / "a"; b = tmp_path / "b"
    a.mkdir(); b.mkdir()
    (a / "1.mp3").write_bytes(b"\x00" * 256)
    (a / "2.mp3").write_bytes(b"\x00" * 256)
    (b / "3.flac").write_bytes(b"\x00" * 256)
    lib = LibraryManager()
    lib.scan([str(a), str(b)])
    assert lib.scanned_path_counts[str(a)] == 2
    assert lib.scanned_path_counts[str(b)] == 1
    assert lib.last_scan_at > 0


def test_scan_ignores_string_for_back_compat(tmp_path):
    """Slice 1 callers passed a single string; that path must still work."""
    from usr.plugins.dj_booth.helpers.library import LibraryManager
    (tmp_path / "x.mp3").write_bytes(b"\x00" * 256)
    lib = LibraryManager()
    count = lib.scan(str(tmp_path))
    assert count == 1
