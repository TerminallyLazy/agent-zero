import os
import tempfile
from pathlib import Path
import pytest
from usr.plugins.dj_booth.helpers.library import LibraryManager, Track


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
