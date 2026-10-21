"""Take one isolated structural write reading.

This script is imported only by its gated suite. Report execution starts it in a
child interpreter, where it drives one case through the production seams of its
window and answers with one JSON line.

Four windows are read. A keyed-write case reads its row inside one
transaction and runs from the public keyed verb until ``transact`` returns:
preparation, buffering, and the pre-commit flush's settlement, SQL lowering,
production bind adaptation, and psycopg's own document serialization. A
target reads nothing before its verb, so its own coverage read
at flush falls inside that window. A public insert case runs one
``tx.wire.insert`` of a nested, polymorphic payload inside an open transaction
to the frozen node it answers, and stops before the commit that flushes the
row. The model-preparation cases each run one complete model preparation: the
structural write model, and the table-per-hierarchy family whose variant
spelling that preparation derives.

Elapsed time and the high-water mark are read over uninterrupted runs of the
whole window. The retained checkpoint is read separately, at the production
stage each window names — what the verb kept of its buffered write beyond the
read it revises, the node answered with its row buffered, the model prepared —
so sampling never prolongs a lifetime inside a timed run.

The fourth window, a cross-object flush, is read over two regions of one
pre-commit flush instead, after its transaction has read every object and
buffered an amendment of each.
Planning runs from finalization's start to the finalized plan, and its elapsed
time is one region; execution is every Write Group's steps, through lowering,
production bind adaptation, psycopg serialization, and presentation to a port
offering ordered transport, and its elapsed time is the sum of those regions.
Each group's completion falls between two regions and inside neither, as it
does in production. The execution high-water mark is the highest rise any one
group's region reached above the level it opened at. The plan's retained bytes
are a separate checkpoint, read across finalization: what is reachable once the
plan is answered, before any group executes, that was not before it began.
Byte readings are reported per flush and per object, and every flush must
present to the port exactly the work its case states.
"""

from __future__ import annotations

import argparse
import gc
import json
import sys
import tracemalloc
from collections.abc import Callable, Generator, Mapping, Sequence
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from time import perf_counter_ns
from types import CodeType, TracebackType
from typing import Any, Final, Literal, cast

from parallax.core import Entity, document_codec
from parallax.core.base import detach_json_container
from parallax.core.document_codec._document import (
    encode_managed_document,
    encode_managed_many,
)
from parallax.core.entity import DomainModel
from parallax.core.execution import prepare_model
from parallax.snapshot import ScopedDatabase

WORKSPACE: Final = Path(__file__).resolve().parents[1]
INSTRUMENT_MODULE: Final = WORKSPACE / "tests" / "unit" / "memory_instruments.py"
SUPPORT_MODULE: Final = WORKSPACE / "tests" / "unit" / "_write_lowering_support.py"
sys.path.insert(0, str(WORKSPACE))

# `sys.path` gains the workspace above, so these imports cannot precede it; that is
# what the E402 suppression each one carries records.
from tests.unit import _write_lowering_support as lowering_support  # noqa: E402
from tests.unit import memory_instruments  # noqa: E402

for module, expected in (
    (memory_instruments, INSTRUMENT_MODULE),
    (lowering_support, SUPPORT_MODULE),
):
    if Path(module.__file__ or "").resolve() != expected:
        raise ImportError(f"this reading requires {expected}, but resolved {module.__file__}")

# E402 again, and imported below the guard proving each module is this workspace's own.
from tests.unit.memory_instruments import (  # noqa: E402
    WARMUP,
    Seam,
    retained,
    retained_increment,
    untraced,
)

type Window = Literal[
    "keyed-write", "wire-insert-response", "model-preparation", "cross-object-flush"
]

KEYED_WINDOW: Final[Window] = "keyed-write"
RESPONSE_WINDOW: Final[Window] = "wire-insert-response"
MODEL_WINDOW: Final[Window] = "model-preparation"
FLUSH_WINDOW: Final[Window] = "cross-object-flush"
MODEL_CASE: Final = "model.prepared"
MODEL_FAMILY_CASE: Final = "model.prepared.family"
MODEL_EDITION: Final = "write-lowering-report"
METRICS: Final = ("elapsedUs", "transientBytes", "retainedBytes")
WORK_CELLS: Final[Mapping[str, Callable[[lowering_support.FlushWork], int]]] = {
    "work.statements": lambda work: work.statements,
    "work.invocations": lambda work: work.invocations,
    "work.largestOrderedInvocation": lambda work: work.largest_ordered_invocation,
    "work.largestGroupedInsert": lambda work: work.largest_grouped_insert,
}
FLUSH_METRICS: Final = (
    "plan.elapsedUs",
    "plan.retainedBytes",
    "plan.retainedBytesPerObject",
    "execution.elapsedUs",
    "execution.transientBytes",
    "execution.transientBytesPerObject",
    *WORK_CELLS,
)
RETAINED_WARMUPS: Final = WARMUP

