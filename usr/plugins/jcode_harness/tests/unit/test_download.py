"""Tests for usr.plugins.jcode_harness.helpers.download."""

from __future__ import annotations

import hashlib
import io
import json
import tarfile
from pathlib import Path

import pytest

from usr.plugins.jcode_harness.helpers import download


# -- helpers ----------------------------------------------------------------


class _FakeResp:
    def __init__(self, body: bytes):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _make_tarball(inner_path: str, payload: bytes) -> bytes:
    """Build a .tar.gz containing ``inner_path`` -> ``payload``."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        info = tarfile.TarInfo(name=inner_path)
        info.size = len(payload)
        info.mode = 0o755
        tf.addfile(info, io.BytesIO(payload))
    return buf.getvalue()


def _sample_release() -> dict:
    return {
        "tag_name": "v0.11.10",
        "assets": [
            {
                "name": "jcode-macos-aarch64.tar.gz",
                "browser_download_url": "https://example.invalid/jcode-macos-aarch64.tar.gz",
            },
            {
                "name": "jcode-macos-x86_64.tar.gz",
                "browser_download_url": "https://example.invalid/jcode-macos-x86_64.tar.gz",
            },
            {
                "name": "jcode-linux-aarch64.tar.gz",
                "browser_download_url": "https://example.invalid/jcode-linux-aarch64.tar.gz",
            },
            {
                "name": "jcode-linux-x86_64.tar.gz",
                "browser_download_url": "https://example.invalid/jcode-linux-x86_64.tar.gz",
            },
            {
                "name": "jcode-windows-x86_64.exe",
                "browser_download_url": "https://example.invalid/jcode-windows-x86_64.exe",
            },
            {
                "name": "SHA256SUMS",
                "browser_download_url": "https://example.invalid/SHA256SUMS",
            },
        ],
    }


# -- fetch_latest_release_metadata -----------------------------------------


def test_fetch_latest_release_returns_parsed_json(monkeypatch):
    payload = json.dumps({"tag_name": "v9.9.9", "assets": []}).encode("utf-8")

    def fake_urlopen(req, *a, **kw):
        # Accept Request object
        return _FakeResp(payload)

    monkeypatch.setattr(download.urllib.request, "urlopen", fake_urlopen)
    out = download.fetch_latest_release_metadata()
    assert out["tag_name"] == "v9.9.9"


# -- pick_asset -------------------------------------------------------------


def test_pick_asset_finds_macos_aarch64():
    rel = _sample_release()
    asset_url, sha_url = download.pick_asset(rel, "macos-aarch64")
    assert asset_url.endswith("jcode-macos-aarch64.tar.gz")
    assert sha_url.endswith("SHA256SUMS")


def test_pick_asset_finds_linux_x86_64():
    rel = _sample_release()
    asset_url, _ = download.pick_asset(rel, "linux-x86_64")
    assert asset_url.endswith("jcode-linux-x86_64.tar.gz")


def test_pick_asset_raises_for_unknown_target():
    rel = _sample_release()
    with pytest.raises(ValueError, match="no .tar.gz asset"):
        download.pick_asset(rel, "plan9-riscv64")


def test_pick_asset_raises_when_sha_missing():
    rel = {
        "tag_name": "v0",
        "assets": [
            {
                "name": "jcode-linux-x86_64.tar.gz",
                "browser_download_url": "https://example.invalid/x.tar.gz",
            }
        ],
    }
    with pytest.raises(ValueError, match="SHA256SUMS asset missing"):
        download.pick_asset(rel, "linux-x86_64")


# -- download_and_verify ----------------------------------------------------


def test_download_verifies_sha256(monkeypatch, tmp_path):
    payload = b"#!/bin/sh\necho hi\n"
    tarball = _make_tarball("jcode-linux-x86_64/jcode", payload)
    digest = hashlib.sha256(tarball).hexdigest()
    sha_text = f"{digest}  jcode-linux-x86_64.tar.gz\n"

    def fake_get(url):
        if url.endswith(".tar.gz"):
            return tarball
        return sha_text.encode("utf-8")

    monkeypatch.setattr(download, "_http_get", fake_get)
    target = tmp_path / "jcode"
    download.download_and_verify(
        "https://example.invalid/jcode-linux-x86_64.tar.gz",
        "https://example.invalid/SHA256SUMS",
        target,
    )
    assert target.exists()
    assert target.read_bytes() == payload


def test_download_rejects_mismatched_sha256(monkeypatch, tmp_path):
    tarball = _make_tarball("jcode-linux-x86_64/jcode", b"hello")
    bogus = "0" * 64
    sha_text = f"{bogus}  jcode-linux-x86_64.tar.gz\n"

    def fake_get(url):
        if url.endswith(".tar.gz"):
            return tarball
        return sha_text.encode("utf-8")

    monkeypatch.setattr(download, "_http_get", fake_get)
    target = tmp_path / "jcode"
    with pytest.raises(ValueError, match="SHA256 mismatch"):
        download.download_and_verify(
            "https://example.invalid/jcode-linux-x86_64.tar.gz",
            "https://example.invalid/SHA256SUMS",
            target,
        )
    assert not target.exists()


def test_download_rejects_when_asset_missing_from_sums(monkeypatch, tmp_path):
    tarball = _make_tarball("jcode/jcode", b"x")
    sha_text = "deadbeef  some-other-asset.tar.gz\n"

    def fake_get(url):
        if url.endswith(".tar.gz"):
            return tarball
        return sha_text.encode("utf-8")

    monkeypatch.setattr(download, "_http_get", fake_get)
    target = tmp_path / "jcode"
    with pytest.raises(ValueError, match="not present in SHA256SUMS"):
        download.download_and_verify(
            "https://example.invalid/jcode-linux-x86_64.tar.gz",
            "https://example.invalid/SHA256SUMS",
            target,
        )


def test_download_extracts_jcode_binary(monkeypatch, tmp_path):
    payload = b"BINARY-CONTENT"
    tarball = _make_tarball("jcode-macos-aarch64/jcode", payload)
    digest = hashlib.sha256(tarball).hexdigest()
    sha_text = f"{digest}  jcode-macos-aarch64.tar.gz\n"

    monkeypatch.setattr(
        download,
        "_http_get",
        lambda url: tarball if url.endswith(".tar.gz") else sha_text.encode(),
    )
    target = tmp_path / "bin" / "jcode"
    download.download_and_verify(
        "https://example.invalid/jcode-macos-aarch64.tar.gz",
        "https://example.invalid/SHA256SUMS",
        target,
    )
    assert target.read_bytes() == payload
    # 0o700 set
    mode = target.stat().st_mode & 0o777
    assert mode == 0o700


def test_download_raises_when_inner_jcode_missing(monkeypatch, tmp_path):
    # tarball has no "jcode" file
    tarball = _make_tarball("jcode-linux-x86_64/README.md", b"hi")
    digest = hashlib.sha256(tarball).hexdigest()
    sha_text = f"{digest}  jcode-linux-x86_64.tar.gz\n"

    monkeypatch.setattr(
        download,
        "_http_get",
        lambda url: tarball if url.endswith(".tar.gz") else sha_text.encode(),
    )
    target = tmp_path / "jcode"
    with pytest.raises(ValueError, match="no inner 'jcode' binary"):
        download.download_and_verify(
            "https://example.invalid/jcode-linux-x86_64.tar.gz",
            "https://example.invalid/SHA256SUMS",
            target,
        )


def test_download_rejects_exe_asset(tmp_path):
    with pytest.raises(NotImplementedError, match="WSL2"):
        download.download_and_verify(
            "https://example.invalid/jcode-windows-x86_64.exe",
            "https://example.invalid/SHA256SUMS",
            tmp_path / "jcode.exe",
        )


def test_download_rejects_zip_asset(tmp_path):
    with pytest.raises(NotImplementedError):
        download.download_and_verify(
            "https://example.invalid/jcode-windows-x86_64.zip",
            "https://example.invalid/SHA256SUMS",
            tmp_path / "jcode.exe",
        )
