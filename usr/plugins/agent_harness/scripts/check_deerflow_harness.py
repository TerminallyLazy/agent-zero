#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parents[4]


PROJECT_ROOT = _project_root()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from usr.plugins.agent_harness.helpers.deerflow_sync import (  # noqa: E402
    collect_plugin_asset_status,
    list_public_skills,
)
from usr.plugins.agent_harness.helpers.settings import load_default_settings  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check whether the Agent Harness plugin has the DeerFlow bootstrap surface in place."
    )
    parser.add_argument(
        "--source",
        help="Optional DeerFlow repo root or skills/public path to validate against.",
    )
    args = parser.parse_args()

    plugin_root = PROJECT_ROOT / "usr" / "plugins" / "agent_harness"
    asset_status = collect_plugin_asset_status(plugin_root)
    defaults = load_default_settings()

    print("Agent Harness DeerFlow Check")
    print(f"Plugin root: {plugin_root}")
    for name, present in asset_status.items():
        label = name.replace("_", " ")
        mark = "OK" if present else "MISSING"
        print(f"- {label}: {mark}")

    print("")
    modes = list(
        dict.fromkeys(
            [
                str(defaults.get("default_deep_mode", "pro")),
                "flash",
                "standard",
                "pro",
                "ultra",
            ]
        )
    )
    print("Modes: " + ", ".join(modes))

    if args.source:
        print("")
        try:
            skills = list_public_skills(args.source)
        except FileNotFoundError as exc:
            print(f"DeerFlow source: INVALID ({exc})")
            return 1
        print(f"DeerFlow source: OK ({len(skills)} public skills found)")
        if skills:
            print("Sample skills: " + ", ".join(skills[:8]))

    if not all(asset_status.values()):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