_MONITORING_TOOL_IDS: Final = range(6)
OBSERVED_FUNCTIONS: Final[Mapping[str, Callable[..., object]]] = {
    "occurrenceShape": document_codec.occurrence_shape,
    "encodeManagedDocument": encode_managed_document,
    "encodeManagedMany": encode_managed_many,
    "applyPatches": document_codec.apply_prepared_patches,
    "detachJsonContainer": detach_json_container,
}
"""Pass observations over the keyed-write window: returns of each named function
per row, diagnostics that distinguish roots, nested values, and repeated calls,
and gate nothing. They are counted over exactly the region the window is timed
over, from the verb to ``transact``'s return, so the read before it counts
nothing. The two managed encoders are observed at the private module
payload preparation imports them from, so the count is of the code objects
production runs: a nested document returns once per recursion, one Many return
covers every element it encodes, a successor lowered as patches returns once per
replaced subtree, and an unchanged successor returns neither."""

WINDOWS: Final[Mapping[str, Window]] = {
    **{case.name: KEYED_WINDOW for case in lowering_support.CASES},
    **{case.name: RESPONSE_WINDOW for case in lowering_support.RESPONSE_CASES},
    MODEL_CASE: MODEL_WINDOW,
    MODEL_FAMILY_CASE: MODEL_WINDOW,
    **{case.name: FLUSH_WINDOW for case in lowering_support.CROSS_OBJECT_CASES},
}
CASE_NAMES: Final = tuple(WINDOWS)
MODEL_CLASSES: Final[Mapping[str, tuple[type[Entity], ...]]] = {
    MODEL_CASE: lowering_support.ENTITY_CLASSES,
    MODEL_FAMILY_CASE: lowering_support.FAMILY_ENTITY_CLASSES,
}
"""The Entity Classes each model-preparation case prepares."""


@dataclass(frozen=True, slots=True)
class Observation:
    calls: Mapping[str, int]


class Observer(AbstractContextManager["Observer"]):
    """Count selected Python calls."""

    def __init__(self, functions: Mapping[str, Callable[..., object]]) -> None:
        self._names = {
            cast("CodeType", cast("Any", function).__code__): name
            for name, function in functions.items()
        }
        self._calls = dict.fromkeys(functions, 0)
        self._tool: int | None = None

    def __enter__(self) -> Observer:
        monitoring = sys.monitoring
        tool = next(
            identifier
            for identifier in _MONITORING_TOOL_IDS
            if monitoring.get_tool(identifier) is None
        )
        monitoring.use_tool_id(tool, "write lowering observer")
        self._tool = tool
        try:
            monitoring.register_callback(tool, monitoring.events.PY_RETURN, self._on_return)
            for code in self._names:
                monitoring.set_local_events(tool, code, monitoring.events.PY_RETURN)
        except BaseException:
            monitoring.free_tool_id(tool)
            self._tool = None
            raise
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc_type, exc, traceback
        tool = self._tool
        if tool is None:
            return
        monitoring = sys.monitoring
        try:
            for code in self._names:
                monitoring.set_local_events(tool, code, 0)
        finally:
            monitoring.free_tool_id(tool)
            self._tool = None

    def _on_return(self, code: CodeType, _offset: int, _value: object) -> None:
        self._calls[self._names[code]] += 1

    def observation(self) -> Observation:
        if self._tool is not None:
            raise RuntimeError("an observation is available only after clean observer teardown")
        return Observation(calls=dict(self._calls))


type Sampler = Callable[[], None]


@dataclass(frozen=True, slots=True)
class Driver:
    """One window's runs: an uninterrupted run, a run that marks the window's
    two ends, and a run that samples at the retained checkpoint, beside the
    instrument that reads that checkpoint."""

    units: int
    run: Callable[[], None]
    marked: Callable[[Sampler, Sampler], None]
    checkpoint: Callable[[Sampler], None]
    kept: Callable[[Seam], int] = retained


def _kept_by_the_verb(seam: Seam) -> int:
    """What a keyed verb kept, read as a retained increment and answered as at
    least zero, as :func:`_peak` answers its rise: a verb that keeps nothing — an
    update restoring every member — can release a few dozen bytes the sequence
    left behind it, and a retained reading is never negative."""
    return max(0, retained_increment(seam))


def _keyed_driver(case: lowering_support.Case, handle: ScopedDatabase) -> Driver:
    """A keyed write's runs. Its checkpoint samples twice, before the verb (after
    the read, where the case makes one) and after the verb has buffered,
    because the read the verb revises must stay alive across it: what the verb
    kept is the difference."""

    def run() -> None:
        lowering_support.write(handle, case)

    def marked(opened: Sampler, closed: Sampler) -> None:
        lowering_support.write(handle, case, opened=opened, closed=closed)

    def checkpoint(sample: Sampler) -> None:
        lowering_support.write(handle, case, opened=sample, buffered=sample)

    return Driver(1, run, marked, checkpoint, _kept_by_the_verb)


