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
    DEFAULT_NAMESPACE,
    import_public_skills,
    list_public_skills,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import DeerFlow public skills into Agent Zero's skills registry."
    )
    parser.add_argument(
        "--source",
        required=True,
        help="Path to a DeerFlow repo root, skills directory, or skills/public directory.",
    )
    parser.add_argument(
        "--namespace",
        default=DEFAULT_NAMESPACE,
        help=f"Destination namespace under usr/skills (default: {DEFAULT_NAMESPACE}).",
    )
    parser.add_argument(
        "--conflict",
        choices=["skip", "overwrite", "rename"],
        default="skip",
        help="Conflict policy for existing imported skills.",
    )
    parser.add_argument("--project-name", help="Optional project-scoped destination.")
    parser.add_argument("--agent-profile", help="Optional agent-profile-scoped destination.")
    args = parser.parse_args()

    available = list_public_skills(args.source)
    result = import_public_skills(
        args.source,
        namespace=args.namespace,
        conflict=args.conflict,
        project_name=args.project_name,
        agent_profile=args.agent_profile,
    )

    print("Imported DeerFlow public skills")
    print(f"- Source skill count: {len(available)}")
    print(f"- Imported: {len(result.imported)}")
    print(f"- Skipped: {len(result.skipped)}")
    print(f"- Namespace: {result.namespace}")
    print(f"- Destination: {result.destination_root / result.namespace}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
