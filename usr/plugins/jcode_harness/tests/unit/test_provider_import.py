"""Tests for usr.plugins.jcode_harness.helpers.provider_import.

Covers Tasks 6.1–6.4 of the jcode-harness plan.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Task 6.1 — discover_a0_providers
# ---------------------------------------------------------------------------


def test_discover_returns_empty_when_yaml_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "usr.plugins.jcode_harness.helpers.provider_import._a0_yaml_path",
        lambda: tmp_path / "does-not-exist.yaml",
    )
    from usr.plugins.jcode_harness.helpers.provider_import import (
        discover_a0_providers,
    )

    assert discover_a0_providers() == []


def test_discover_parses_chat_section(monkeypatch, tmp_path):
    yaml_path = tmp_path / "model_providers.yaml"
    yaml_path.write_text(
        """
chat:
  acme:
    name: Acme LLM
    litellm_provider: openai
    kwargs:
      api_base: https://acme.example.com/v1
      default_model: acme-fast
      api_key_env: ACME_KEY
"""
    )
    monkeypatch.setattr(
        "usr.plugins.jcode_harness.helpers.provider_import._a0_yaml_path",
        lambda: yaml_path,
    )
    from usr.plugins.jcode_harness.helpers.provider_import import (
        discover_a0_providers,
    )

    providers = discover_a0_providers()
    assert len(providers) == 1
    p = providers[0]
    assert p["id"] == "acme"
    assert p["name"] == "Acme LLM"
    assert p["kind"] == "chat"
    assert p["api_base"] == "https://acme.example.com/v1"
    assert p["default_model"] == "acme-fast"
    assert p["api_key_env"] == "ACME_KEY"


def test_discover_skips_provider_without_api_base(monkeypatch, tmp_path):
    yaml_path = tmp_path / "model_providers.yaml"
    yaml_path.write_text(
        """
chat:
  no_base:
    name: No Base
    litellm_provider: openai
  has_base:
    name: Has Base
    kwargs:
      api_base: https://has.example.com/v1
"""
    )
    monkeypatch.setattr(
        "usr.plugins.jcode_harness.helpers.provider_import._a0_yaml_path",
        lambda: yaml_path,
    )
    from usr.plugins.jcode_harness.helpers.provider_import import (
        discover_a0_providers,
    )

    ids = {p["id"] for p in discover_a0_providers()}
    assert ids == {"has_base"}


def test_discover_walks_multiple_kinds(monkeypatch, tmp_path):
    yaml_path = tmp_path / "model_providers.yaml"
    yaml_path.write_text(
        """
chat:
  chat_one:
    kwargs:
      api_base: https://chat.example.com/v1
embedding:
  embed_one:
    kwargs:
      api_base: https://embed.example.com/v1
"""
    )
    monkeypatch.setattr(
        "usr.plugins.jcode_harness.helpers.provider_import._a0_yaml_path",
        lambda: yaml_path,
    )
    from usr.plugins.jcode_harness.helpers.provider_import import (
        discover_a0_providers,
    )

    by_id = {p["id"]: p for p in discover_a0_providers()}
    assert set(by_id) == {"chat_one", "embed_one"}
    assert by_id["chat_one"]["kind"] == "chat"
    assert by_id["embed_one"]["kind"] == "embedding"


def test_default_api_key_env_derived_from_pid(monkeypatch, tmp_path):
    yaml_path = tmp_path / "model_providers.yaml"
    yaml_path.write_text(
        """
chat:
  bareprov:
    kwargs:
      api_base: https://bare.example.com/v1
