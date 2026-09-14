from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from typing import Any, cast

import pytest

from cost_report import (
    MEMBERS,
    Member,
    MemberResult,
    collect,
    portfolio_document,
    report_recipes,
    validate_snapshot_matrix,
    verify,
)
from parallax.conformance.budget import BudgetContract
from parallax.conformance.cost_envelope import CostReportEnvelope
from snapshot_delivery_overhead import (
    ChildReading,
    build_envelope,
    canary,
    expanded_cells,
    is_memory_cell,
    is_scaling_cell,
    unit,
)


def _just_report_recipes() -> frozenset[str]:
    completed = subprocess.run(
        ["just", "--dump", "--dump-format", "json"],
        cwd=Path(__file__).resolve().parents[4],
        capture_output=True,
        text=True,
        check=True,
    )
    document = cast("dict[str, Any]", json.loads(completed.stdout))
    recipes = cast("dict[str, object]", document["recipes"])
    return frozenset(
        name
        for name in recipes
        if name.startswith("python-report-") and name != "python-report-cost"
    )


def _complete_snapshot(contract: BudgetContract) -> dict[str, Any]:
    provenance = canary(
        contract,
        lambda _request: ChildReading(
            1.0,
            "ms",
            (1.0,) * contract.timing_measured,
        ),
    ).provenance
    results: dict[tuple[str, str], tuple[ChildReading, ...]] = {}
    for cell in expanded_cells(contract):
        count = (
            contract.memory_children * len(contract.memory_scaling_arms)
            if is_scaling_cell(cell.path)
            else contract.memory_children
            if is_memory_cell(cell.path)
            else 1
        )
        samples = (
            () if is_memory_cell(cell.path) else (float(cell.value),) * contract.timing_measured
        )
        results[(cell.workload, cell.path)] = tuple(
            ChildReading(float(cell.value), unit(cell.path), samples) for _ in range(count)
        )
    return build_envelope(contract, provenance, results).document()


def _optional_document(member: Member) -> dict[str, object]:
    contract = BudgetContract.load()
    return CostReportEnvelope(
        member.subject,
        canary(
            contract,
            lambda _request: ChildReading(
                1.0,
                "ms",
                (1.0,) * contract.timing_measured,
            ),
        ).provenance,
        "non-authoritative",
    ).document()


def _clear_readings(document: dict[str, Any]) -> None:
    cast("list[object]", document["readings"]).clear()


def _clear_comparisons(document: dict[str, Any]) -> None:
    cast("list[object]", document["comparisons"]).clear()


def _duplicate_reading(document: dict[str, Any]) -> None:
    readings = cast("list[dict[str, object]]", document["readings"])
    readings.append(deepcopy(readings[0]))


def _wrong_reading_unit(document: dict[str, Any]) -> None:
    cast("list[dict[str, object]]", document["readings"])[0]["unit"] = "wrong"


def _remove_samples(document: dict[str, Any]) -> None:
    cast("list[dict[str, object]]", document["readings"])[0]["samples"] = []


def _forge_value(document: dict[str, Any]) -> None:
    cast("list[dict[str, object]]", document["readings"])[0]["value"] = -1


def _forge_outcome(document: dict[str, Any]) -> None:
    cast("list[dict[str, object]]", document["comparisons"])[0]["outcome"] = "outside"


def test_collector_members_are_the_python_report_command_graph() -> None:
    assert report_recipes() == _just_report_recipes()


def test_collection_attempts_every_member_and_fails_late_for_the_required_one() -> None:
    attempted: list[str] = []

    def failing(member: Member) -> tuple[int, str, str]:
        recipe = member.recipe
        attempted.append(recipe)
        return (7, "", f"{recipe} failed")

    results, failed_required = collect(failing)
    assert attempted == [member.recipe for member in MEMBERS]
    assert len(results) == len(MEMBERS)
    assert failed_required


def test_verify_refuses_a_missing_required_envelope() -> None:
    assert verify({"schemaVersion": 1, "members": [], "failures": []}) == [
        "the portfolio has no required snapshot-delivery envelope"
    ]


