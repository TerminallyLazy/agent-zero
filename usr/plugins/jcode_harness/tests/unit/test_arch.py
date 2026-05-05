"""Tests for usr.plugins.jcode_harness.helpers.arch."""

from __future__ import annotations

import subprocess

import pytest

from usr.plugins.jcode_harness.helpers import arch


VALID_TARGETS = {
    "macos-aarch64",
    "macos-x86_64",
    "linux-aarch64",
    "linux-x86_64",
    "windows-aarch64",
    "windows-x86_64",
}


def test_returns_known_arch():
    """Whatever the host is, we return one of the six valid strings."""
    assert arch.detect_release_asset_target() in VALID_TARGETS


def test_macos_rosetta_detection(monkeypatch):
    """sysctl returns b'1' even when platform.machine() reports x86_64 (Rosetta)."""
    monkeypatch.setattr(arch.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(arch.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(
        arch.subprocess, "check_output", lambda *a, **kw: b"1\n"
    )
    assert arch.detect_release_asset_target() == "macos-aarch64"


def test_macos_intel_when_sysctl_missing(monkeypatch):
    """sysctl missing on the PATH yields macos-x86_64 fallback."""
    monkeypatch.setattr(arch.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(arch.platform, "machine", lambda: "x86_64")

    def _raise(*a, **kw):
        raise FileNotFoundError("sysctl not found")

    monkeypatch.setattr(arch.subprocess, "check_output", _raise)
    assert arch.detect_release_asset_target() == "macos-x86_64"


def test_macos_intel_when_sysctl_returns_zero(monkeypatch):
    """sysctl returns b'0' -> macos-x86_64."""
    monkeypatch.setattr(arch.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(arch.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(arch.subprocess, "check_output", lambda *a, **kw: b"0\n")
    assert arch.detect_release_asset_target() == "macos-x86_64"


def test_macos_sysctl_calledprocesserror(monkeypatch):
    """sysctl exits non-zero -> fallback to x86_64."""
    monkeypatch.setattr(arch.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(arch.platform, "machine", lambda: "x86_64")

    def _raise(*a, **kw):
        raise subprocess.CalledProcessError(1, "sysctl")

    monkeypatch.setattr(arch.subprocess, "check_output", _raise)
    assert arch.detect_release_asset_target() == "macos-x86_64"


def test_linux_arm64(monkeypatch):
    monkeypatch.setattr(arch.platform, "system", lambda: "Linux")
    monkeypatch.setattr(arch.platform, "machine", lambda: "aarch64")
    assert arch.detect_release_asset_target() == "linux-aarch64"


def test_linux_arm64_alt_name(monkeypatch):
    """`arm64` is also a valid Linux machine string on some distros."""
    monkeypatch.setattr(arch.platform, "system", lambda: "Linux")
    monkeypatch.setattr(arch.platform, "machine", lambda: "arm64")
    assert arch.detect_release_asset_target() == "linux-aarch64"


def test_linux_x86_64(monkeypatch):
    monkeypatch.setattr(arch.platform, "system", lambda: "Linux")
    monkeypatch.setattr(arch.platform, "machine", lambda: "x86_64")
    assert arch.detect_release_asset_target() == "linux-x86_64"


def test_windows_arm64(monkeypatch):
    monkeypatch.setattr(arch.platform, "system", lambda: "Windows")
    monkeypatch.setattr(arch.platform, "machine", lambda: "ARM64")
    assert arch.detect_release_asset_target() == "windows-aarch64"


def test_windows_x86_64(monkeypatch):
    monkeypatch.setattr(arch.platform, "system", lambda: "Windows")
    monkeypatch.setattr(arch.platform, "machine", lambda: "AMD64")
    assert arch.detect_release_asset_target() == "windows-x86_64"


def test_unsupported_os_raises(monkeypatch):
    monkeypatch.setattr(arch.platform, "system", lambda: "FreeBSD")
    with pytest.raises(RuntimeError, match="unsupported OS"):
        arch.detect_release_asset_target()
