"""How the cost class is split: the ``I/N`` spelling a cell names its shard with,
the assignment that balances the class over those shards, and the tracked file of
what each item last cost that the balance is drawn from."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

import pytest

from tests._support.repo import PY_ROOT

COST_DURATIONS = PY_ROOT / "tests" / "_support" / "cost_durations.json"


def index_and_count(spec: str) -> tuple[int, int]:
    """The ``(index, count)`` a ``--shard I/N`` spelling names, one-based.

    Every other spelling is the option's usage error rather than a failure
    partway through the session that read it.
    """
    match = re.fullmatch(r"(\d+)/(\d+)", spec, re.ASCII)
    if match is not None:
        index, count = int(match[1]), int(match[2])
        if 1 <= index <= count:
            return index, count
    raise pytest.UsageError(f"--shard expects I/N with 1 <= I <= N, not {spec!r}")


def weights(nodeids: Sequence[str], known: Mapping[str, float]) -> list[float]:
    """What each item weighs: its stored duration, or the mean of the stored
    ones for an item the store does not know."""
    unknown = sum(known.values()) / len(known)
    return [known.get(nodeid, unknown) for nodeid in nodeids]


def shard_of_each(weights: Sequence[float], count: int) -> list[int]:
    """The one-based shard each weighted item lands in.

    Heaviest first, each onto the lightest shard so far, ties to the lowest
    index: deterministic over stable input, and within one item's weight of the
    best balance.
    """
    loads = [0.0] * count
    shard = [0] * len(weights)
    for position in sorted(range(len(weights)), key=lambda p: (-weights[p], p)):
        target = min(range(count), key=lambda i: (loads[i], i))
        loads[target] += weights[position]
        shard[position] = target + 1
    return shard


def known(path: Path = COST_DURATIONS) -> dict[str, float]:
    """The seconds each cost item last cost, by node id.

    A required input rather than an optimization: with nothing to weigh by, the
    shards would still partition the class but balance it by nothing, so a file
    that cannot be read as a non-empty object of non-negative finite seconds is
    a usage error naming it rather than a silent default.
    """
    try:
        payload: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as error:
        raise pytest.UsageError(
            f"{path} is unreadable as the durations the cost shards are balanced over: {error}"
        ) from None
    if not isinstance(payload, dict) or not payload:
        raise pytest.UsageError(f"{path} holds no object of durations")
    durations: dict[str, float] = {}
    for node_id, duration in cast("dict[str, object]", payload).items():
        if (
            isinstance(duration, bool)
            or not isinstance(duration, int | float)
            or not math.isfinite(duration)
            or duration < 0
        ):
            raise pytest.UsageError(
                f"{path} maps {node_id!r} to {duration!r}; a duration is a non-negative "
                f"finite number of seconds"
            )
        durations[node_id] = float(duration)
    return durations


def store(observed: Mapping[str, float], *, replace: bool, path: Path = COST_DURATIONS) -> None:
    """Record *observed* as what the cost items it names last cost, replacing
    the stored durations or merging into them."""
    measured = {node_id: round(duration, 1) for node_id, duration in observed.items()}
    stored = measured if replace else known(path) | measured
    path.write_text(json.dumps(dict(sorted(stored.items())), indent=1) + "\n", encoding="utf-8")
