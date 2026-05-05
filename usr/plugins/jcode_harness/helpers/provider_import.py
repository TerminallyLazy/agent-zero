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

import json
import os
import subprocess
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


# ---------------------------------------------------------------------------
# Task 6.2 — add_jcode_profile / list_jcode_profiles
# ---------------------------------------------------------------------------


def add_jcode_profile(
    jcode_bin: str,
    profile_name: str,
    base_url: str,
    model: str,
    api_key: str,
    overwrite: bool = True,
) -> dict:
    """Add an OpenAI-compatible jcode provider profile.

    The API key is passed via a private env var (``JCODE_PROVIDER_<NAME>_API_KEY``)
    that exists only in the spawned subprocess's environment — never argv,
    never shell history, never persisted in the parent process.

    Per Spike 0.4, ``--api-key-stdin`` does not exist on jcode v0.11.10, and
    the visibility of ``--json`` / ``--overwrite`` on ``provider add`` is not
    confirmed. We attempt them and retry without on rejection.
    """
    if not profile_name.startswith(PLUGIN_PROFILE_PREFIX):
        raise ValueError(
            f"plugin-managed profiles must start with {PLUGIN_PROFILE_PREFIX}"
        )
    env_var = (
        f"JCODE_PROVIDER_{profile_name.upper().replace('-', '_')}_API_KEY"
    )
    child_env = dict(os.environ, **{env_var: api_key})
    base_cmd = [
        jcode_bin,
        "provider",
        "add",
        profile_name,
        "--base-url",
        base_url,
        "--model",
        model,
        "--api-key-env",
        env_var,
    ]
    cmd_full = base_cmd + ["--json"] + (["--overwrite"] if overwrite else [])
    result = subprocess.run(
        cmd_full, env=child_env, capture_output=True, text=True
    )
    if result.returncode != 0 and (
        "--json" in result.stderr
        or "--overwrite" in result.stderr
        or "unrecognized" in result.stderr
        or "unexpected" in result.stderr
    ):
        result = subprocess.run(
            base_cmd, env=child_env, capture_output=True, text=True
        )
    if result.returncode != 0:
        raise RuntimeError(
            f"jcode provider add failed: {result.stderr.strip()}"
        )
    try:
        return (
            json.loads(result.stdout)
            if result.stdout.strip()
            else {"ok": True}
        )
    except json.JSONDecodeError:
        return {"ok": True, "stdout": result.stdout}


def list_jcode_profiles(jcode_bin: str) -> list[dict]:
    """List jcode provider profiles via ``provider list --json``.

    jcode v0.11.x returns ``{"providers": [{"id": str, ...}, ...]}``; older
    or future shapes may return a bare list. Normalise both to a list of
    profile dicts. The canonical key on each profile is ``"id"``.
    """
    result = subprocess.run(
        [jcode_bin, "provider", "list", "--json"],
        capture_output=True,
        text=True,
        check=True,
    )
    data = json.loads(result.stdout)
    if isinstance(data, dict):
        return list(data.get("providers", []))
    if isinstance(data, list):
        return data
    return []


# ---------------------------------------------------------------------------
# Task 6.3 — collision-safe bulk import
# ---------------------------------------------------------------------------


def import_a0_providers(
    jcode_bin: str,
    providers: list[dict] | None = None,
    api_keys: dict[str, str] | None = None,
) -> dict:
    """Bulk-import A0 providers into jcode as ``_a0_imported_*`` profiles.

    Returns ``{imported: [provider_id, ...], skipped: {provider_id: reason}}``.

    Skip rules:
      - name collision with a USER-OWNED jcode profile (no plugin prefix)
      - missing API key (env var unset)
      - missing default model

    Idempotent for plugin-owned profiles via ``add_jcode_profile``'s
    overwrite path. If ``list_jcode_profiles`` fails, we proceed with an
    empty user-owned set rather than aborting the whole import.
    """
    if providers is None:
        providers = discover_a0_providers()
    if api_keys is None:
        api_keys = {}
        for p in providers:
            env = p["api_key_env"]
            if env in os.environ:
                api_keys[p["id"]] = os.environ[env]

    try:
        existing = list_jcode_profiles(jcode_bin)
    except (subprocess.CalledProcessError, OSError, json.JSONDecodeError):
        existing = []
    # jcode profile shape uses "id" (verified against v0.11.10
    # `provider list --json`); fall back to "name" for forward-compat.
    def _profile_id(prof: dict) -> str:
        return prof.get("id") or prof.get("name") or ""

    user_owned = {
        _profile_id(p)
        for p in existing
        if _profile_id(p) and not _profile_id(p).startswith(PLUGIN_PROFILE_PREFIX)
    }

    imported: list[str] = []
    skipped: dict[str, str] = {}

    for p in providers:
        pid = p["id"]
        if pid in user_owned:
            skipped[pid] = "name collision with user-owned profile"
            continue
        if pid not in api_keys:
            skipped[pid] = "no API key in environment"
            continue
        if not p.get("default_model"):
            skipped[pid] = "no default model"
            continue
        try:
            add_jcode_profile(
                jcode_bin,
                f"{PLUGIN_PROFILE_PREFIX}{pid}",
                p["api_base"],
                p["default_model"],
                api_keys[pid],
                overwrite=True,
            )
            imported.append(pid)
        except (ValueError, RuntimeError) as e:
            skipped[pid] = str(e)

    return {"imported": imported, "skipped": skipped}


# ---------------------------------------------------------------------------
# Task 6.4 — purge plugin-managed profiles via direct config edit (Spike 0.9)
# ---------------------------------------------------------------------------


def _config_path() -> Path:
    """Return jcode's primary config TOML path."""
    return Path.home() / ".jcode" / "config.toml"


def purge_imported_profiles(jcode_bin: str) -> list[str]:
    """Remove all plugin-prefixed profiles from ``~/.jcode/config.toml``.

    Spike 0.9: jcode v0.11.10 has no ``provider remove`` subcommand, so we
    edit the config TOML directly. The daemon must be stopped first to avoid
    racing with jcode's own config writer.

    Returns the list of profile names removed.
    """
    import sys

    if sys.version_info >= (3, 11):
        import tomllib
    else:  # pragma: no cover — project requires 3.11+
        import tomli as tomllib  # type: ignore
    import tomli_w

    from usr.plugins.jcode_harness.helpers.daemon import DaemonSupervisor
    from usr.plugins.jcode_harness.helpers.paths import jcode_runtime_dir

    sup = DaemonSupervisor(jcode_bin, jcode_runtime_dir())
    if sup.is_running():
        sup.stop()

    config_path = _config_path()
    purged: list[str] = []
    if not config_path.exists():
        return purged

    data = tomllib.loads(config_path.read_text())
    providers = data.get("providers", {})
    to_remove = [
        n for n in providers if n.startswith(PLUGIN_PROFILE_PREFIX)
    ]
    if not to_remove:
        return purged

    for n in to_remove:
        del providers[n]
        purged.append(n)
        env_file = (
            Path.home() / ".config" / "jcode" / f"provider-{n}.env"
        )
        env_file.unlink(missing_ok=True)

    if data.get("provider", {}).get("default_provider") in purged:
        data["provider"]["default_provider"] = "auto"

    config_path.write_text(tomli_w.dumps(data))
    config_path.chmod(0o600)
    return purged
