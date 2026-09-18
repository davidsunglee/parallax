"""Take one isolated structural write reading.

This script is imported only by its gated suite. Report execution starts it in a
child interpreter, where it drives one case through the production seams of its
window and answers with one JSON line.

Three windows are read. A keyed-write case runs from Typed or Wire input
through preparation, settlement, SQL lowering, production bind adaptation, and
psycopg's own document serialization. A predicate-acquisition case runs from a
prepared Bitemporal predicate and freshly composed resolving rows through
production acquisition to a buffered Materialized Write Group, and stops before
any flush. The model-preparation case runs one complete model preparation.

Elapsed time and the high-water mark are read over uninterrupted runs of the
whole window. The retained checkpoint is read separately, at the production
stage each window names — the write prepared and settled, the group buffered,
the model prepared — so sampling never prolongs a lifetime inside a timed run.
"""

from __future__ import annotations

import argparse
import gc
import json
import sys
import tracemalloc
from collections.abc import Callable, Mapping, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from time import perf_counter_ns
from types import CodeType, TracebackType
from typing import Any, Final, Literal, cast

from parallax.core import document_codec
from parallax.core.base import detach_json_container
from parallax.core.document_codec._document import (
    encode_managed_document,
    encode_managed_many,
)
from parallax.core.entity import DomainModel, EntityRowCodec
from parallax.core.unit_work import WritePlanner
from parallax.snapshot import prepare_model
from parallax.snapshot.handle import Database, build_write_planner

WORKSPACE: Final = Path(__file__).resolve().parents[1]
INSTRUMENT_MODULE: Final = WORKSPACE / "tests" / "unit" / "memory_instruments.py"
SUPPORT_MODULE: Final = WORKSPACE / "tests" / "unit" / "_write_lowering_support.py"
ACQUISITION_MODULE: Final = WORKSPACE / "tests" / "unit" / "_predicate_acquisition_support.py"
sys.path.insert(0, str(WORKSPACE))

# `sys.path` gains the workspace above, so these imports cannot precede it; that is
# what the E402 suppression each one carries records.
from tests.unit import _predicate_acquisition_support as acquisition_support  # noqa: E402
from tests.unit import _write_lowering_support as lowering_support  # noqa: E402
from tests.unit import memory_instruments  # noqa: E402

for module, expected in (
    (memory_instruments, INSTRUMENT_MODULE),
    (lowering_support, SUPPORT_MODULE),
    (acquisition_support, ACQUISITION_MODULE),
):
    if Path(module.__file__ or "").resolve() != expected:
        raise ImportError(f"this reading requires {expected}, but resolved {module.__file__}")

# E402 again, and imported below the guard proving each module is this workspace's own.
from tests.unit.memory_instruments import WARMUP, retained, untraced  # noqa: E402

type Window = Literal["keyed-write", "predicate-acquisition", "model-preparation"]

KEYED_WINDOW: Final[Window] = "keyed-write"
ACQUISITION_WINDOW: Final[Window] = "predicate-acquisition"
MODEL_WINDOW: Final[Window] = "model-preparation"
MODEL_CASE: Final = "model.prepared"
MODEL_EDITION: Final = "write-lowering-report"
METRICS: Final = ("elapsedUs", "transientBytes", "retainedBytes")
RETAINED_WARMUPS: Final = WARMUP

_MONITORING_TOOL_IDS: Final = range(6)
OBSERVED_FUNCTIONS: Final[Mapping[str, Callable[..., object]]] = {
    "shapeOfDeclaration": document_codec.shape_of_declaration,
    "entityShape": document_codec.entity_shape,
    "occurrenceShape": document_codec.occurrence_shape,
    "encodeManagedDocument": encode_managed_document,
    "encodeManagedMany": encode_managed_many,
    "applyPatches": document_codec.apply_patches,
    "detachJsonContainer": detach_json_container,
}
"""Pass observations over the keyed-write window: returns of each named function
per row, diagnostics that distinguish roots, nested values, and repeated calls,
and gate nothing. The two managed encoders are observed at the private module
SQL lowering imports them from, so the count is of the code objects production
runs: a nested document returns once per recursion, one Many return covers every
element it encodes, a successor lowered as patches returns once per replaced
subtree, and an unchanged successor returns neither."""

WINDOWS: Final[Mapping[str, Window]] = {
    **{case.name: KEYED_WINDOW for case in lowering_support.CASES},
    **{case.name: ACQUISITION_WINDOW for case in acquisition_support.CASES},
    MODEL_CASE: MODEL_WINDOW,
}
CASE_NAMES: Final = tuple(WINDOWS)


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
    two ends, and a run that samples at the retained checkpoint."""

    units: int
    run: Callable[[], None]
    marked: Callable[[Sampler, Sampler], None]
    checkpoint: Callable[[Sampler], None]


def _keyed_driver(case: lowering_support.Case) -> Driver:
    codec = EntityRowCodec(lowering_support.CATALOG)
    planner: WritePlanner = build_write_planner(lowering_support.CATALOG.meta)
    units = len(case.values) if case.ingress == "typed" else len(case.wire_rows)

    def run() -> None:
        lowering_support.lower(case, codec, planner)

    def marked(opened: Sampler, closed: Sampler) -> None:
        opened()
        lowering_support.lower(case, codec, planner)
        closed()

    def checkpoint(sample: Sampler) -> None:
        settled = lowering_support.settle(case, codec, planner)
        sample()
        assert settled.plan is not None

    return Driver(units, run, marked, checkpoint)


def _acquisition_driver(case: acquisition_support.Case) -> Driver:
    handle: Database = acquisition_support.database(case)

    def run() -> None:
        acquisition_support.acquire(handle, case)

    def marked(opened: Sampler, closed: Sampler) -> None:
        acquisition_support.acquire(handle, case, opened=opened, closed=closed)

    def checkpoint(sample: Sampler) -> None:
        acquisition_support.acquire(handle, case, closed=sample)

    return Driver(case.rows, run, marked, checkpoint)


def _model_driver() -> Driver:
    def prepare() -> object:
        return prepare_model(DomainModel(*lowering_support.ENTITY_CLASSES), edition=MODEL_EDITION)

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


def driver_for(name: str) -> Driver:
    window = WINDOWS[name]
    if window == KEYED_WINDOW:
        return _keyed_driver(lowering_support.case_named(name))
    if window == ACQUISITION_WINDOW:
        return _acquisition_driver(acquisition_support.case_named(name))
    return _model_driver()


def _timed(driver: Driver) -> int:
    marks: list[int] = []

    def opened() -> None:
        marks.append(perf_counter_ns())

    def closed() -> None:
        marks.append(perf_counter_ns())

    driver.marked(opened, closed)
    return marks[1] - marks[0]


def _peak(driver: Driver) -> int:
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
    with observer:
        driver.run()
    return observer.observation()


def _per_unit(samples: Sequence[int | float], units: int) -> list[float]:
    return [float(sample) / units for sample in samples]


def measure(name: str, *, warmups: int, measured: int) -> dict[str, object]:
    """One case's per-unit samples over its window, and its pass observations."""
    if warmups < 0 or measured <= 0:
        raise ValueError("warmups must be non-negative and measured must be positive")
    window = WINDOWS[name]
    driver = driver_for(name)
    observe = window == KEYED_WINDOW

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
        kept = retained(driver.checkpoint)
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