"""
    )
    monkeypatch.setattr(
        "usr.plugins.jcode_harness.helpers.provider_import._a0_yaml_path",
        lambda: yaml_path,
    )
    from usr.plugins.jcode_harness.helpers.provider_import import (
        discover_a0_providers,
    )

    p = discover_a0_providers()[0]
    assert p["api_key_env"] == "BAREPROV_API_KEY"


# ---------------------------------------------------------------------------
# Task 6.2 — add_jcode_profile / list_jcode_profiles
# ---------------------------------------------------------------------------


def _ok_run(stdout: str = '{"ok": true}', stderr: str = "", returncode: int = 0):
    return MagicMock(returncode=returncode, stdout=stdout, stderr=stderr)


def test_provider_add_uses_env_not_argv(monkeypatch):
    captured_argv: list[list[str]] = []
    captured_env: list[dict] = []

    def fake_run(argv, env=None, **kw):
        captured_argv.append(list(argv))
        captured_env.append(dict(env or {}))
        return _ok_run()

    monkeypatch.setattr("subprocess.run", fake_run)
    from usr.plugins.jcode_harness.helpers.provider_import import (
        add_jcode_profile,
    )

    add_jcode_profile(
        "/bin/jcode",
        "_a0_imported_acme",
        "https://acme/v1",
        "gpt-4",
        "SECRET_KEY_VAL",
    )
    argv = captured_argv[0]
    env = captured_env[0]
    # Critical security check: API key never appears in argv anywhere.
    assert "SECRET_KEY_VAL" not in " ".join(argv)
    assert "--api-key-env" in argv
    idx = argv.index("--api-key-env")
    env_var_name = argv[idx + 1]
    assert env_var_name.startswith("JCODE_PROVIDER_")
    assert env_var_name.endswith("_API_KEY")
    assert env[env_var_name] == "SECRET_KEY_VAL"
    # The model and base-url are in argv (non-secret).
    assert "gpt-4" in argv
    assert "https://acme/v1" in argv


def test_provider_add_env_var_name_format(monkeypatch):
    captured_argv: list[list[str]] = []

    def fake_run(argv, env=None, **kw):
        captured_argv.append(list(argv))
        return _ok_run()

    monkeypatch.setattr("subprocess.run", fake_run)
    from usr.plugins.jcode_harness.helpers.provider_import import (
        add_jcode_profile,
    )

    add_jcode_profile(
        "/bin/jcode",
        "_a0_imported_my-prov",
        "https://x/v1",
        "m1",
        "K",
    )
    argv = captured_argv[0]
    idx = argv.index("--api-key-env")
    env_var_name = argv[idx + 1]
    # Hyphens are converted to underscores; entire name is uppercased.
    assert env_var_name == "JCODE_PROVIDER__A0_IMPORTED_MY_PROV_API_KEY"


def test_provider_add_rejects_unprefixed_name(monkeypatch):
    monkeypatch.setattr("subprocess.run", lambda *a, **k: _ok_run())
    from usr.plugins.jcode_harness.helpers.provider_import import (
        add_jcode_profile,
    )

    with pytest.raises(ValueError):
        add_jcode_profile(
            "/bin/jcode", "bare_name", "https://x/v1", "m", "k"
        )


def test_provider_add_retries_without_json_overwrite_on_rejection(monkeypatch):
    calls: list[list[str]] = []

    def fake_run(argv, env=None, **kw):
        calls.append(list(argv))
        if len(calls) == 1:
            return _ok_run(
                stdout="",
                stderr="error: unrecognized argument: --json",
                returncode=2,
            )
        return _ok_run()

    monkeypatch.setattr("subprocess.run", fake_run)
    from usr.plugins.jcode_harness.helpers.provider_import import (
        add_jcode_profile,
    )

    add_jcode_profile(
        "/bin/jcode",
        "_a0_imported_x",
        "https://x/v1",
        "m",
        "k",
    )
    assert len(calls) == 2
    second = calls[1]
    assert "--json" not in second
    assert "--overwrite" not in second


def test_provider_add_raises_on_genuine_failure(monkeypatch):
    def fake_run(argv, env=None, **kw):
        return _ok_run(
            stdout="",
            stderr="connection refused",
            returncode=3,
        )

    monkeypatch.setattr("subprocess.run", fake_run)
    from usr.plugins.jcode_harness.helpers.provider_import import (
        add_jcode_profile,
    )

    with pytest.raises(RuntimeError, match="connection refused"):
        add_jcode_profile(
            "/bin/jcode", "_a0_imported_x", "https://x/v1", "m", "k"
        )


def test_list_jcode_profiles_returns_parsed_json(monkeypatch):
    payload = [{"name": "_a0_imported_acme"}, {"name": "userprof"}]

    def fake_run(argv, **kw):
        assert argv[1:] == ["provider", "list", "--json"]
        return _ok_run(stdout=json.dumps(payload))

    monkeypatch.setattr("subprocess.run", fake_run)
    from usr.plugins.jcode_harness.helpers.provider_import import (
        list_jcode_profiles,
    )

    assert list_jcode_profiles("/bin/jcode") == payload


# ---------------------------------------------------------------------------
# Task 6.3 — import_a0_providers
# ---------------------------------------------------------------------------


def _provider(pid: str, **overrides) -> dict:
    base = {
        "id": pid,
        "name": pid,
        "kind": "chat",
        "api_base": f"https://{pid}.example.com/v1",
        "default_model": "m1",
        "api_key_env": f"{pid.upper()}_API_KEY",
    }
    base.update(overrides)
    return base


def test_import_skips_user_owned_collision(monkeypatch):
    monkeypatch.setattr(
        "usr.plugins.jcode_harness.helpers.provider_import.list_jcode_profiles",
        lambda b: [{"name": "acme"}],
    )
    from usr.plugins.jcode_harness.helpers.provider_import import (
        import_a0_providers,
    )

    result = import_a0_providers(
        "/bin/jcode",
        providers=[_provider("acme")],
        api_keys={"acme": "K"},
    )
    assert "acme" in result["skipped"]
    assert "collision" in result["skipped"]["acme"]
    assert result["imported"] == []


def test_import_skips_missing_api_key(monkeypatch):
    monkeypatch.setattr(
        "usr.plugins.jcode_harness.helpers.provider_import.list_jcode_profiles",
        lambda b: [],
    )
    from usr.plugins.jcode_harness.helpers.provider_import import (
        import_a0_providers,
    )

    result = import_a0_providers(
        "/bin/jcode",
        providers=[_provider("acme")],
        api_keys={},
    )
    assert "acme" in result["skipped"]
    assert "API key" in result["skipped"]["acme"]


def test_import_skips_missing_default_model(monkeypatch):
    monkeypatch.setattr(
        "usr.plugins.jcode_harness.helpers.provider_import.list_jcode_profiles",
        lambda b: [],
    )
    from usr.plugins.jcode_harness.helpers.provider_import import (
        import_a0_providers,
    )

    result = import_a0_providers(
        "/bin/jcode",
        providers=[_provider("acme", default_model=None)],
        api_keys={"acme": "K"},
    )
    assert "acme" in result["skipped"]
    assert "default model" in result["skipped"]["acme"]


def test_import_succeeds_for_well_formed_provider(monkeypatch):
    monkeypatch.setattr(
        "usr.plugins.jcode_harness.helpers.provider_import.list_jcode_profiles",
        lambda b: [],
    )
    calls: list[dict] = []

    def fake_add(jcode_bin, profile_name, base_url, model, api_key, overwrite=True):
        calls.append(
            {
                "jcode_bin": jcode_bin,
                "profile_name": profile_name,
                "base_url": base_url,
                "model": model,
                "api_key": api_key,
                "overwrite": overwrite,
            }
        )
        return {"ok": True}

    monkeypatch.setattr(
        "usr.plugins.jcode_harness.helpers.provider_import.add_jcode_profile",
        fake_add,
    )
    from usr.plugins.jcode_harness.helpers.provider_import import (
        import_a0_providers,
    )

    result = import_a0_providers(
        "/bin/jcode",
        providers=[_provider("acme")],
        api_keys={"acme": "K"},
    )
    assert result["imported"] == ["acme"]
    assert result["skipped"] == {}
    assert len(calls) == 1
    assert calls[0]["profile_name"] == "_a0_imported_acme"
    assert calls[0]["api_key"] == "K"
    assert calls[0]["overwrite"] is True


def test_import_handles_list_failure_gracefully(monkeypatch):
    def boom(b):
        raise subprocess.CalledProcessError(1, ["jcode"])

    monkeypatch.setattr(
        "usr.plugins.jcode_harness.helpers.provider_import.list_jcode_profiles",
        boom,
    )
    monkeypatch.setattr(
        "usr.plugins.jcode_harness.helpers.provider_import.add_jcode_profile",
        lambda *a, **k: {"ok": True},
    )
    from usr.plugins.jcode_harness.helpers.provider_import import (
        import_a0_providers,
    )

    result = import_a0_providers(
        "/bin/jcode",
        providers=[_provider("acme")],
        api_keys={"acme": "K"},
    )
    # No collision detected -> import proceeds.
    assert result["imported"] == ["acme"]


# ---------------------------------------------------------------------------
# Task 6.4 — purge_imported_profiles
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_home(monkeypatch, tmp_path):
    """Redirect Path.home() and provider_import._config_path() to tmp_path."""
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    cfg = tmp_path / ".jcode" / "config.toml"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        "usr.plugins.jcode_harness.helpers.provider_import._config_path",
        lambda: cfg,
    )
    return tmp_path


def _patch_supervisor(monkeypatch, running: bool):
    stop_calls = {"count": 0}

    class FakeSup:
        def __init__(self, *a, **kw):
            pass

        def is_running(self):
            return running

        def stop(self):
            stop_calls["count"] += 1

    monkeypatch.setattr(
        "usr.plugins.jcode_harness.helpers.daemon.DaemonSupervisor",
        FakeSup,
    )
    return stop_calls


def _write_config(path: Path, body: str) -> None:
    path.write_text(body)


def test_purge_removes_prefixed_profiles_only(monkeypatch, fake_home):
    cfg = fake_home / ".jcode" / "config.toml"
    _write_config(
        cfg,
        """
