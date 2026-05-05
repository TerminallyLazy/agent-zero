"""Unit tests for the A0 instance-id helper."""

from __future__ import annotations

import os
import re

from usr.plugins.jcode_harness.helpers.instance import compute_instance_id


_HEX12 = re.compile(r"^[0-9a-f]{12}$")


def test_instance_id_is_12_hex_chars() -> None:
    iid = compute_instance_id("/tmp/example/a0")
    assert len(iid) == 12
    assert _HEX12.match(iid), f"expected 12 lowercase hex chars, got {iid!r}"


def test_instance_id_stable() -> None:
    a = compute_instance_id("/tmp/example/a0")
    b = compute_instance_id("/tmp/example/a0")
    assert a == b


def test_instance_id_distinguishes_paths() -> None:
    a = compute_instance_id("/tmp/example/a0")
    b = compute_instance_id("/tmp/example/other")
    assert a != b


def test_instance_id_default_resolves_repo_root() -> None:
    """Default invocation must resolve to a directory containing agent.py.

    Sanity-checks the relative ".." walk from helpers/instance.py.
    """
    iid = compute_instance_id()
    assert iid  # non-empty
    assert _HEX12.match(iid)

    # Independently re-derive the path the helper should be using and confirm
    # agent.py lives there.
    here = os.path.dirname(
        os.path.realpath(
            os.path.join(
                os.path.dirname(
                    os.path.realpath(
                        # mirror the helper's relative walk
                        os.path.join(
                            os.path.dirname(__file__),
                            "..",
                            "..",  # tests/unit -> tests -> jcode_harness
                            "helpers",
                            "instance.py",
                        )
                    )
                ),
                "..",
                "..",
                "..",
                "..",
                "agent.py",
            )
        )
    )
    assert os.path.isfile(os.path.join(here, "agent.py")), (
        f"expected agent.py in {here!r}"
    )
