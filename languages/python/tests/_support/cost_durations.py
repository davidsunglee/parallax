"""How the cost class is split: the ``I/N`` spelling a cell names its shard with,
the assignment that balances the class over those shards, and the tracked file of
what each item last cost that the balance is drawn from."""

from __future__ import annotations

import json
import math
from collections.abc import Collection, Mapping, Sequence
from pathlib import Path
from typing import cast

import pytest

from tests._support.repo import PY_ROOT

COST_DURATIONS = PY_ROOT / "tests" / "_support" / "cost_durations.json"


def _cardinal(digits: str) -> int | None:
    """The number an ASCII digit string names, or ``None`` when it names none.

    ``str.isdigit`` answers for spellings Python's own parser then rejects, such
    as ``'²'`` and a run of more digits than the interpreter will convert.
    """
    if not (digits.isascii() and digits.isdigit()):
        return None
    try:
        return int(digits)
    except ValueError:
        return None


def index_and_count(spec: str) -> tuple[int, int]:
    """The ``(index, count)`` a ``--shard I/N`` spelling names, one-based.

    Every other spelling is the option's usage error rather than a failure
    partway through the session that read it.
    """
    index, separator, count = spec.partition("/")
    first, total = _cardinal(index), _cardinal(count)
    if separator and first is not None and total is not None and 1 <= first <= total:
        return first, total
    raise pytest.UsageError(f"--shard expects I/N with 1 <= I <= N, not {spec!r}")


def _mean(values: Collection[float]) -> float:
    """The mean of *values*, summed exactly and rounded once.

    Durations a float carries one at a time can still total more than one holds;
    that answers infinite here rather than raising out of the arithmetic, so the
    reader below can reject the mapping as the file's usage error.
    """
    try:
        total = math.fsum(values)
    except OverflowError:
        return math.inf
    return total / len(values)


def weights(nodeids: Sequence[str], known: Mapping[str, float]) -> list[float]:
    """What each item weighs: its stored duration, or the mean of the stored
    ones for an item the store does not know."""
    unknown = _mean(known.values())
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
    weights spelled as data. Values a float holds one at a time can still total
    more than one holds, and their mean is what every item the file does not know
    weighs, so the aggregate is answered for here as well as each value.
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
    if not math.isfinite(_mean(durations.values())):
        raise pytest.UsageError(
            f"{path} holds durations a float cannot average finitely; that mean is what "
            f"an item the file does not know weighs"
        )
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
    that will never run it again. Every other session merges: whatever it did
    measure, it cannot establish that the file is a complete refresh, and an
    entry it left unobserved may be the only record of an item it never ran.
    """
    measured = {node_id: round(duration, 1) for node_id, duration in observed.items()}
    whole_class = collected_the_whole_class and succeeded and set(collected) == set(observed)
    stored = measured if whole_class else known(path) | measured
    path.write_text(json.dumps(dict(sorted(stored.items())), indent=1) + "\n", encoding="utf-8")
