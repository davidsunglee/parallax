"""Take one isolated write-lowering case reading.

This script is imported only by its gated suite. Report execution starts it in a
child interpreter, where it drives one case through the production lowering
seams and answers with one JSON line.
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
from typing import Any, Final, cast

from parallax.core import document_codec
from parallax.core.entity import EntityRowCodec
from parallax.core.unit_work import WritePlanner
from parallax.snapshot.handle import build_write_planner

WORKSPACE: Final = Path(__file__).resolve().parents[1]
INSTRUMENT_MODULE: Final = WORKSPACE / "tests" / "unit" / "memory_instruments.py"
SUPPORT_MODULE: Final = WORKSPACE / "tests" / "unit" / "_write_lowering_support.py"
sys.path.insert(0, str(WORKSPACE))

from tests.unit import _write_lowering_support as lowering_support  # noqa: E402
from tests.unit import memory_instruments  # noqa: E402

if Path(memory_instruments.__file__ or "").resolve() != INSTRUMENT_MODULE:
    raise ImportError(
        f"this reading requires {INSTRUMENT_MODULE}, but resolved {memory_instruments.__file__}"
    )
if Path(lowering_support.__file__ or "").resolve() != SUPPORT_MODULE:
    raise ImportError(
        f"this reading requires {SUPPORT_MODULE}, but resolved {lowering_support.__file__}"
    )

from tests.unit.memory_instruments import untraced  # noqa: E402

_MONITORING_TOOL_IDS: Final = range(6)
OBSERVED_FUNCTIONS: Final[Mapping[str, Callable[..., object]]] = {
    "shapeOfDeclaration": document_codec.shape_of_declaration,
    "entityShape": document_codec.entity_shape,
    "occurrenceShape": document_codec.occurrence_shape,
    "encodeDocument": document_codec.encode_document,
    "encodeMany": document_codec.encode_many,
}
CASE_NAMES: Final = tuple(case.name for case in lowering_support.CASES)


@dataclass(frozen=True, slots=True)
class Observation:
    calls: Mapping[str, int]
    attributable: int


class Observer(AbstractContextManager["Observer"]):
    """Count selected Python calls and attribute inclusive outermost work."""

    def __init__(
        self,
        functions: Mapping[str, Callable[..., object]],
        read: Callable[[], int],
    ) -> None:
        self._read = read
        self._names = {
            cast("CodeType", cast("Any", function).__code__): name
            for name, function in functions.items()
        }
        self._calls = dict.fromkeys(functions, 0)
        self._attributable = 0
        self._depth = 0
        self._started = 0
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
            monitoring.register_callback(tool, monitoring.events.PY_START, self._on_start)
            monitoring.register_callback(tool, monitoring.events.PY_RETURN, self._on_return)
            events = monitoring.events.PY_START | monitoring.events.PY_RETURN
            for code in self._names:
                monitoring.set_local_events(tool, code, events)
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

    def _on_start(self, code: CodeType, _offset: int) -> None:
        if self._depth == 0:
            self._started = self._read()
        self._depth += 1

    def _on_return(self, code: CodeType, _offset: int, _value: object) -> None:
        self._calls[self._names[code]] += 1
        self._depth -= 1
        if self._depth == 0:
            self._attributable += max(0, self._read() - self._started)

    def observation(self) -> Observation:
        if self._tool is not None or self._depth != 0:
            raise RuntimeError("an observation is available only after clean observer teardown")
        return Observation(calls=dict(self._calls), attributable=self._attributable)


def _collaborators() -> tuple[EntityRowCodec, WritePlanner]:
    return (
        EntityRowCodec(lowering_support.CATALOG),
        build_write_planner(lowering_support.CATALOG.meta),
    )


def _timed(case: lowering_support.Case) -> tuple[int, int]:
    codec, planner = _collaborators()
    started = perf_counter_ns()
    rows = lowering_support.lower(case, codec, planner)
    return rows, perf_counter_ns() - started


def _peak(case: lowering_support.Case) -> tuple[int, int]:
    codec, planner = _collaborators()
    gc.collect()
    gc.collect()
    floor, _ = tracemalloc.get_traced_memory()
    tracemalloc.reset_peak()
    rows = lowering_support.lower(case, codec, planner)
    _, high_water = tracemalloc.get_traced_memory()
    return rows, max(0, high_water - floor)


def _observed(case: lowering_support.Case, read: Callable[[], int]) -> tuple[int, Observation]:
    codec, planner = _collaborators()
    observer = Observer(OBSERVED_FUNCTIONS, read)
    with observer:
        rows = lowering_support.lower(case, codec, planner)
    return rows, observer.observation()


def _current_bytes() -> int:
    return tracemalloc.get_traced_memory()[0]


def _per_row(samples: Sequence[int | float], rows: int) -> float:
    return float(median(samples)) / rows


def measure(case: lowering_support.Case, *, warmups: int, measured: int) -> dict[str, object]:
    """One case's unobserved totals and observed builder attribution."""
    if warmups < 0 or measured <= 0:
        raise ValueError("warmups must be non-negative and measured must be positive")

    with untraced():
        for _ in range(warmups):
            codec, planner = _collaborators()
            lowering_support.lower(case, codec, planner)

        elapsed: list[int] = []
        observed_elapsed: list[int] = []
        attributable_elapsed: list[int] = []
        call_samples: dict[str, list[int]] = {name: [] for name in OBSERVED_FUNCTIONS}
        expected_rows: int | None = None
        for _ in range(measured):
            rows, total = _timed(case)
            expected_rows = rows if expected_rows is None else expected_rows
            if rows != expected_rows:
                raise RuntimeError("a write-lowering case changed row count between samples")
            elapsed.append(total)

            codec, planner = _collaborators()
            observer = Observer(OBSERVED_FUNCTIONS, perf_counter_ns)
            started = perf_counter_ns()
            with observer:
                observed_rows = lowering_support.lower(case, codec, planner)
            observed_elapsed.append(perf_counter_ns() - started)
            observation = observer.observation()
            if observed_rows != expected_rows:
                raise RuntimeError("an observed sample lowered a different row count")
            attributable_elapsed.append(observation.attributable)
            for name, count in observation.calls.items():
                call_samples[name].append(count)

    transient: list[int] = []
    attributable_transient: list[int] = []
    tracemalloc.start()
    try:
        with untraced():
            for _ in range(measured):
                rows, peak = _peak(case)
                if rows != expected_rows:
                    raise RuntimeError("a memory sample lowered a different row count")
                transient.append(peak)

                observed_rows, observation = _observed(case, _current_bytes)
                if observed_rows != expected_rows:
                    raise RuntimeError("an observed memory sample lowered a different row count")
                attributable_transient.append(observation.attributable)
                if observation.calls != {
                    name: samples[-1] for name, samples in call_samples.items()
                }:
                    raise RuntimeError("timed and memory observations saw different call counts")
    finally:
        tracemalloc.stop()

    assert expected_rows is not None
    elapsed_median = float(median(elapsed))
    observed_elapsed_median = float(median(observed_elapsed))
    return {
        "rows": expected_rows,
        "perRow": {
            "elapsedUs": elapsed_median / (expected_rows * 1_000),
            "transientBytes": _per_row(transient, expected_rows),
        },
        "calls": {name: _per_row(samples, expected_rows) for name, samples in call_samples.items()},
        "attributable": {
            "elapsedUs": _per_row(attributable_elapsed, expected_rows) / 1_000,
            "transientBytes": _per_row(attributable_transient, expected_rows),
        },
        "observation": {"elapsedRatio": observed_elapsed_median / elapsed_median},
        "warmups": warmups,
        "measured": measured,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=CASE_NAMES)
    parser.add_argument("--warmups", required=True, type=int)
    parser.add_argument("--measured", required=True, type=int)
    args = parser.parse_args(argv)
    try:
        reading = measure(
            lowering_support.case_named(args.case),
            warmups=args.warmups,
            measured=args.measured,
        )
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps(reading, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