[providers._a0_imported_x]
base_url = "https://x/v1"
model = "m"

[providers._a0_imported_y]
base_url = "https://y/v1"
model = "m"

[providers.userprof]
base_url = "https://u/v1"
model = "m"
""",
    )
    _patch_supervisor(monkeypatch, running=False)
    from usr.plugins.jcode_harness.helpers.provider_import import (
        purge_imported_profiles,
    )

    purged = purge_imported_profiles("/bin/jcode")
    assert sorted(purged) == ["_a0_imported_x", "_a0_imported_y"]

    import tomllib

    data = tomllib.loads(cfg.read_text())
    assert set(data["providers"]) == {"userprof"}


def test_purge_leaves_user_profiles_untouched(monkeypatch, fake_home):
    cfg = fake_home / ".jcode" / "config.toml"
    _write_config(
        cfg,
        """
[providers.userprof]
base_url = "https://u/v1"
model = "m"
""",
    )
    _patch_supervisor(monkeypatch, running=False)
    from usr.plugins.jcode_harness.helpers.provider_import import (
        purge_imported_profiles,
    )

    purged = purge_imported_profiles("/bin/jcode")
    assert purged == []

    import tomllib

    data = tomllib.loads(cfg.read_text())
    assert "userprof" in data["providers"]


def test_purge_resets_default_provider_when_pointed_at_removed(
    monkeypatch, fake_home
):
    cfg = fake_home / ".jcode" / "config.toml"
    _write_config(
        cfg,
        """
