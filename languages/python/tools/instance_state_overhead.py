"""What one published Entity retained before the flip, over the six canonical
scenarios.

Six scenarios — shallow, wide, nested, nullable, partial, polymorphic — each
measured in a fresh child interpreter of its own, with every arm of that scenario
taken inside the same child. It is a `report`: it passes no verdict and joins no
aggregate, because a total in bytes is machine- and interpreter-relative. What
has been read off it, and under what conditions, is
``docs/instance-state-baseline.md``.

**The arm it measures is a FIXTURE** —
``_instance_state_support.legacy_publication``, which builds one node the way
Entity Graph Construction built one before publication became compact: a
zero-argument ``model_construct`` filled one member at a time. It reproduced the
real path exactly while that path existed, and every scenario's fixture was
compared against it before any reading was taken. Publication no longer builds a
node that way, so there is nothing left to compare against and the reading this
fixture takes is what carries the comparison forward — the "before" a later
aggregate divides into.

**What is measured, per scenario.** Bytes reachable at the seam's innermost point
while one node of the measured arm is held that were not reachable before the
window opened — read twice, once with the node's lifecycle state attached and once
without, so the aggregate that includes unchanged lifecycle state and the one that
isolates publication state are both available. Beside them: what constructing one
node costs, what an ordinary declared-field read costs, what
``model_dump()`` costs, and what one construction allocates and frees again.

**How decoded payload leaves are excluded — structurally, not by filtering.**
Every scenario's input row and every leaf in it is allocated at import time,
outside every window, so a node that merely references one of them costs the
reading the position and not the leaf. Shared class and model metadata is excluded
the same way: every reading warms its seam before opening its window, so a layout,
a class index, or a construction's per-Entity facts is already in the baseline the
sample is compared against.

**What it is measured with.** ``memory_instruments``, the one definition the gated
suites read the same claims through: a collection before every sample so a reading
answers what is still REACHABLE, warm-up passes before every window, and the line
tracer uninstalled for the window.

Run it through `just python-report-instance-state`.
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
import tracemalloc
from collections.abc import Callable
from pathlib import Path
from time import perf_counter
from typing import Any, Final, NamedTuple, cast

INSTRUMENTS: Final = Path(__file__).resolve().parents[1] / "tests" / "unit"
"""The one directory this report names, so it can read the instruments and the
scenario fixture the gated suite reads.

They are support code for `tests/unit/`, whose own suites are their other
readers, and `core/spec/language-testing.md` §4 keeps single-surface support code
inside its surface — a report is no surface of its own, so picking them up here
does not move them. The reach stays deliberate and one-way: the path is spelled
once, here, and nothing under `tests/` knows this file exists.
"""

INSTRUMENT_MODULE: Final = INSTRUMENTS / "memory_instruments.py"
SUPPORT_MODULE: Final = INSTRUMENTS / "_instance_state_support.py"
"""The exact files the reading is taken through and over.

