"""Spec §8.2: API keys must NEVER appear in subprocess argv.

The Spike 0.4 fix uses ``--api-key-env`` plus a private env var injected only
into the spawned subprocess's environment. The contract is also verified by
``tests/unit/test_provider_import.py::test_provider_add_uses_env_not_argv``;
this smoke test re-asserts the contract at the security tier in case the
unit-level test gets renamed, deleted, or refactored — argv leakage is a
hard security regression and we want a tier that catches it independently.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


def test_add_jcode_profile_never_emits_key_to_argv(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_argv: list[list[str]] = []
    captured_env: list[dict] = []

    def fake_run(argv, env=None, **kw):
        captured_argv.append(list(argv))
        captured_env.append(dict(env or {}))
        return MagicMock(returncode=0, stdout='{"ok": true}', stderr="")

    monkeypatch.setattr("subprocess.run", fake_run)

    from usr.plugins.jcode_harness.helpers.provider_import import (
        add_jcode_profile,
    )

    secret = "SECRET_KEY_a1b2c3d4e5f6"
    add_jcode_profile(
        "/bin/jcode",
        "_a0_imported_test",
        "https://example.com/v1",
        "fake-model",
        secret,
        overwrite=True,
    )

    assert captured_argv, "subprocess.run was not called"
    argv = captured_argv[0]
    full_argv_text = " ".join(argv)

    # Hard requirement: the literal secret value must NEVER appear in argv.
    assert secret not in full_argv_text, (
        f"API key leaked into argv: {full_argv_text}"
    )

    # The contract is: pass the env-var NAME via --api-key-env and only put
    # the actual key in child env.
    assert "--api-key-env" in argv
    env_var_name = argv[argv.index("--api-key-env") + 1]
    assert env_var_name.startswith("JCODE_PROVIDER_"), (
        f"unexpected env var name: {env_var_name}"
    )
    assert captured_env[0].get(env_var_name) == secret, (
        "API key must be present in the spawned subprocess env"
    )

    # The non-secret config IS allowed in argv (sanity).
    assert "https://example.com/v1" in argv
    assert "fake-model" in argv


def test_no_common_key_env_names_appear_as_argv_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Belt-and-braces: even an env-var-shaped string must not be argv-leaked.

    If a future refactor accidentally reverts to passing the key directly,
    this catches the case where someone names the env var something like
    ``ANTHROPIC_API_KEY`` and the key string happens to look env-shaped.
    """
    captured_argv: list[list[str]] = []

    def fake_run(argv, env=None, **kw):
        captured_argv.append(list(argv))
        return MagicMock(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("subprocess.run", fake_run)

    from usr.plugins.jcode_harness.helpers.provider_import import (
        add_jcode_profile,
    )

    # A key that contains characters jcode CLI may treat suspiciously.
    secret = "sk-ant-very-secret-with-=signs/and/slashes"
    add_jcode_profile(
        "/bin/jcode",
        "_a0_imported_anthropic",
        "https://api.anthropic.com",
        "claude-3",
        secret,
    )
    assert secret not in " ".join(captured_argv[0])