[provider]
default_provider = "_a0_imported_x"

[providers._a0_imported_x]
base_url = "https://x/v1"
model = "m"
""",
    )
    _patch_supervisor(monkeypatch, running=False)
    from usr.plugins.jcode_harness.helpers.provider_import import (
        purge_imported_profiles,
    )

    purge_imported_profiles("/bin/jcode")

    import tomllib

    data = tomllib.loads(cfg.read_text())
    assert data["provider"]["default_provider"] == "auto"


def test_purge_removes_env_files(monkeypatch, fake_home):
    cfg = fake_home / ".jcode" / "config.toml"
    _write_config(
        cfg,
        """
[providers._a0_imported_x]
base_url = "https://x/v1"
model = "m"
""",
    )
    env_file = fake_home / ".config" / "jcode" / "provider-_a0_imported_x.env"
    env_file.parent.mkdir(parents=True, exist_ok=True)
    env_file.write_text("KEY=val")

    _patch_supervisor(monkeypatch, running=False)
    from usr.plugins.jcode_harness.helpers.provider_import import (
        purge_imported_profiles,
    )

    purge_imported_profiles("/bin/jcode")
    assert not env_file.exists()


def test_purge_no_op_when_config_missing(monkeypatch, fake_home):
    # Do not write any config file.
    _patch_supervisor(monkeypatch, running=False)
    from usr.plugins.jcode_harness.helpers.provider_import import (
        purge_imported_profiles,
    )

    assert purge_imported_profiles("/bin/jcode") == []


def test_purge_stops_running_daemon_first(monkeypatch, fake_home):
    cfg = fake_home / ".jcode" / "config.toml"
    _write_config(
        cfg,
        """
[providers._a0_imported_x]
base_url = "https://x/v1"
""",
    )
    stop_calls = _patch_supervisor(monkeypatch, running=True)
    from usr.plugins.jcode_harness.helpers.provider_import import (
        purge_imported_profiles,
    )

    purge_imported_profiles("/bin/jcode")
    assert stop_calls["count"] == 1


def test_purge_skips_stop_when_not_running(monkeypatch, fake_home):
    cfg = fake_home / ".jcode" / "config.toml"
    _write_config(
        cfg,
        """
[providers._a0_imported_x]
base_url = "https://x/v1"
""",
    )
    stop_calls = _patch_supervisor(monkeypatch, running=False)
    from usr.plugins.jcode_harness.helpers.provider_import import (
        purge_imported_profiles,
    )

    purge_imported_profiles("/bin/jcode")
    assert stop_calls["count"] == 0