Both are generic names on a path this process does not own, so prepending the
directory is only half of what makes the import deterministic: a module of either
name already in :data:`sys.modules` wins before any path entry is consulted. The
report therefore states which files it means and refuses to measure through any
other, because the alternative failure is silent — a different sampling recipe or
a different scenario mix would still produce numbers, and they would not be the
numbers the recorded baseline is stated over.
"""

sys.path.insert(0, str(INSTRUMENTS))

import _instance_state_support  # noqa: E402
import memory_instruments  # noqa: E402

for _module, _expected in (
    (memory_instruments, INSTRUMENT_MODULE),
    (_instance_state_support, SUPPORT_MODULE),
):
    if Path(_module.__file__ or "").resolve() != _expected:
        raise ImportError(
            f"this report measures through {_expected}, but "
            f"{_module.__name__!r} resolved to {_module.__file__}"
        )

from _instance_state_support import (  # noqa: E402
    SCENARIOS,
    Scenario,
    legacy_publication,
    scenario_named,
)
from memory_instruments import (  # noqa: E402
    WARMUP,
    Seam,
    allocation,
    retained,
    untraced,
)
from pydantic import BaseModel  # noqa: E402

from parallax.core.entity._pydantic_storage import instance_state  # noqa: E402

REPETITIONS: Final = 2_000
"""Timed repetitions of each operation. Wall clock is recorded for visibility
alone, so this buys a stable mean rather than a distribution."""


class Reading(NamedTuple):
    """One scenario's whole reading, as a child interpreter answers it."""

    scenario: str
    summary: str
    fields: int
    entries: int
    retained_bytes: int
    bare_bytes: int
    transient_bytes: int
    construct_ns: float
    read_ns: float
    dump_ns: float

    @property
    def lifecycle_bytes(self) -> int:
        """What the unchanged lifecycle state costs — the difference between the
        two readings rather than a measurement of the state object alone, so
        whatever attaching it makes reachable is counted where a reader would."""
        return self.retained_bytes - self.bare_bytes


# --------------------------------------------------------------------------- #
# The seams, and one scenario's reading. Taken in a child interpreter.          #
# --------------------------------------------------------------------------- #


def held(scenario: Scenario, *, lifecycle: bool) -> Seam:
    """One legacy-shaped node, built inside the window and held at the sample.

    The lifecycle state is built inside the window too, so the reading that
    carries it counts it: an object allocated before the window would be borrowed
    rather than retained, and the difference between the two readings would be
    zero for the wrong reason.
    """

    def run(sample: Callable[[], None]) -> None:
        state = scenario.state() if lifecycle else None
        node = legacy_publication(scenario, state)
        sample()
        assert node is not None

    return run


def _elapsed_ns(work: Callable[[], None], *, per: int = 1) -> float:
    """Mean nanoseconds one ``work`` takes, over :data:`REPETITIONS` runs."""
    with untraced():
        for _ in range(WARMUP):
            work()
        start = perf_counter()
        for _ in range(REPETITIONS):
            work()
        elapsed = perf_counter() - start
    return elapsed * 1e9 / (REPETITIONS * per)


def measure(scenario: Scenario) -> Reading:
    """``scenario``'s whole reading, taken in this interpreter.

    Every arm in one process, which is what the child is for: a byte reading is
    read against a floor the interpreter decides, so two arms compared across two
    processes would be compared across two floors.
    """
    node = cast("BaseModel", legacy_publication(scenario, scenario.state()))
    field_names = tuple(type(node).__pydantic_fields__)
    entries = len(instance_state(node))

    def construct() -> None:
        legacy_publication(scenario, scenario.state())

    def read_fields() -> None:
        for name in field_names:
            getattr(node, name)

    def dump() -> None:
        node.model_dump()

    tracemalloc.start()
    try:
        retained_bytes = retained(held(scenario, lifecycle=True))
        bare_bytes = retained(held(scenario, lifecycle=False))
        _, transient_bytes = allocation(held(scenario, lifecycle=True))
    finally:
        tracemalloc.stop()
    return Reading(
        scenario=scenario.name,
        summary=scenario.summary,
        fields=len(field_names),
        entries=entries,
        retained_bytes=retained_bytes,
        bare_bytes=bare_bytes,
        transient_bytes=transient_bytes,
        construct_ns=_elapsed_ns(construct),
        read_ns=_elapsed_ns(read_fields, per=len(field_names)),
        dump_ns=_elapsed_ns(dump),
    )