def _response_driver(case: lowering_support.ResponseCase, handle: ScopedDatabase) -> Driver:
    def run() -> None:
        lowering_support.insert_response(handle, case)

    def marked(opened: Sampler, closed: Sampler) -> None:
        lowering_support.insert_response(handle, case, opened=opened, closed=closed)

    def checkpoint(sample: Sampler) -> None:
        lowering_support.insert_response(handle, case, closed=sample)

    return Driver(1, run, marked, checkpoint)


def _model_driver(classes: Sequence[type[Entity]]) -> Driver:
    def prepare() -> object:
        return prepare_model(DomainModel(*classes), edition=MODEL_EDITION)

    def run() -> None:
        prepare()

    def marked(opened: Sampler, closed: Sampler) -> None:
        opened()
        selection = prepare()
        closed()
        assert selection is not None

    def checkpoint(sample: Sampler) -> None:
        selection = prepare()
        sample()
        assert selection is not None

    return Driver(1, run, marked, checkpoint)


@contextmanager
def driver_for(name: str) -> Generator[Driver]:
    window = WINDOWS[name]
    if window == KEYED_WINDOW:
        keyed = lowering_support.case_named(name)
        with lowering_support.database(keyed) as handle:
            yield _keyed_driver(keyed, handle)
        return
    if window == RESPONSE_WINDOW:
        response = lowering_support.response_case_named(name)
        with lowering_support.response_database(response) as handle:
            yield _response_driver(response, handle)
        return
    yield _model_driver(MODEL_CLASSES[name])


def _timed(driver: Driver) -> int:
    marks: list[int] = []

    def opened() -> None:
        marks.append(perf_counter_ns())

    def closed() -> None:
        marks.append(perf_counter_ns())

    driver.marked(opened, closed)
    return marks[1] - marks[0]


def _peak(driver: Driver) -> int:
    memory_instruments.require_own_interpreter("write-lowering peak")
    marks: list[int] = []

    def opened() -> None:
        gc.collect()
        gc.collect()
        floor, _ = tracemalloc.get_traced_memory()
        tracemalloc.reset_peak()
        marks.append(floor)

    def closed() -> None:
        _, high_water = tracemalloc.get_traced_memory()
        marks.append(high_water)

    driver.marked(opened, closed)
    return max(0, marks[1] - marks[0])


def _observed(driver: Driver) -> Observation:
    observer = Observer(OBSERVED_FUNCTIONS)

    def opened() -> None:
        observer.__enter__()

    def closed() -> None:
        observer.__exit__(None, None, None)

    try:
        driver.marked(opened, closed)
    finally:
        observer.__exit__(None, None, None)
    return observer.observation()


def _per_unit(samples: Sequence[int | float], units: int) -> list[float]:
    return [float(sample) / units for sample in samples]


class _Stopwatch:
    __slots__ = ("_opened", "total")

    def __init__(self) -> None:
        self._opened = 0
        self.total = 0

    def open(self) -> None:
        self._opened = perf_counter_ns()

    def close(self) -> None:
        self.total += perf_counter_ns() - self._opened


class _RegionalPeak:
    """The highest rise above its own floor that any one region it was opened
    and closed around reached; ``tracemalloc`` must already be tracing. Each
    floor is read after a collection, as :func:`_peak` reads its one."""

    __slots__ = ("_floor", "highest")

    def __init__(self) -> None:
        self._floor = 0
        self.highest = 0

    def open(self) -> None:
        memory_instruments.require_own_interpreter("write-lowering regional peak")
        gc.collect()
        gc.collect()
        self._floor = tracemalloc.get_traced_memory()[0]
        tracemalloc.reset_peak()

    def close(self) -> None:
        _, high_water = tracemalloc.get_traced_memory()
        self.highest = max(self.highest, high_water - self._floor)


@dataclass(frozen=True, slots=True)
class _FlushDriver:
    objects: int
    regions: lowering_support.FlushRegions
    run: Callable[[], lowering_support.FlushWork]

    def marked(
        self,
        *,
        planning: Sampler = lowering_support.unmarked,
        planned: Sampler = lowering_support.unmarked,
        executing: Sampler = lowering_support.unmarked,
        executed: Sampler = lowering_support.unmarked,
    ) -> lowering_support.FlushWork:
        regions = self.regions
        regions.planning, regions.planned = planning, planned
        regions.executing, regions.executed = executing, executed
        try:
            return self.run()
        finally:
            regions.planning = regions.planned = lowering_support.unmarked
            regions.executing = regions.executed = lowering_support.unmarked


