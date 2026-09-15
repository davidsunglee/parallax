from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from typing import cast

import pytest

import write_lowering_overhead as report
from parallax.conformance.budget import BudgetContract
from parallax.conformance.cost_envelope import validate
from tests.unit import _write_lowering_support as lowering_support


def _reading(
    case: str,
    *,
    rows: int = 1,
    elapsed: float = 10.0,
    transient: float = 100.0,
    attributable_elapsed: float = 2.0,
    attributable_transient: float = 30.0,
) -> report.ChildReading:
    return report.ChildReading(
        case,
        rows,
        elapsed,
        transient,
        dict.fromkeys(report.CALL_NAMES, 1.0),
        attributable_elapsed,
        attributable_transient,
        1.25,
        report.WARMUPS,
        report.MEASURED,
    )


def _matrix(*runtimes: str) -> report.Matrix:
    return {runtime: {case: _reading(case) for case in report.CASE_NAMES} for runtime in runtimes}


def test_parent_case_names_match_the_shared_workload() -> None:
    assert tuple(case.name for case in lowering_support.CASES) == report.CASE_NAMES


def test_child_protocol_selects_the_runtime_and_sampling_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current = report._child_command(  # pyright: ignore[reportPrivateUsage] - protocol under test
        report.CURRENT_MINOR, report.CASE_NAMES[0]
    )
    other = report._child_command(  # pyright: ignore[reportPrivateUsage] - protocol under test
        "9.99", report.CASE_NAMES[0]
    )
    assert current[0] != "uv"
    assert other[:6] == ["uv", "run", "--frozen", "--python", "9.99", "python"]
    assert current[-4:] == [
        "--warmups",
        str(report.WARMUPS),
        "--measured",
        str(report.MEASURED),
    ]
    monkeypatch.setenv("PYTHONHOME", "wrong-runtime")
    monkeypatch.setenv("VIRTUAL_ENV", "wrong-environment")
    monkeypatch.setenv("COVERAGE_PROCESS_START", "coverage")
    current_environment = report._child_environment(  # pyright: ignore[reportPrivateUsage]
        report.CURRENT_MINOR
    )
    other_environment = report._child_environment(  # pyright: ignore[reportPrivateUsage]
        "9.99"
    )
    assert current_environment["PYTHONHASHSEED"] == "0"
    assert current_environment["PYTHONPATH"] == os.pathsep.join(
        entry for entry in report.sys.path if entry
    )
    assert "COVERAGE_PROCESS_START" not in current_environment
    assert not {"PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"} & other_environment.keys()
    assert other_environment["UV_PROJECT_ENVIRONMENT"].endswith("parallax-write-lowering-9.99")


def test_envelope_retains_every_case_address_and_row_weighted_share() -> None:
    matrix = _matrix("3.13", "3.14")
    first = report.CASE_NAMES[0]
    matrix["3.13"][first] = _reading(
        first,
        rows=3,
        elapsed=20.0,
        transient=200.0,
        attributable_elapsed=10.0,
        attributable_transient=100.0,
    )
    contract = BudgetContract.load()
    envelope = report.build_envelope(
        contract,
        report._provenance(contract),  # pyright: ignore[reportPrivateUsage] - entrypoint seam
        matrix,
    )

    assert envelope.subject == report.SUBJECT
    assert envelope.authority == "non-authoritative"
    assert envelope.comparisons == ()
    assert envelope.incomplete == ()
    assert envelope.errors == ()
    assert envelope.provenance.workload_digest == lowering_support.write_lowering_digest()
    assert envelope.provenance.postgres == "not-used"
    assert envelope.provenance.sampling == {
        "warmups": report.WARMUPS,
        "measured": report.MEASURED,
    }
    validate(envelope)

    addresses = {(reading.workload, reading.cell) for reading in envelope.readings}
    expected: set[tuple[str, str]] = set()
    for runtime in matrix:
        workload = f"cpython-{runtime}"
        for case in report.CASE_NAMES:
            expected.update(
                (workload, f"{case}.{cell}")
                for cell in (
                    "perRow.elapsedUs",
                    "perRow.transientBytes",
                    *(f"calls.{name}" for name in report.CALL_NAMES),
                    "attributable.elapsedUs",
                    "attributable.transientBytes",
                    "share.elapsed",
                    "share.transient",
                    "observation.elapsedRatio",
                )
            )
        expected.update((workload, cell) for cell in ("all.share.elapsed", "all.share.transient"))
    assert addresses == expected
    aggregates = {
        (reading.workload, reading.cell): reading.value
        for reading in envelope.readings
        if reading.cell.startswith("all.share.")
    }
    assert aggregates[("cpython-3.13", "all.share.elapsed")] == pytest.approx(36 / 90)
    assert aggregates[("cpython-3.13", "all.share.transient")] == pytest.approx(390 / 900)
    assert aggregates[("cpython-3.14", "all.share.elapsed")] == pytest.approx(0.2)
    assert aggregates[("cpython-3.14", "all.share.transient")] == pytest.approx(0.3)


