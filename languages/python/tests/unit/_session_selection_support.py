"""What a real pytest session over this tree selects, read off a session of its
own rather than off the one grading it."""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor

from tests._support.repo import PY_ROOT

__all__ = ["WHOLE_CLASS", "selection", "selections"]

WHOLE_CLASS = "1/1"


def selection(expression: str | None, shard: str) -> list[str]:
    """The items one session selects under ``--shard shard``, narrowed to
    ``-m expression`` when one is given, in collection order.

    A shard is a property of a whole session, so it is read off a session of
    its own rather than off the one grading it.
    """
    narrowing = [] if expression is None else ["-m", expression]
    collected = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            *narrowing,
            "--shard",
            shard,
            "--collect-only",
            "-q",
            "-p",
            "no:cacheprovider",
        ],
        cwd=PY_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return [line for line in collected.stdout.splitlines() if "::" in line]


def selections(requests: Sequence[tuple[str | None, str]]) -> list[list[str]]:
    """One :func:`selection` per request, the sessions run side by side.

    Each session collects the whole tree, so the batch performs one collection
    per request however it is run; waiting on them together overlaps their wall
    times and nothing else. What the sessions share is the checkout, the
    environment, and the tracked durations file, which each of them only reads —
    none of them passes ``--store-cost-durations`` — so running them at once
    cannot race.
    """
    expressions = [expression for expression, _ in requests]
    shards = [shard for _, shard in requests]
    with ThreadPoolExecutor(max_workers=len(requests)) as sessions:
        return list(sessions.map(selection, expressions, shards))
