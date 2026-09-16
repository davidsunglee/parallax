from __future__ import annotations

import io
import json
import sys
from contextlib import redirect_stdout
from typing import cast

import write_lowering_reading
from tests.unit import _predicate_acquisition_support as acquisition_support
from tests.unit import _write_lowering_support as lowering_support
from tests.unit.memory_instruments import (
    in_a_child_interpreter,
    serve_one_measurement,
)
from write_lowering_reading import CASE_NAMES, Observer


def test_observer_counts_nested_calls() -> None:
    def inner() -> None:
        return None

    def outer() -> None:
        inner()
        inner()

    observer = Observer({"outer": outer, "inner": inner})
    with observer:
        outer()

    observation = observer.observation()
    assert observation.calls == {"outer": 1, "inner": 2}


def test_child_case_names_match_the_shared_workloads() -> None:
    assert (
        *(case.name for case in lowering_support.CASES),
        *(case.name for case in acquisition_support.CASES),
        write_lowering_reading.MODEL_CASE,
    ) == CASE_NAMES


def _reading(name: str) -> dict[str, object]:
    output = io.StringIO()
    with redirect_stdout(output):
        assert write_lowering_reading.main([name, "--warmups", "1", "--measured", "2"]) == 0
    lines = output.getvalue().splitlines()
    assert len(lines) == 1
    return cast("dict[str, object]", json.loads(lines[0]))


def _assert_reading(name: str, *, units: int) -> None:
    reading = _reading(name)
    window = write_lowering_reading.WINDOWS[name]
    assert set(reading) == {
        "case",
        "window",
        "units",
        "samples",
        "calls",
        "warmups",
        "measured",
        "retainedWarmups",
    }
    assert reading["case"] == name
    assert reading["window"] == window
    assert reading["units"] == units
    assert reading["warmups"] == 1
    assert reading["measured"] == 2
    assert reading["retainedWarmups"] == write_lowering_reading.RETAINED_WARMUPS
    samples = cast("dict[str, list[float]]", reading["samples"])
    assert set(samples) == set(write_lowering_reading.METRICS)
    assert len(samples["elapsedUs"]) == 2
    assert len(samples["transientBytes"]) == 2
    assert len(samples["retainedBytes"]) == 1
    assert all(value > 0 for value in samples["elapsedUs"])
    assert all(value > 0 for value in samples["transientBytes"])
    assert samples["retainedBytes"][0] > 0
    calls = cast("dict[str, float]", reading["calls"])
    if window == write_lowering_reading.KEYED_WINDOW:
        assert set(calls) == set(write_lowering_reading.OBSERVED_FUNCTIONS)
        assert all(value >= 0 for value in calls.values())
    else:
        assert calls == {}


@in_a_child_interpreter
def test_a_typed_opening_insert_reads_its_keyed_window() -> None:
    _assert_reading("txtime.opening.columns.typed", units=1)


@in_a_child_interpreter
def test_a_wire_changed_document_successor_reads_its_keyed_window() -> None:
    _assert_reading("txtime.changed.document.wire", units=1)


@in_a_child_interpreter
def test_a_bitemporal_interior_update_reads_its_keyed_window() -> None:
    _assert_reading("bitemporal.interior.columns.typed", units=1)


@in_a_child_interpreter
def test_a_geometry_insert_reads_its_keyed_window() -> None:
    _assert_reading("geometry.many-8.document.typed", units=1)


@in_a_child_interpreter
def test_a_changed_ancestor_successor_reads_its_keyed_window() -> None:
    _assert_reading("ancestor.width-64.document.typed", units=1)


@in_a_child_interpreter
def test_an_acquisition_family_reads_its_window_per_resolved_row() -> None:
    case = acquisition_support.CASES[0]
    _assert_reading(case.name, units=case.rows)


@in_a_child_interpreter
def test_the_model_preparation_checkpoint_reads_one_preparation() -> None:
    _assert_reading(write_lowering_reading.MODEL_CASE, units=1)


if __name__ == "__main__":
    serve_one_measurement(sys.argv[1])