def test_canary_is_a_schema_valid_complete_envelope() -> None:
    envelope = report.canary(BudgetContract.load())
    validate(envelope)
    assert envelope.subject == report.SUBJECT
    assert len(envelope.readings) == len(report.CASE_NAMES) * 12 + 2


def test_child_output_decodes_from_its_final_line() -> None:
    document = {
        "rows": 2,
        "perRow": {"elapsedUs": 10.0, "transientBytes": 100.0},
        "calls": dict.fromkeys(report.CALL_NAMES, 1.0),
        "attributable": {"elapsedUs": 2.0, "transientBytes": 30.0},
        "observation": {"elapsedRatio": 1.25},
        "warmups": report.WARMUPS,
        "measured": report.MEASURED,
    }
    decoded = report._decoded(  # pyright: ignore[reportPrivateUsage] - child protocol under test
        f"ignored diagnostic\n{json.dumps(document)}\n", "opening.columns"
    )
    assert decoded == _reading("opening.columns", rows=2, attributable_transient=30.0)


@pytest.mark.parametrize(
    "output",
    [
        "",
        "not-json",
        json.dumps(
            {
                "rows": 0,
                "perRow": {"elapsedUs": 10.0, "transientBytes": 100.0},
                "calls": dict.fromkeys(report.CALL_NAMES, 1.0),
                "attributable": {"elapsedUs": 2.0, "transientBytes": 30.0},
                "observation": {"elapsedRatio": 1.2},
                "warmups": report.WARMUPS,
                "measured": report.MEASURED,
            }
        ),
        json.dumps(
            {
                "rows": 1,
                "perRow": {"elapsedUs": 10.0, "transientBytes": 100.0},
                "calls": {},
                "attributable": {"elapsedUs": 2.0, "transientBytes": 30.0},
                "observation": {"elapsedRatio": 1.2},
                "warmups": report.WARMUPS,
                "measured": report.MEASURED,
            }
        ),
    ],
)
def test_invalid_child_output_is_an_unavailable_cell(output: str) -> None:
    assert isinstance(
        report._decoded(  # pyright: ignore[reportPrivateUsage] - child protocol under test
            output, "opening.columns"
        ),
        str,
    )


def test_successful_entrypoint_stdout_is_only_the_owned_envelope(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    matrix = _matrix("3.14")
    monkeypatch.setattr(report, "supported_minors", lambda: ("3.14",))

    def child(runtime: str, case: str) -> report.Cell:
        return matrix[runtime][case]

    monkeypatch.setattr(report, "in_a_child", child)

    assert report.main([]) == 0
    captured = capsys.readouterr()
    document = cast("Mapping[str, object]", json.loads(captured.out))
    assert captured.err == ""
    assert document["subject"] == report.SUBJECT
    assert cast("Sequence[object]", document["readings"])
    validate(document)


def test_entrypoint_refuses_arguments_and_an_incomplete_matrix(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert report.main(["unexpected"]) == 2
    assert "usage:" in capsys.readouterr().err

    monkeypatch.setattr(report, "supported_minors", lambda: ("3.14",))

    def failing_child(_runtime: str, case: str) -> report.Cell:
        return f"{case} failed"

    monkeypatch.setattr(report, "in_a_child", failing_child)
    assert report.main([]) == 3
    diagnostic = capsys.readouterr().err
    assert "the matrix is incomplete" in diagnostic
    assert all(case in diagnostic for case in report.CASE_NAMES)


def test_missing_cells_and_shape_totals_refuse_incomplete_or_zero_data() -> None:
    assert report.missing_cells({}, ("3.14",), report.CASE_NAMES) == [
        f"CPython 3.14, {case}: no child was run" for case in report.CASE_NAMES
    ]
    with pytest.raises(ValueError, match="matrix is incomplete"):
        report.build_envelope(
            BudgetContract.load(),
            report._provenance(  # pyright: ignore[reportPrivateUsage] - entrypoint seam
                BudgetContract.load()
            ),
            {"3.14": {}},
        )
    zero = _reading(report.CASE_NAMES[0], elapsed=0.0)
    with pytest.raises(ValueError, match="total must be positive"):
        report._case_readings(  # pyright: ignore[reportPrivateUsage] - arithmetic under test
            "cpython-3.14", zero
        )