@contextmanager
def _flush_driver_for(case: lowering_support.CrossObjectCase) -> Generator[_FlushDriver]:
    regions = lowering_support.FlushRegions()
    port = lowering_support.OrderedAcceptingPort(case.stored)

    with (
        lowering_support.flush_database(case, port) as handle,
        lowering_support.marked_flushes(regions),
    ):

        def run() -> lowering_support.FlushWork:
            port.reset()
            lowering_support.flush_objects(handle, case)
            work = port.work()
            if work != case.work:
                raise RuntimeError(f"{case.name} presented {work}, expected {case.work}")
            return work

        yield _FlushDriver(case.objects, regions, run)


def _timed_flush(driver: _FlushDriver) -> tuple[int, int, lowering_support.FlushWork]:
    planning, execution = _Stopwatch(), _Stopwatch()
    work = driver.marked(
        planning=planning.open,
        planned=planning.close,
        executing=execution.open,
        executed=execution.close,
    )
    return planning.total, execution.total, work


def _execution_peak(driver: _FlushDriver) -> int:
    peak = _RegionalPeak()
    driver.marked(executing=peak.open, executed=peak.close)
    return peak.highest


def _plan_kept(driver: _FlushDriver) -> int:
    def checkpoint(sample: Sampler) -> None:
        driver.marked(planning=sample, planned=sample)

    return max(0, retained_increment(checkpoint))


def _measure_flush(name: str, *, warmups: int, measured: int) -> dict[str, object]:
    case = lowering_support.cross_object_case_named(name)
    with _flush_driver_for(case) as driver:
        with untraced():
            for _ in range(warmups):
                driver.run()
            planning: list[int] = []
            execution: list[int] = []
            works: set[lowering_support.FlushWork] = set()
            for _ in range(measured):
                planning_ns, execution_ns, work = _timed_flush(driver)
                planning.append(planning_ns)
                execution.append(execution_ns)
                works.add(work)

        transient: list[int] = []
        tracemalloc.start()
        try:
            with untraced():
                for _ in range(measured):
                    transient.append(_execution_peak(driver))
            kept = _plan_kept(driver)
        finally:
            tracemalloc.stop()

    (work,) = works
    objects = case.objects
    samples: dict[str, list[float]] = {
        "plan.elapsedUs": [total / 1_000 for total in planning],
        "plan.retainedBytes": [float(kept)],
        "plan.retainedBytesPerObject": _per_unit([kept], objects),
        "execution.elapsedUs": [total / 1_000 for total in execution],
        "execution.transientBytes": [float(peak) for peak in transient],
        "execution.transientBytesPerObject": _per_unit(transient, objects),
        **{cell: [float(count(work))] for cell, count in WORK_CELLS.items()},
    }
    return {
        "case": name,
        "window": FLUSH_WINDOW,
        "units": objects,
        "samples": samples,
        "calls": {},
        "warmups": warmups,
        "measured": measured,
        "retainedWarmups": RETAINED_WARMUPS,
    }


def measure(name: str, *, warmups: int, measured: int) -> dict[str, object]:
    """One case's per-unit samples over its window, and its pass observations."""
    if warmups < 0 or measured <= 0:
        raise ValueError("warmups must be non-negative and measured must be positive")
    window = WINDOWS[name]
    if window == FLUSH_WINDOW:
        return _measure_flush(name, warmups=warmups, measured=measured)
    observe = window == KEYED_WINDOW

    with driver_for(name) as driver:
        with untraced():
            for _ in range(warmups):
                driver.run()
            elapsed: list[int] = []
            call_samples: dict[str, list[int]] = {name: [] for name in OBSERVED_FUNCTIONS}
            for _ in range(measured):
                elapsed.append(_timed(driver))
                if observe:
                    for called, count in _observed(driver).calls.items():
                        call_samples[called].append(count)

        transient: list[int] = []
        tracemalloc.start()
        try:
            with untraced():
                for _ in range(measured):
                    transient.append(_peak(driver))
            kept = driver.kept(driver.checkpoint)
        finally:
            tracemalloc.stop()

        units = driver.units
        return {
            "case": name,
            "window": window,
            "units": units,
            "samples": {
                "elapsedUs": _per_unit([total / 1_000 for total in elapsed], units),
                "transientBytes": _per_unit(transient, units),
                "retainedBytes": _per_unit([kept], units),
            },
            "calls": {
                called: float(median(samples)) / units
                for called, samples in call_samples.items()
                if observe
            },
            "warmups": warmups,
            "measured": measured,
            "retainedWarmups": RETAINED_WARMUPS,
        }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=CASE_NAMES)
    parser.add_argument("--warmups", required=True, type=int)
    parser.add_argument("--measured", required=True, type=int)
    args = parser.parse_args(argv)
    try:
        reading = measure(args.case, warmups=args.warmups, measured=args.measured)
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps(reading, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
