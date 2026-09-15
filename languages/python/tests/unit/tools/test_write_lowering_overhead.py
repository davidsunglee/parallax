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
) -> report.ChildReading:
    return report.ChildReading(
        case,
        rows,
        elapsed,
        transient,
        dict.fromkeys(report.CALL_NAMES, 1.0),
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


def test_envelope_retains_every_case_address() -> None:
    matrix = _matrix("3.13", "3.14")
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
                )
            )
    assert addresses == expected


def test_canary_is_a_schema_valid_complete_envelope() -> None:
    envelope = report.canary(BudgetContract.load())
    validate(envelope)
    assert envelope.subject == report.SUBJECT
    assert len(envelope.readings) == len(report.CASE_NAMES) * 7


def test_child_output_decodes_from_its_final_line() -> None:
    document = {
        "rows": 2,
        "perRow": {"elapsedUs": 10.0, "transientBytes": 100.0},
        "calls": dict.fromkeys(report.CALL_NAMES, 1.0),
        "warmups": report.WARMUPS,
        "measured": report.MEASURED,
    }
    decoded = report._decoded(  # pyright: ignore[reportPrivateUsage] - child protocol under test
        f"ignored diagnostic\n{json.dumps(document)}\n", "opening.columns"
    )
    assert decoded == _reading("opening.columns", rows=2)


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
                "warmups": report.WARMUPS,
                "measured": report.MEASURED,
            }
        ),
        json.dumps(
            {
                "rows": 1,
                "perRow": {"elapsedUs": 10.0, "transientBytes": 100.0},
                "calls": {},
                "warmups": report.WARMUPS,
                "measured": report.MEASURED,
            }
        ),
        json.dumps(
            {
                "rows": 1,
                "perRow": {"elapsedUs": 10.0, "transientBytes": 100.0},
                "calls": dict.fromkeys(report.CALL_NAMES, 1.0),
                "attributable": {"elapsedUs": -1.0},
                "observation": {"elapsedRatio": -1.0},
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


@pytest.mark.parametrize(
    ("section", "field", "value"),
    [
        (None, "rows", 1.5),
        (None, "warmups", float(report.WARMUPS)),
        (None, "measured", float(report.MEASURED)),
        ("perRow", "elapsedUs", 0),
        ("perRow", "transientBytes", -1),
        ("calls", report.CALL_NAMES[0], -1),
    ],
)
def test_semantically_invalid_child_numbers_are_unavailable(
    section: str | None,
    field: str,
    value: object,
) -> None:
    document: dict[str, object] = {
        "rows": 2,
        "perRow": {"elapsedUs": 10.0, "transientBytes": 100.0},
        "calls": dict.fromkeys(report.CALL_NAMES, 1.0),
        "warmups": report.WARMUPS,
        "measured": report.MEASURED,
    }
    target = document if section is None else cast("dict[str, object]", document[section])
    target[field] = value

    assert isinstance(
        report._decoded(  # pyright: ignore[reportPrivateUsage] - child protocol under test
            json.dumps(document), "opening.columns"
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


def test_missing_cells_and_envelope_refuse_an_incomplete_matrix() -> None:
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
