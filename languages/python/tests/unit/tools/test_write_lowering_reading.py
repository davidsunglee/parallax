from __future__ import annotations

import io
import json
import sys
from contextlib import redirect_stdout
from typing import cast

import write_lowering_reading
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


def test_child_case_names_match_the_shared_workload() -> None:
    assert tuple(case.name for case in lowering_support.CASES) == CASE_NAMES


def _reading(name: str) -> dict[str, object]:
    output = io.StringIO()
    with redirect_stdout(output):
        assert write_lowering_reading.main([name, "--warmups", "1", "--measured", "1"]) == 0
    lines = output.getvalue().splitlines()
    assert len(lines) == 1
    return cast("dict[str, object]", json.loads(lines[0]))


def _assert_reading(name: str) -> None:
    case = lowering_support.case_named(name)
    reading = _reading(name)
    assert set(reading) == {
        "rows",
        "perRow",
        "calls",
        "warmups",
        "measured",
    }
    assert reading["rows"] == len(case.values)
    assert reading["warmups"] == 1
    assert reading["measured"] == 1

    per_row = cast("dict[str, float]", reading["perRow"])
    calls = cast("dict[str, float]", reading["calls"])
    assert set(per_row) == {"elapsedUs", "transientBytes"}
    assert set(calls) == {
        "shapeOfDeclaration",
        "entityShape",
        "occurrenceShape",
        "encodeDocument",
        "encodeMany",
    }
    assert all(value > 0 for value in per_row.values())
    removed = {"shapeOfDeclaration", "entityShape", "occurrenceShape"}
    assert all(calls[builder] == 0 for builder in removed)
    assert all(value > 0 for builder, value in calls.items() if builder not in removed)


@in_a_child_interpreter
def test_opening_columns_reading() -> None:
    _assert_reading("opening.columns")


@in_a_child_interpreter
def test_opening_document_reading() -> None:
    _assert_reading("opening.document")


@in_a_child_interpreter
def test_successor_columns_reading() -> None:
    _assert_reading("successor.columns")


@in_a_child_interpreter
def test_successor_document_reading() -> None:
    _assert_reading("successor.document")


if __name__ == "__main__":
    serve_one_measurement(sys.argv[1])
