"""What each cost item last cost, and the tracked file recording it."""

from __future__ import annotations

import json
import math
from collections.abc import Collection, Mapping
from pathlib import Path
from typing import cast

import pytest

from _support.repo import PY_ROOT

COST_DURATIONS = PY_ROOT / "tests" / "_support" / "cost_durations.json"


def _seconds(duration: object) -> float | None:
    """*duration* as a number of seconds, or ``None`` when it is not one.

    A magnitude the interpreter holds exactly is still no duration when no float
    can carry it: both the conversion and the finiteness question raise on it
    rather than answering.
    """
    if isinstance(duration, bool) or not isinstance(duration, int | float):
        return None
    try:
        seconds = float(duration)
    except (OverflowError, ValueError):
        return None
    return seconds if math.isfinite(seconds) and seconds >= 0 else None


def known(path: Path = COST_DURATIONS) -> dict[str, float]:
    """The seconds each cost item last cost, by node id.

    A required input rather than an optimization: with nothing to weigh by, the
    shards would weigh every item the same, partition the class exactly as
    before, and balance it by nothing, so every way of failing to read a duration
    out of it is a usage error naming the file rather than a silent default.
    Unreadable covers every reason the bytes do not arrive as JSON, not only a
    file that is absent: a number spelled in more digits than the interpreter
    will parse never becomes a value to weigh either. A JSON object keys by
    string already; what it does not constrain is the value, and a string, a
    boolean, a negative, a non-finite one, or one too large for a float would
    weigh a shard or poison the mean the unknown items weigh. An object holding
    nothing at all reads as durations while naming none, which is those equal
    weights spelled as data.
    """
    try:
        payload: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as error:
        raise pytest.UsageError(
            f"{path} is unreadable as the durations the cost shards are balanced over: {error}"
        ) from None
    if not isinstance(payload, dict):
        raise pytest.UsageError(
            f"{path} holds {type(payload).__name__}, not an object of durations"
        )
    if not payload:
        raise pytest.UsageError(f"{path} names no durations; it is what balances the cost shards")
    durations: dict[str, float] = {}
    for node_id, duration in cast("dict[str, object]", payload).items():
        seconds = _seconds(duration)
        if seconds is None:
            raise pytest.UsageError(
                f"{path} maps {node_id!r} to {duration!r}; a duration is a non-negative "
                f"number of seconds a float holds finitely"
            )
        durations[node_id] = seconds
    return durations


def store(
    observed: Mapping[str, float],
    *,
    collected_the_whole_class: bool,
    collected: Collection[str],
    succeeded: bool,
    path: Path = COST_DURATIONS,
) -> None:
    """Record *observed* as what the cost items it names last cost.

    Replaces the file only for a session that measured the whole class: it
    collected the class entire, reported a call for every cost item it collected,
    and ended successfully. Only then is an unobserved entry an item that has
    been deleted or renamed, which must leave no record behind to weigh a shard
    that will never run it again. Every other session measured part of the class
    and merges, because the entries it did not observe are the only record of the
    items it never ran.
    """
    measured = {node_id: round(duration, 1) for node_id, duration in observed.items()}
    whole_class = collected_the_whole_class and succeeded and set(collected) == set(observed)
    stored = measured if whole_class else known(path) | measured
    path.write_text(json.dumps(dict(sorted(stored.items())), indent=1) + "\n", encoding="utf-8")
