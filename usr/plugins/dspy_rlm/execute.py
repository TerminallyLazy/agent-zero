"""Manual-only dependency setup diagnostics for the isolated DSPy RLM worker.

This module intentionally does not create environments, start processes, access a
package index, or install packages.  It produces a reviewable operator plan only.
"""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from typing import Any


PLUGIN_ROOT = Path(__file__).resolve().parent
LOCK_MANIFEST = PLUGIN_ROOT / "requirements-gepa.lock"
INSTALLER_LOCK = PLUGIN_ROOT / "state" / "worker-env-install.lock"
INSTALL_LOG = PLUGIN_ROOT / "state" / "worker-env-install.log"
WORKER_VENV = PLUGIN_ROOT / "state" / "worker-venv"
_HASH_RE = re.compile(r"--hash=sha256:[A-Fa-f0-9]{64}")
_MODULE_NAMES = {"dspy-ai": "dspy", "gepa": "gepa"}


def locked_requirements() -> list[str]:
    """Return the exact pinned package lines in the reviewed GEPA manifest.

    Unsupported pip directives are deliberately ignored: setup is allowed only
    for direct ``name==version`` entries in the repository lock manifest.
    """
    if not LOCK_MANIFEST.is_file():
        return []
    packages: list[str] = []
    for raw in LOCK_MANIFEST.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        package = line.split("#", 1)[0].strip()
        if re.fullmatch(r"[A-Za-z0-9_.-]+==[A-Za-z0-9_.!+~-]+(?:\s+--hash=sha256:[A-Fa-f0-9]{64})*", package):
            packages.append(package)
    return packages


def _package_name(requirement: str) -> str:
    return requirement.split("==", 1)[0].strip().lower()


def dependency_diagnostics() -> dict[str, Any]:
    """Inspect import availability and lock integrity without changing runtime."""
    requirements = locked_requirements()
    installed: list[str] = []
    missing: list[str] = []
    for requirement in requirements:
        name = _package_name(requirement)
        module = _MODULE_NAMES.get(name, name.replace("-", "_"))
        if importlib.util.find_spec(module) is None:
            missing.append(requirement)
        else:
            installed.append(requirement)

    lock_text = LOCK_MANIFEST.read_text(encoding="utf-8") if LOCK_MANIFEST.is_file() else ""
    hash_complete = bool(requirements) and all(_HASH_RE.search(line) for line in requirements)
    diagnostics: list[str] = []
    if not LOCK_MANIFEST.is_file():
        diagnostics.append("lock_manifest_missing")
    elif not requirements:
        diagnostics.append("lock_manifest_has_no_supported_exact_pins")
    if requirements and not hash_complete:
        diagnostics.append("lock_manifest_missing_hashes")
    if lock_text and not requirements:
        diagnostics.append("lock_manifest_not_usable")

    return {
        "lock_manifest": str(LOCK_MANIFEST),
        "exact_requirements": requirements,
        "installed": installed,
        "missing": missing,
        "hash_complete": hash_complete,
        "diagnostics": diagnostics,
        "ready": bool(requirements) and hash_complete and not missing,
    }


def manual_setup_plan() -> dict[str, Any]:
    """Return a non-executing, hash- and index-gated worker setup plan.

    The current checked-in manifest intentionally records exact versions but no
    hashes.  Consequently this plan is *blocked* until an operator supplies an
    approved hash-bearing revision of that same reviewed manifest.
    """
    report = dependency_diagnostics()
    trusted_index = "${DSPY_RLM_TRUSTED_INDEX_URL}"
    worker_python = WORKER_VENV / "bin" / "python"
    commands = [
        f"python3 -m venv {WORKER_VENV}",
        (
            f"{worker_python} -m pip install --require-hashes --index-url {trusted_index} "
            f"-r {LOCK_MANIFEST}"
        ),
        f"{worker_python} -c 'import dspy, gepa; print(\"DSPy/GEPA worker imports OK\")'",
        # Run from the repository root so the plugin module itself is visible;
        # this command is an operator review item, not executable API behavior.
        f"{worker_python} -m usr.plugins.dspy_rlm.worker --once",
    ]
    blockers = list(report["diagnostics"])
    if not report["hash_complete"] and "lock_manifest_missing_hashes" not in blockers:
        blockers.append("lock_manifest_missing_hashes")
    blockers.extend(["operator_must_supply_trusted_index", "operator_must_explicitly_execute_plan"])
    return {
        "ok": False,
        "mode": "manual_explicit_setup_only",
        "execution_performed": False,
        "lock_manifest": str(LOCK_MANIFEST),
        "exact_requirements": report["exact_requirements"],
        "isolated_worker_venv": str(WORKER_VENV),
        "installer_lock": str(INSTALLER_LOCK),
        "installer_lock_policy": "one_operator_at_a_time",
        "timeout_seconds": 900,
        "trusted_index_required": True,
        "hashes_required": True,
        "log_path": str(INSTALL_LOG),
        "smoke_test": "import dspy and gepa in the isolated worker venv",
        "worker_recycle_required": True,
        "commands_for_operator_review": commands,
        "blockers": list(dict.fromkeys(blockers)),
        "depfix": {
            "supported": False,
            "disclaimer": (
                "Depfix is experimental and may be used only as an isolated worker adapter "
                "against this plugin's frozen store. It must use no dynamic requirements, "
                "perform explicit imports in each subprocess, and must never modify or repair "
                "Agent Zero's interpreter."
            ),
        },
    }


def setup_action() -> dict[str, Any]:
    """Compatibility entry point for an explicit setup action; it never executes it."""
    return manual_setup_plan()
