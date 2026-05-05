"""A0 → jcode provider importer.

Spec ref: §5.5, §8.2.

Discovers chat/embedding providers declared in A0's
``conf/model_providers.yaml`` and exposes them as plugin-managed jcode
provider profiles. All profiles created by this module are prefixed with
``_a0_imported_`` so they are unambiguously distinguishable from
user-owned jcode profiles and can be safely purged on plugin uninstall.

Spike findings baked in (jcode v0.11.10):
  - Spike 0.4: ``--api-key-stdin`` does not exist; we use ``--api-key-env``
    with a private env-var injection. The key never appears in argv.
  - Spike 0.4: ``--json`` and ``--overwrite`` are not visible in
    ``provider add --help``; we attempt them and retry without on
    rejection.
  - Spike 0.9: ``provider remove`` subcommand does not exist; uninstall
    edits ``~/.jcode/config.toml`` directly after stopping the daemon.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml


PLUGIN_PROFILE_PREFIX = "_a0_imported_"


# ---------------------------------------------------------------------------
# Task 6.1 — discover_a0_providers
# ---------------------------------------------------------------------------


def _a0_yaml_path() -> Path:
    """Resolve the A0 ``conf/model_providers.yaml`` from this file's location.

    The plugin lives at ``<repo>/usr/plugins/jcode_harness/helpers/``, so four
    ``..`` hops climb out to the repo root.
    """
    return Path(__file__).resolve().parents[4] / "conf" / "model_providers.yaml"


def _first_model_from_settings(pid: str) -> str | None:
    """Fall back to the user's selected model for ``pid`` from A0 settings.

    Stubbed for now — the importer simply skips providers without a usable
    default. Wiring this into ``python/helpers/settings.py`` is a follow-up.
    """
    return None


def discover_a0_providers() -> list[dict]:
    """Return one dict per A0 provider with an ``api_base`` configured.

    Each dict has: ``id``, ``name``, ``kind`` (chat/embedding), ``api_base``,
    ``default_model``, ``api_key_env``. Providers without an ``api_base`` are
    skipped — jcode's OpenAI-compatible profile shape requires one.
    """
    p = _a0_yaml_path()
    if not p.exists():
        return []

    data = yaml.safe_load(p.read_text()) or {}
    out: list[dict] = []
    for kind, providers in data.items():
        if not isinstance(providers, dict):
            continue
        for pid, cfg in providers.items():
            if not isinstance(cfg, dict):
                continue
            kwargs = cfg.get("kwargs") or {}
            api_base = kwargs.get("api_base")
            if not api_base:
                continue
            out.append(
                {
                    "id": pid,
                    "name": cfg.get("name", pid),
                    "kind": kind,
                    "api_base": api_base,
                    "default_model": kwargs.get("default_model")
                    or _first_model_from_settings(pid),
                    "api_key_env": kwargs.get("api_key_env")
                    or f"{pid.upper()}_API_KEY",
                }
            )
    return out
