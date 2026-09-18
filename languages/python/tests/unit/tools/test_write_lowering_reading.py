from __future__ import annotations

import io
import json
import sys
from contextlib import redirect_stdout
from typing import cast

import write_lowering_overhead
import write_lowering_reading
from parallax.core import document_codec
from parallax.core.base import INT32
from parallax.core.document_codec import Leaf, MemberShape, Occurrence, _document
from parallax.core.metamodel import Multiplicity
from parallax.core.sql_gen import _write as sql_write
from tests.unit import _predicate_acquisition_support as acquisition_support
from tests.unit import _write_lowering_support as lowering_support
from tests.unit.memory_instruments import (
    in_a_child_interpreter,
    serve_one_measurement,
)
from write_lowering_reading import CASE_NAMES, OBSERVED_FUNCTIONS, Observer


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


def test_the_observed_functions_are_the_managed_encoders_lowering_calls() -> None:
    assert tuple(OBSERVED_FUNCTIONS) == write_lowering_overhead.CALL_NAMES
    lowering = vars(sql_write)
    assert (
        OBSERVED_FUNCTIONS["encodeManagedDocument"]
        is _document.encode_managed_document
        is lowering["encode_managed_document"]
    )
    assert (
        OBSERVED_FUNCTIONS["encodeManagedMany"]
        is _document.encode_managed_many
        is lowering["encode_managed_many"]
    )
    assert not {"encodeDocument", "encodeMany"} & set(OBSERVED_FUNCTIONS)
    assert document_codec.encode_document not in OBSERVED_FUNCTIONS.values()
    assert document_codec.encode_many not in OBSERVED_FUNCTIONS.values()
    assert "encode_managed_document" not in document_codec.__all__
    assert "encode_managed_many" not in document_codec.__all__
    assert not hasattr(document_codec, "encode_managed_document")
    assert not hasattr(document_codec, "encode_managed_many")


def test_managed_encoder_observations_count_returns_not_rows() -> None:
    element = MemberShape(members=(Leaf("leaf", INT32, True),))
    shape = MemberShape(
        members=(
            Leaf("scalar", INT32, True),
            Occurrence("one", Multiplicity.ONE, False, element),
            Occurrence("many", Multiplicity.MANY, False, element),
        )
    )
    observer = Observer(OBSERVED_FUNCTIONS)
    with observer:
        _document.encode_managed_document(
            shape, {"scalar": 1, "one": {"leaf": 2}, "many": [{"leaf": 3}, {"leaf": 4}, {}]}
        )
        _document.encode_managed_document(shape, {"scalar": 5})
    calls = observer.observation().calls
    assert calls["encodeManagedDocument"] == 6
    assert calls["encodeManagedMany"] == 1
    assert calls["applyPatches"] == 0
    assert calls["detachJsonContainer"] == 0


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