def test_portfolio_document_preserves_optional_failures() -> None:
    optional = MEMBERS[1]
    document = portfolio_document((MemberResult(optional, None, "unavailable"),))
    assert document["failures"] == [
        {"recipe": optional.recipe, "required": False, "message": "unavailable"}
    ]


def test_snapshot_member_canary_emits_a_schema_valid_envelope() -> None:
    envelope = canary(
        BudgetContract.load(),
        lambda _request: ChildReading(
            1.0,
            "ms",
            (1.0,) * BudgetContract.load().timing_measured,
        ),
    )
    assert envelope.subject == "snapshot-delivery"
    assert envelope.authority == "non-authoritative"
    assert envelope.incomplete


def test_outside_budget_outcomes_do_not_fail_collection() -> None:
    contract = BudgetContract.load()
    document = _complete_snapshot(contract)
    readings = cast("list[dict[str, object]]", document["readings"])
    comparisons = cast("list[dict[str, object]]", document["comparisons"])
    limit = cast("float", comparisons[0]["limit"])
    readings[0]["value"] = limit * 2
    readings[0]["samples"] = [limit * 2] * contract.timing_measured
    comparisons[0]["outcome"] = "outside"

    def run(member: Member) -> tuple[int, str, str]:
        if member.required:
            return (0, json.dumps(document), "")
        return (9, "", "optional report unavailable")

    results, failed_required = collect(run)
    assert not failed_required
    assert results[0].envelope is not None


def test_collection_decodes_each_members_own_envelope() -> None:
    snapshot = _complete_snapshot(BudgetContract.load())

    def run(member: Member) -> tuple[int, str, str]:
        document = snapshot if member.required else _optional_document(member)
        return (0, json.dumps(document), "")

    results, failed_required = collect(run)
    assert not failed_required
    assert [result.envelope["subject"] for result in results if result.envelope] == [
        member.subject for member in MEMBERS
    ]


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (_clear_readings, "reading matrix is not exact"),
        (_clear_comparisons, "comparison matrix is not exact"),
        (_duplicate_reading, "duplicate Snapshot reading"),
        (_wrong_reading_unit, "reading unit"),
        (_remove_samples, "samples, expected"),
        (_forge_value, "disagrees with sample median"),
        (_forge_outcome, "comparison outcome"),
    ],
)
def test_snapshot_matrix_validation_rejects_semantic_forgeries(
    mutate: Callable[[dict[str, Any]], None], message: str
) -> None:
    contract = BudgetContract.load()
    document = _complete_snapshot(contract)
    mutate(document)
    with pytest.raises(ValueError, match=message):
        validate_snapshot_matrix(document, contract)


def test_snapshot_matrix_validation_requires_every_scaling_arm() -> None:
    contract = BudgetContract.load()
    document = _complete_snapshot(contract)
    reading = next(
        reading
        for reading in cast("list[dict[str, object]]", document["readings"])
        if str(reading["cell"]).startswith("streamedMemory.")
    )
    samples = cast("list[float]", reading["samples"])
    del samples[-contract.memory_children :]
    with pytest.raises(ValueError, match="samples, expected"):
        validate_snapshot_matrix(document, contract)


def test_verify_rejects_a_semantically_incomplete_snapshot_matrix() -> None:
    document = _complete_snapshot(BudgetContract.load())
    cast("list[object]", document["comparisons"]).clear()
    failures = verify({"schemaVersion": 1, "members": [document], "failures": []})
    assert len(failures) == 1
    assert "comparison matrix is not exact" in failures[0]


def test_collection_attempts_later_members_after_an_invalid_required_matrix() -> None:
    attempted: list[str] = []
    snapshot = _complete_snapshot(BudgetContract.load())
    cast("list[object]", snapshot["readings"]).clear()

    def run(member: Member) -> tuple[int, str, str]:
        attempted.append(member.recipe)
        document = snapshot if member.required else _optional_document(member)
        return (0, json.dumps(document), "")

    results, failed_required = collect(run)
    assert attempted == [member.recipe for member in MEMBERS]
    assert failed_required
    assert results[0].envelope is None
    assert all(result.envelope is not None for result in results[1:])
