"""Spec §8.7: plugin removal hygiene.

Uninstall must leave ``~/.jcode/`` user data untouched unless
``--delete-user-data`` is explicitly passed. This is a security smoke test —
the unit-level equivalents in ``tests/unit/test_execute.py`` provide the
detailed behavioural coverage; here we re-assert the user-data preservation
contract independently so it cannot regress unnoticed.
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def fake_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> dict[str, Path]:
    """Redirect ``Path.home()`` to ``tmp_path`` everywhere it's read.

    ``Path.home`` is a classmethod on the immutable ``pathlib.Path`` type, so
    monkeypatching the global ``Path`` doesn't work. Instead we patch the
    ``Path`` symbol re-imported into the two modules that use it directly
    (``helpers.paths`` and ``execute``), mirroring the working pattern from
    ``tests/unit/test_execute.py``.
    """
    instance_dir = tmp_path / ".amplihack" / "jcode" / "test-instance"
    instance_dir.mkdir(parents=True)
    (instance_dir / "marker").write_text("amplihack")

    user_data = tmp_path / ".jcode"
    user_data.mkdir()
    (user_data / "auth.json").write_text("dummy-creds")

    from usr.plugins.jcode_harness import execute as execute_mod
    from usr.plugins.jcode_harness.helpers import paths as paths_mod

    monkeypatch.setattr(
        paths_mod.Path, "home", classmethod(lambda cls: tmp_path)
    )
    monkeypatch.setattr(paths_mod.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(
        execute_mod.Path, "home", classmethod(lambda cls: tmp_path)
    )

    # Pin the per-instance path so we don't rely on compute_instance_id().
    monkeypatch.setattr(
        paths_mod, "jcode_runtime_dir", lambda *_a, **_kw: instance_dir
    )

    # Stub locate_jcode_binary so DaemonSupervisor.stop is a noop path.
    monkeypatch.setattr(
        "usr.plugins.jcode_harness.helpers.daemon.locate_jcode_binary",
        lambda: None,
    )

    return {"instance": instance_dir, "user_data": user_data, "tmp": tmp_path}


def test_default_cleanup_preserves_jcode_user_data(
    fake_home: dict[str, Path],
) -> None:
    """`amplihack uninstall` (no flag) must NEVER touch ``~/.jcode/``."""
    from usr.plugins.jcode_harness.execute import main

    rc = main(["--cleanup"])
    assert rc == 0

    assert not fake_home["instance"].exists(), (
        "amplihack-managed instance dir should have been removed"
    )
    assert fake_home["user_data"].exists(), (
        "~/.jcode user data must be preserved by default"
    )
    assert (fake_home["user_data"] / "auth.json").exists(), (
        "user-owned auth credentials must survive uninstall"
    )


def test_delete_user_data_flag_removes_jcode_dir(
    fake_home: dict[str, Path],
) -> None:
    """Only the explicit ``--delete-user-data`` opt-in removes ``~/.jcode/``."""
    from usr.plugins.jcode_harness.execute import main

    rc = main(["--cleanup", "--delete-user-data"])
    assert rc == 0

    assert not fake_home["instance"].exists()
    assert not fake_home["user_data"].exists(), (
        "--delete-user-data should remove ~/.jcode entirely"
    )


def test_cleanup_is_idempotent_when_dirs_already_gone(
    fake_home: dict[str, Path],
) -> None:
    """Re-running cleanup after a successful run must still succeed."""
    from usr.plugins.jcode_harness.execute import main

    assert main(["--cleanup"]) == 0
    assert main(["--cleanup"]) == 0  # second run, dirs gone
