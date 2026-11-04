"""Measured scheduling weights and deterministic cost/database partitions."""

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
DB_DURATIONS = PY_ROOT / "tests" / "_support" / "db_durations.json"


def index_and_count(spec: str, *, option: str = "--shard") -> tuple[int, int]:
    """The one-based ``(index, count)`` a class selector's ``I/N`` spelling names.

    Every other spelling is the option's usage error rather than a failure
    partway through the session that read it.
    """
    match = re.fullmatch(r"(\d+)/(\d+)", spec, re.ASCII)
    if match is not None:
        index, count = int(match[1]), int(match[2])
        if 1 <= index <= count:
            return index, count
    raise pytest.UsageError(f"{option} expects I/N with 1 <= I <= N, not {spec!r}")


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
    """Measured seconds by node id.

    A required input rather than an optimization: with nothing to weigh by, the
    shards would still partition the class but balance it by nothing, so a file
    that cannot be read as a non-empty object of non-negative finite seconds is
    a usage error naming it rather than a silent default.
    """
    try:
        payload: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as error:
        raise pytest.UsageError(
            f"{path} is unreadable as the durations the shards are balanced over: {error}"
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


def group_of(item: pytest.Item) -> str | None:
    names = {
        str(mark.args[0] if mark.args else mark.kwargs.get("name", "default"))
        for mark in item.iter_markers("xdist_group")
    }
    return "_".join(sorted(names)) if names else None


def shard_of_groups(
    nodeids: Sequence[str], groups: Mapping[str, str], known: Mapping[str, float], count: int
) -> list[int]:
    """Assign whole xdist groups; ungrouped items remain independent units.

    xdist may already have appended its group suffix during collection. The
    stored weight always names the original pytest item.
    """
    units: dict[tuple[bool, str], list[int]] = {}
    canonical: list[str] = []
    for position, nodeid in enumerate(nodeids):
        group = groups.get(nodeid)
        key = (True, group) if group is not None else (False, nodeid)
        units.setdefault(key, []).append(position)
        canonical.append(nodeid.removesuffix(f"@{group}") if group is not None else nodeid)
    measured = weights(canonical, known)
    assignment = shard_of_each(
        [sum(measured[position] for position in positions) for positions in units.values()], count
    )
    result = [0] * len(nodeids)
    for positions, shard in zip(units.values(), assignment, strict=True):
        for position in positions:
            result[position] = shard
    return result
