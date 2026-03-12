# usr/plugins/qmd/initialize.py
"""One-time setup for the QMD plugin.

Verifies Node.js >= 22, installs @tobilu/qmd via npm, and runs
a bridge selftest to confirm the installation works.
"""
from __future__ import annotations

import subprocess
import sys
import os


def main() -> int:
    plugin_dir = os.path.dirname(os.path.abspath(__file__))
    bridge_dir = os.path.join(plugin_dir, "bridge")
    bridge_js = os.path.join(bridge_dir, "bridge.js")

    # Step 1: Check Node.js >= 22
    print("Checking Node.js version...")
    try:
        result = subprocess.run(
            ["node", "--version"], capture_output=True, text=True, check=True
        )
        version_str = result.stdout.strip().lstrip("v")
        major = int(version_str.split(".")[0])
        if major < 22:
            print(f"ERROR: Node.js {version_str} found, but >= 22 is required.")
            print("Install from https://nodejs.org or: brew install node")
            return 1
        print(f"  Node.js {version_str} ok")
    except FileNotFoundError:
        print("ERROR: Node.js not found.")
        print("Install from https://nodejs.org or: brew install node")
        return 1

    # Step 2: npm install in bridge/
    print("Installing @tobilu/qmd (this may take a minute)...")
    result = subprocess.run(
        ["npm", "install"],
        cwd=bridge_dir,
        check=False,
    )
    if result.returncode != 0:
        print("ERROR: npm install failed.")
        return result.returncode
    print("  @tobilu/qmd installed ok")

    # Step 3: Bridge selftest
    print("Running bridge selftest...")
    try:
        result = subprocess.run(
            ["node", bridge_js, "--selftest"],
            capture_output=True, text=True, check=False,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        print("ERROR: Bridge selftest timed out after 60 seconds.")
        return 1
    if result.returncode != 0:
        print(f"ERROR: Bridge selftest failed (exit {result.returncode}).")
        print(f"stderr: {result.stderr[:300]}")
        return result.returncode
    print("  Bridge selftest passed ok")

    print("")
    print("QMD bridge ready.")
    print("Next steps:")
    print("  qmd collection add ~/notes --name notes")
    print("  qmd embed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
