from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import cast

import pytest

import instance_state_overhead as report
from parallax.conformance.budget import BudgetContract
from parallax.conformance.cost_envelope import validate
from parallax.conformance.workloads import workload_digest
from tests.unit._instance_state_support import ARMS, REPORTED, Scenario


def test_envelope_retains_the_complete_matrix_and_member_provenance() -> None:
    matrix = _matrix()
    envelope = report.build_envelope(
        BudgetContract.load(),
        report._provenance(  # pyright: ignore[reportPrivateUsage] - the entrypoint seam
            BudgetContract.load(), matrix
        ),
        matrix,
    )

    assert envelope.subject == report.SUBJECT
    assert envelope.authority == "non-authoritative"
    assert envelope.incomplete == ()
    assert envelope.errors == ()
    assert envelope.readings
    assert envelope.provenance.workload_digest == workload_digest()
    assert envelope.provenance.postgres == "not-used"
    assert envelope.provenance.sampling["scenarios"] == [scenario.name for scenario in REPORTED]
    validate(envelope)

    addresses = {(reading.workload, reading.cell) for reading in envelope.readings}
    assert len(addresses) == len(envelope.readings)
    assert addresses == _expected_addresses(tuple(matrix))


def test_envelope_comparisons_are_the_existing_advisory_rules() -> None:
    matrix = _matrix(compact_retention=0.90, compact_operation_ratio=2.0)
    contract = BudgetContract.load()
    envelope = report.build_envelope(
        contract,
        report._provenance(contract, matrix),  # pyright: ignore[reportPrivateUsage]
        matrix,
    )

    expected_cells = {
        "aggregate.retained.reduction",
        *(
            f"operation.{operation.name.replace(' ', '-')}.armAgainstArm"
            for operation in report.OPERATIONS
        ),
    }
    assert {comparison.cell for comparison in envelope.comparisons} == expected_cells
    aggregate = next(
        comparison
        for comparison in envelope.comparisons
        if comparison.cell == "aggregate.retained.reduction"
    )
    assert (aggregate.operator, aggregate.limit, aggregate.outcome) == (
        "at-least",
        report.AGGREGATE_TARGET,
        "outside",
    )
    operation_comparisons = [
        comparison
        for comparison in envelope.comparisons
        if comparison.cell.startswith("operation.")
    ]
    assert len(operation_comparisons) == len(report.OPERATIONS)
    assert all(
        (comparison.operator, comparison.limit, comparison.outcome)
        == ("at-most", report.REGRESSION_LIMIT, "outside")
        for comparison in operation_comparisons
    )
    reading_addresses = {(reading.workload, reading.cell) for reading in envelope.readings}
    assert all(
        (comparison.workload, comparison.cell) in reading_addresses
        for comparison in envelope.comparisons
    )


def test_successful_entrypoint_stdout_is_only_the_owned_envelope(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    matrix = _matrix()
    runtime = next(iter(matrix))
    monkeypatch.setattr(report, "supported_minors", lambda: (runtime,))

    def child(selected_runtime: str, scenario: Scenario) -> report.Cell:
        return matrix[selected_runtime][scenario.name]

    monkeypatch.setattr(report, "in_a_child", child)

    assert report.main([]) == 0
    captured = capsys.readouterr()
    document = cast("Mapping[str, object]", json.loads(captured.out))
    assert captured.err == ""
    assert document["subject"] == report.SUBJECT
    assert cast("Sequence[object]", document["readings"])
    validate(document)


def _expected_addresses(runtimes: tuple[str, ...]) -> set[tuple[str, str]]:
    arm_metrics = {
        report._metric_name(name)  # pyright: ignore[reportPrivateUsage] - emitted contract
        for name in report.ArmReading._fields
    } | {"lifecycleBytes", "transientBytes", "unreproducedNs"}
    expected: set[tuple[str, str]] = set()
    for runtime in runtimes:
        for scenario in REPORTED:
            workload = f"cpython-{runtime}/{scenario.name}"
            expected.update((workload, cell) for cell in ("fields", "warmups"))
            expected.update(
                (workload, f"{arm.name}.{metric}") for arm in ARMS for metric in arm_metrics
            )
            expected.update(
                (workload, cell)
                for cell in (
                    "vsLegacy.retainedReduction",
                    "vsLegacy.bareReduction",
                    "vsOrdinary.retainedReduction",
                    "vsOrdinary.bareReduction",
                )
            )
        workload = f"cpython-{runtime}"
        expected.update(
            (workload, f"{aggregate}.{metric}")
            for aggregate in (
                "aggregate.retained",
                "aggregate.bare",
                "vsOrdinary.retained",
            )
            for metric in ("before", "after", "reduction")
        )
        expected.update(
            (workload, f"operation.{operation.name.replace(' ', '-')}.{comparison}")
            for operation in report.OPERATIONS
            for comparison in ("armAgainstArm", "likeForLike", "vsOrdinary")
        )
    return expected


def _arm(
    scenario: Scenario,
    retained: int,
    operation_ratio: float,
    *,
    legacy: bool,
) -> report.ArmReading:
    cells = len(scenario.values) + len(scenario.unloaded)
    baseline_ns = float(max(cells, 1) * 100)
    scaled_ns = baseline_ns if legacy else baseline_ns * operation_ratio
    return report.ArmReading(
        cells=cells,
        retained_bytes=retained,
        bare_bytes=retained - max(cells, 1),
        peak_bytes=retained + max(cells, 1),
        construct_ns=scaled_ns,
        call_ns=baseline_ns / max(cells, 1),
        scaffolding_ns=0.0,
        read_ns=scaled_ns,
        dump_ns=scaled_ns,
    )


def _reading(
    scenario: Scenario,
    compact_retention: float,
    compact_operation_ratio: float,
) -> report.Reading:
    scale = max(len(scenario.values) + len(scenario.unloaded), 1)
    legacy_retained = scale * 100
    compact_retained = round(legacy_retained * compact_retention)
    return report.Reading(
        scenario.name,
        scenario.summary,
        len(scenario.values),
        BudgetContract.load().timing_warmups,
        _arm(scenario, legacy_retained * 2, 1.0, legacy=True),
        _arm(scenario, legacy_retained, 1.0, legacy=True),
        _arm(
            scenario,
            compact_retained,
            compact_operation_ratio,
            legacy=False,
        ),
    )


def _matrix(
    *,
    compact_retention: float = 0.50,
    compact_operation_ratio: float = 1.0,
) -> report.Matrix:
    runtime = report.CURRENT_MINOR
    return {
        runtime: {
            scenario.name: _reading(
                scenario,
                compact_retention,
                compact_operation_ratio,
            )
            for scenario in REPORTED
        }
    }