def in_a_child(scenario: Scenario) -> Reading:
    """``scenario``'s reading, taken in an interpreter that has loaded only what
    it needs.

    One child per COMPLETE scenario rather than per arm: the isolation a whole-
    interpreter reading needs is a property of the process, and paying one process
    per arm would buy nothing while making every arm's floor a different one.

    ``memory_instruments.in_a_child_interpreter`` is the same pattern for a test,
    and is deliberately not reused: it raises on a non-zero exit and discards the
    child's output, where a report has to read the numbers back.
    """
    report = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), scenario.name],
        capture_output=True,
        text=True,
        check=False,
        env=os.environ | {"PYTHONPATH": os.pathsep.join(entry for entry in sys.path if entry)},
    )
    if report.returncode != 0:
        raise SystemExit(
            f"the {scenario.name} scenario failed in its child interpreter "
            f"(exit {report.returncode})\n{report.stdout}{report.stderr}"
        )
    payload = cast("dict[str, Any]", json.loads(report.stdout.strip().splitlines()[-1]))
    return Reading(**payload)


# --------------------------------------------------------------------------- #
# Output.                                                                      #
# --------------------------------------------------------------------------- #


def _conditions() -> list[tuple[str, str]]:
    return [
        ("Python", f"CPython {platform.python_version()}"),
        ("Platform", f"{sys.platform}/{platform.machine()}"),
        ("Warm-up", f"{WARMUP} unsampled runs before every window"),
        ("Timings", f"mean of {REPETITIONS} repetitions, taken untraced"),
        ("Isolation", "one fresh child interpreter per complete scenario"),
    ]


def _table(readings: list[Reading]) -> list[str]:
    header = (
        f"{'scenario':<12} {'fields':>6} {'slots':>6} {'retained B':>11} {'bare B':>9} "
        f"{'lifecycle B':>12} {'build us':>9} {'read ns':>8} {'dump us':>8} {'transient B':>12}"
    )
    lines = [header]
    for reading in readings:
        lines.append(
            f"{reading.scenario:<12} {reading.fields:>6} {reading.entries:>6} "
            f"{reading.retained_bytes:>11,} {reading.bare_bytes:>9,} "
            f"{reading.lifecycle_bytes:>12,} {reading.construct_ns / 1e3:>9.2f} "
            f"{reading.read_ns:>8.1f} {reading.dump_ns / 1e3:>8.2f} "
            f"{reading.transient_bytes:>12,}"
        )
    return lines


def _totals(readings: list[Reading]) -> list[str]:
    retained_total = sum(reading.retained_bytes for reading in readings)
    bare_total = sum(reading.bare_bytes for reading in readings)
    return [
        "the two sums a later aggregate divides into",
        f"  summed retained bytes, lifecycle included = {retained_total:,}",
        f"  summed retained bytes, lifecycle excluded = {bare_total:,}",
        f"  the mix's unchanged lifecycle share       = {retained_total - bare_total:,}",
        "",
        "An aggregate is 1 - sum(after) / sum(before) over these sums, never the mean",
        "of per-scenario percentages, and both sums must come from one object layout:",
        "these were taken on this tree, so a figure frozen on another one is not their",
        "comparand. Both sums are printed so the arithmetic is the reader's rather",
        "than this report's.",
    ]


def _detail(readings: list[Reading]) -> list[str]:
    return ["what each scenario is", *(f"  {r.scenario:<12} {r.summary}" for r in readings)]


# --------------------------------------------------------------------------- #
# Entry points.                                                                #
# --------------------------------------------------------------------------- #


def main(argv: list[str]) -> int:
    """Measure and print; never judge a number.

    Exit codes: 0 — the measurement ran; 2 — usage error. There is no exit code
    for a number that is too large, deliberately.
    """
    if len(argv) > 1:
        print("usage: python tools/instance_state_overhead.py [scenario]", file=sys.stderr)
        return 2
    if argv:
        print(json.dumps(measure(scenario_named(argv[0]))._asdict()))
        return 0

    readings = [in_a_child(scenario) for scenario in SCENARIOS]
    lines = ["parallax published instance state — legacy publication arm", ""]
    lines += [f"  {name:<10}{value}" for name, value in _conditions()]
    lines += ["", *_table(readings), "", *_totals(readings), "", *_detail(readings)]
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
