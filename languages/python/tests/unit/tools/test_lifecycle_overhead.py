from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from typing import Any, cast

import pytest

import lifecycle_overhead as report
from parallax.conformance.budget import BudgetContract
from tests.unit.tools._cost_report_support import lifecycle_document


def _document() -> dict[str, Any]:
    return deepcopy(lifecycle_document(BudgetContract.load()))


def _readings(document: dict[str, Any]) -> list[dict[str, Any]]:
    return cast("list[dict[str, Any]]", document["readings"])


def _comparisons(document: dict[str, Any]) -> list[dict[str, Any]]:
    return cast("list[dict[str, Any]]", document["comparisons"])


def _reading(document: dict[str, Any], workload: str, cell: str) -> dict[str, Any]:
    return next(
        reading
        for reading in _readings(document)
        if (reading["workload"], reading["cell"]) == (workload, cell)
    )


def test_a_complete_envelope_reads_and_compares_every_configuration_once() -> None:
    document = _document()
    report.validate_matrix(document)
    addresses = {(reading["workload"], reading["cell"]) for reading in _readings(document)}
    assert addresses == set(report.expected_readings())
    assert {report.WORKLOAD, *report.CONFIGURATIONS} == {workload for workload, _ in addresses}
    compared = {
        (comparison["workload"], comparison["cell"]) for comparison in _comparisons(document)
    }
    assert compared == set(report.expected_comparisons())


def _drop_reading(document: dict[str, Any]) -> None:
    _readings(document).pop()


def _drop_configuration(document: dict[str, Any]) -> None:
    last = report.CONFIGURATIONS[-1]
    document["readings"] = [r for r in _readings(document) if r["workload"] != last]
    document["comparisons"] = [c for c in _comparisons(document) if c["workload"] != last]


def _duplicate_reading(document: dict[str, Any]) -> None:
    _readings(document).append(dict(_readings(document)[0]))


def _unknown_reading(document: dict[str, Any]) -> None:
    _readings(document).append(
        {"workload": "a sixth configuration", "cell": "plain.p50", "value": 1.0, "unit": "us"}
    )


def _wrong_unit(document: dict[str, Any]) -> None:
    _reading(document, report.CONFIGURATIONS[0], "dispatchPerEvent.p95")["unit"] = "us"


def _not_a_number(document: dict[str, Any]) -> None:
    _reading(document, report.WORKLOAD, "events")["value"] = "28"


def _drop_comparison(document: dict[str, Any]) -> None:
    _comparisons(document).pop()


def _duplicate_comparison(document: dict[str, Any]) -> None:
    _comparisons(document).append(dict(_comparisons(document)[0]))


def _compare_a_reported_cell(document: dict[str, Any]) -> None:
    _comparisons(document).append(
        {
            "workload": report.CONFIGURATIONS[0],
            "cell": "plain.p50",
            "operator": "at-most",
            "limit": 1.0,
            "unit": "us",
            "outcome": "within",
        }
    )


def _forge_outcome(document: dict[str, Any]) -> None:
    comparison = _comparisons(document)[0]
    comparison["outcome"] = "outside" if comparison["outcome"] == "within" else "within"


def _move_ceiling(document: dict[str, Any]) -> None:
    _comparisons(document)[0]["limit"] = 50.0


def _comparison_unit(document: dict[str, Any]) -> None:
    _comparisons(document)[1]["unit"] = "us"


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (_drop_reading, "reading matrix is not exact: missing"),
        (_drop_configuration, "reading matrix is not exact: missing fan-out of three"),
        (_duplicate_reading, "duplicate lifecycle-overhead readings workload.events"),
        (_unknown_reading, "reading matrix is not exact: unexpected a sixth configuration"),
        (_wrong_unit, "dispatchPerEvent.p95 reading unit 'us', expected 'us/event'"),
        (_not_a_number, "is not a number"),
        (_drop_comparison, "comparison matrix is not exact: missing"),
        (_duplicate_comparison, "duplicate lifecycle-overhead comparisons"),
        (_compare_a_reported_cell, "comparison matrix is not exact: unexpected"),
        (_forge_outcome, "comparison outcome"),
        (_move_ceiling, "comparison limit 50.0, expected 5.0"),
        (_comparison_unit, "comparison unit 'us', expected 'ratio'"),
    ],
)
def test_the_matrix_refuses_every_inexact_envelope(
    mutate: Callable[[dict[str, Any]], None], message: str
) -> None:
    document = _document()
    mutate(document)
    with pytest.raises(ValueError, match=message):
        report.validate_matrix(document)
