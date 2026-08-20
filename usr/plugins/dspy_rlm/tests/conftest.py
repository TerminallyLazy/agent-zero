from __future__ import annotations

from pathlib import Path
import sys

import pytest


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
# dspy_rlm lives at <repository>/usr/plugins/dspy_rlm.
# Keep the repository itself importable when pytest is invoked normally, without
# requiring callers to set PYTHONPATH.
REPOSITORY_ROOT = PLUGIN_ROOT.parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))


@pytest.fixture
def isolated_plugin_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Keep plugin-path globals and future state/config caches isolated per test."""
    import usr.plugins.dspy_rlm.helpers.paths as paths
    import usr.plugins.dspy_rlm.helpers.state as state

    state_dir = tmp_path / "state"
    monkeypatch.setattr(paths, "PLUGIN_ROOT", tmp_path)
    monkeypatch.setattr(paths, "STATE_DIR", state_dir)
    monkeypatch.setattr(paths, "TRACE_FILE", state_dir / "traces.jsonl")
    monkeypatch.setattr(paths, "STATE_FILE", state_dir / "runtime_state.json")
    monkeypatch.setattr(paths, "COMPILED_STATE_FILE", state_dir / "compiled_guidance.json")
    monkeypatch.setattr(state, "STATE_FILE", state_dir / "runtime_state.json")
    monkeypatch.setattr(state, "COMPILED_STATE_FILE", state_dir / "compiled_guidance.json")
    return tmp_path
