"""One scenario's reading under both arms, taken in a child interpreter.

The half of `tools/instance_state_overhead.py` that measures. It is a script
rather than a function that report calls: every instrument here reads the whole
process, so a reading is only a property of its own subject when it is taken in
an interpreter that has loaded nothing else, and the report starts one child per
complete scenario naming this file. Both arms are measured in that one child —
a byte reading is read against a floor the interpreter decides, so two arms
compared across two processes would be compared across two floors.

Keeping it out of the report's own module is structural. The `dbfree` suite that
grades the report's verdicts imports that module whole, and
`core/spec/language-testing.md` §5 requires a whole-interpreter reading to be
reachable only through an entry point that acquires an interpreter of its own. So
nothing the suite imports binds a reader or reaches one: the reading lives here,
and the only thing that runs it is a child.

The answer crosses back as one line of JSON on stdout, encoded by the report's
own :func:`~instance_state_overhead.payload` so the encoder and the decoder stay
in one place.
"""

from __future__ import annotations

import gc
import sys
import tracemalloc
from collections.abc import Callable
from pathlib import Path
from time import perf_counter
from typing import Any, Final, cast

WORKSPACE: Final = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(WORKSPACE / "tests" / "unit"))

from _instance_state_support import (  # noqa: E402
    Scenario,
    compact_publication,
    legacy_publication,
    scenario_named,
    state_cells,
)
from memory_instruments import (  # noqa: E402
    WARMUP,
    Seam,
    retained,
    untraced,
)

from instance_state_overhead import (  # noqa: E402
    REPETITIONS,
    ArmReading,
    Reading,
    payload,
)


def held(
    scenario: Scenario,
    arm: Callable[[Scenario, object | None], object],
    *,
    lifecycle: bool,
) -> Seam:
    """One node of ``arm``, built inside the window and held at the sample.

    The lifecycle state is built inside the window too, so the reading that
    carries it counts it: an object allocated before the window would be borrowed
    rather than retained, and the difference between the two readings would be
    zero for the wrong reason.
    """

    def run(sample: Callable[[], None]) -> None:
        state = scenario.state() if lifecycle else None
        node = arm(scenario, state)
        sample()
        assert node is not None

    return run


def _nothing() -> None:
    """The sampler an unobserved run passes."""


def peak(seam: Seam) -> int:
    """Bytes the high-water mark of one run of ``seam`` stands above the floor it
    started from.

    ``memory_instruments.allocation``'s transient half cannot answer this for
    these seams, and its own contract says why: it reads the current total as
    soon as the run RETURNS, which is the floor again only for a seam that leaves
    nothing behind. A construction leaves a node in a reference cycle, so the
    total still holds it and whatever else is waiting for the collector — and
    subtracting that from the high-water mark answers neither what the run
    reached nor what it freed again. The floor is therefore taken and collected
    for BEFORE the run, and what the node keeps is subtracted from the answer
    rather than from the sample (:attr:`ArmReading.transient_bytes`).
    """
    with untraced():
        for _ in range(WARMUP):
            seam(_nothing)
        gc.collect()
        gc.collect()
        floor, _ = tracemalloc.get_traced_memory()
        tracemalloc.reset_peak()
        seam(_nothing)
        _, high_water = tracemalloc.get_traced_memory()
    return high_water - floor


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


def measure_arm(
    scenario: Scenario,
    arm: Callable[[Scenario, object | None], object],
    field_names: tuple[str, ...],
) -> ArmReading:
    """``arm``'s reading of ``scenario``, taken in this interpreter."""
    node = arm(scenario, scenario.state())

    def construct() -> None:
        arm(scenario, scenario.state())

    def read_fields() -> None:
        for name in field_names:
            getattr(node, name)

    def dump() -> None:
        cast("Any", node).model_dump()

    tracemalloc.start()
    try:
        retained_bytes = retained(held(scenario, arm, lifecycle=True))
        bare_bytes = retained(held(scenario, arm, lifecycle=False))
        peak_bytes = peak(held(scenario, arm, lifecycle=True))
    finally:
        tracemalloc.stop()
    return ArmReading(
        cells=state_cells(node),
        retained_bytes=retained_bytes,
        bare_bytes=bare_bytes,
        peak_bytes=peak_bytes,
        construct_ns=_elapsed_ns(construct),
        read_ns=_elapsed_ns(read_fields, per=len(field_names)),
        dump_ns=_elapsed_ns(dump),
    )


def measure(scenario: Scenario) -> Reading:
    """``scenario``'s reading under both arms, taken in this interpreter."""
    field_names = tuple(cast("Any", scenario.cls).__pydantic_fields__)
    return Reading(
        scenario=scenario.name,
        summary=scenario.summary,
        fields=len(field_names),
        legacy=measure_arm(scenario, legacy_publication, field_names),
        compact=measure_arm(scenario, compact_publication, field_names),
    )


def main(argv: list[str]) -> int:
    """Take the one scenario ``argv`` names and answer with its reading."""
    if len(argv) != 1:
        print("usage: python tools/instance_state_reading.py <scenario>", file=sys.stderr)
        return 2
    print(payload(measure(scenario_named(argv[0]))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
