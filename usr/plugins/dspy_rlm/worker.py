"""Explicit CLI entry point for local-multiprocess optimization workers.

Examples::

    python3 -m usr.plugins.dspy_rlm.worker --once
    python3 -m usr.plugins.dspy_rlm.worker --serve --worker-id optimizer-a

The command never starts from an API request; it is an operator/supervisor owned
process.  SQLite is local-machine only, hence the reported mode is always
``local_multiprocess`` rather than distributed.
"""
from __future__ import annotations

import argparse
import os
import socket
import sys
import uuid
from pathlib import Path

from .helpers.scheduler.worker import worker_loop


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="DSPy RLM local multiprocess queue worker")
    operation = parser.add_mutually_exclusive_group(required=True)
    operation.add_argument("--once", action="store_true", help="claim and process at most one queued job")
    operation.add_argument("--serve", action="store_true", help="poll and process jobs until interrupted")
    parser.add_argument("--worker-id", default="", help="stable identifier for leases and heartbeats")
    parser.add_argument("--plugin-dir", default="", help="plugin root; defaults to this installed plugin")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    plugin_dir = Path(args.plugin_dir).resolve() if args.plugin_dir else Path(__file__).resolve().parent
    worker_id = str(args.worker_id or f"dspy-rlm-{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:8]}")
    try:
        worker_loop(str(plugin_dir), worker_id, max_iterations=1 if args.once else None, once=bool(args.once))
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
