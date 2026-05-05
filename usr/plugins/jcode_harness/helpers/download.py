"""GitHub release downloader + SHA256 verifier for jcode binaries.

Spec ref: §5.2 — fetch the latest jcode release, pick the asset matching the
detected host target, verify its SHA256 against the published SHA256SUMS,
extract the inner ``jcode`` binary, and chmod +x.

Notes (Spike 0.6 verified against jcode v0.11.10):
- Asset naming: ``jcode-{macos|linux|windows}-{aarch64|x86_64}.{tar.gz|exe}``.
- ``SHA256SUMS`` is published as a release asset alongside the binaries.
- v1 only handles ``.tar.gz``. ``.zip``/``.exe`` raises NotImplementedError
  with a deferred-to-v1.1 message.

No third-party dependencies — uses ``urllib.request`` from the stdlib.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tarfile
import tempfile
import urllib.request
from pathlib import Path

_LATEST_RELEASE_URL = (
    "https://api.github.com/repos/1jehuang/jcode/releases/latest"
)


def fetch_latest_release_metadata() -> dict:
    """Return parsed JSON for the latest jcode GitHub release."""
    req = urllib.request.Request(
        _LATEST_RELEASE_URL,
        headers={"Accept": "application/vnd.github+json"},
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


def pick_asset(release: dict, target: str) -> tuple[str, str]:
    """Return ``(asset_url, sha_url)`` for ``target`` (e.g. ``macos-aarch64``).

    Raises ValueError when no asset matches the target or when SHA256SUMS is
    missing from the release.
    """
    assets = release.get("assets") or []
    asset_url: str | None = None
    sha_url: str | None = None
    for a in assets:
        name = a.get("name", "")
        url = a.get("browser_download_url", "")
        if not url:
            continue
        if name == "SHA256SUMS":
            sha_url = url
            continue
        # Prefer .tar.gz for the target. Skip .exe / .zip — handled below.
        if target in name and name.endswith(".tar.gz"):
            asset_url = url
    if asset_url is None:
        raise ValueError(
            f"no .tar.gz asset for target {target!r} found in release "
            f"{release.get('tag_name', '?')!r}"
        )
    if sha_url is None:
        raise ValueError(
            f"SHA256SUMS asset missing from release "
            f"{release.get('tag_name', '?')!r}"
        )
    return asset_url, sha_url


def _parse_sha256sums(text: str) -> dict[str, str]:
    """Parse a SHA256SUMS file (``<hex>  <filename>`` per line)."""
    result: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(maxsplit=1)
        if len(parts) != 2:
            continue
        digest, name = parts
        # Some tools prefix ``*`` for binary mode -- strip it.
        result[name.lstrip("*").strip()] = digest.lower()
    return result


def _http_get(url: str) -> bytes:
    with urllib.request.urlopen(url) as resp:
        return resp.read()


def download_and_verify(
    asset_url: str, sha_url: str, target_path: Path
) -> None:
    """Download a jcode tarball, verify SHA256, extract the binary.

    The inner ``jcode`` file (whichever path inside the archive) is written
    to ``target_path`` with mode 0o700. Parent directories are created.

    Currently only handles ``.tar.gz`` archives. Raw ``.exe`` or ``.zip``
    assets raise ``NotImplementedError``.
    """
    asset_name = asset_url.rsplit("/", 1)[-1]
    if asset_name.endswith(".zip") or asset_name.endswith(".exe"):
        raise NotImplementedError(
            f"asset {asset_name!r} is not a .tar.gz; Windows native install "
            "is deferred to v1.1 — use WSL2 in the meantime"
        )
    if not asset_name.endswith(".tar.gz"):
        raise NotImplementedError(
            f"unrecognized asset extension for {asset_name!r}"
        )

    tarball = _http_get(asset_url)
    sha_text = _http_get(sha_url).decode("utf-8")
    sums = _parse_sha256sums(sha_text)

    expected = sums.get(asset_name)
    if expected is None:
        raise ValueError(
            f"asset {asset_name!r} not present in SHA256SUMS"
        )
    actual = hashlib.sha256(tarball).hexdigest()
    if actual.lower() != expected.lower():
        raise ValueError(
            f"SHA256 mismatch for {asset_name!r}: "
            f"expected {expected}, got {actual}"
        )

    target_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        archive_path = Path(tmp) / asset_name
        archive_path.write_bytes(tarball)
        with tarfile.open(archive_path, mode="r:gz") as tf:
            jcode_member = None
            for m in tf.getmembers():
                if not m.isfile():
                    continue
                base = os.path.basename(m.name)
                if base == "jcode":
                    jcode_member = m
                    break
            if jcode_member is None:
                raise ValueError(
                    f"no inner 'jcode' binary in archive {asset_name!r}"
                )
            extracted = tf.extractfile(jcode_member)
            if extracted is None:
                raise ValueError(
                    f"could not extract 'jcode' from {asset_name!r}"
                )
            with open(target_path, "wb") as out:
                shutil.copyfileobj(extracted, out)
    target_path.chmod(0o700)
