from __future__ import annotations

import json
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from cost_report import (
    MEMBERS,
    Member,
    MemberResult,
    collect,
    portfolio_document,
    report_recipes,
    verify,
)
from parallax.conformance.budget import BudgetContract
from snapshot_delivery_overhead import ChildReading, canary


def _just_report_recipes() -> frozenset[str]:
    completed = subprocess.run(
        ["just", "--dump", "--dump-format", "json"],
        cwd=Path(__file__).resolve().parents[4],
        capture_output=True,
        text=True,
        check=True,
    )
    document = cast("Mapping[str, object]", json.loads(completed.stdout))
    recipes = cast("Mapping[str, object]", document["recipes"])
    return frozenset(
        name
        for name in recipes
        if name.startswith("python-report-") and name != "python-report-cost"
    )


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
        lambda _request: ChildReading(1.0, "ms", (1.0,) * 9),
    )
    assert envelope.subject == "snapshot-delivery"
    assert envelope.authority == "non-authoritative"
    assert envelope.incomplete


def test_outside_budget_outcomes_do_not_fail_collection() -> None:
    document = canary(
        BudgetContract.load(),
        lambda _request: ChildReading(1.0, "ms", (1.0,) * 9),
    ).document()
    comparisons = cast("list[dict[str, object]]", document["comparisons"])
    comparisons[0]["outcome"] = "outside"

    def run(member: Member) -> tuple[int, str, str]:
        if member.required:
            return (0, json.dumps(document), "")
        return (9, "", "optional report unavailable")

    results, failed_required = collect(run)
    assert not failed_required
    assert results[0].envelope is not None
