"""Which milestones a keyed temporal write leaves unchanged, and how planning
keeps them, at the planner seam."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal

import pytest

from parallax.core import inheritance
from parallax.core.base import INFINITY
from parallax.core.unit_work import (
    RetainedObservation,
)
from parallax.core.write_plan.plan import (
    TRANSACTION_TIME_ENDS,
    OwnedEndpoint,
)
from parallax.core.write_plan.steps import (
    OPTIMISTIC_CONFLICT,
    ExactCount,
    PlannedTemporalGuard,
    TemporalGate,
)
from tests.unit.core.unit_work._ownership_support import OpenedRows
from tests.unit.core.unit_work._unchanged_milestones_support import (
    BALANCE,
    BALANCES,
    JAN,
    JUN,
    MAR,
    SPAN,
    SPANS,
    T0,
    balance_row,
    observed_write,
    planned,
    retained_state,
    span_row,
    step_kinds,
)

# --------------------------------------------------------------------------- #
# One observed milestone: the guard, and what stands in for it.               #
# --------------------------------------------------------------------------- #
_RESTATED = retained_state(BALANCES, BALANCE, balance_row("100.00"))


def test_an_update_restating_its_milestone_is_one_guard_on_the_observed_start() -> None:
    plan = planned(
        BALANCES, observed_write(BALANCES, "Balance", "update", _RESTATED, value="100.00")
    )
    (guard,) = plan.steps
    assert isinstance(guard, PlannedTemporalGuard)
    assert guard.target.end_values == TRANSACTION_TIME_ENDS
    assert isinstance(guard.concurrency, TemporalGate)
    assert guard.concurrency.observed_start == T0
    assert guard.affected_rows == ExactCount(expected=1, on_shortfall=OPTIMISTIC_CONFLICT)
    (unit,) = plan.units
    # The claim is spent, and the state it observed is named changed by nobody.
    assert (unit.claim, tuple(unit.changed)) == (_RESTATED, ())


def test_without_a_count_that_proves_it_an_unchanged_milestone_is_closed_and_chained() -> None:
    plan = planned(
        BALANCES,
        observed_write(BALANCES, "Balance", "update", _RESTATED, value="100.00"),
        counts_unchanged_rows=False,
    )
    assert step_kinds(plan.steps) == ["PlannedClose", "PlannedInsert"]
    (unit,) = plan.units
    # Closing it changes the observed state, which the unit names itself.
    assert (unit.claim, tuple(unit.changed)) == (_RESTATED, (_RESTATED.key,))


def test_under_locking_the_held_lock_proves_an_unchanged_milestone_without_a_statement() -> None:
    plan = planned(
        BALANCES,
        observed_write(BALANCES, "Balance", "update", _RESTATED, value="100.00"),
        concurrency="locking",
        counts_unchanged_rows=False,
    )
    assert len(plan.steps) == 0
    (unit,) = plan.units
    assert (unit.claim, tuple(unit.changed)) == (_RESTATED, ())


def test_a_milestone_the_attempt_opened_needs_no_statement_to_stay_unchanged() -> None:
    owned = OpenedRows(frozenset({OwnedEndpoint(BALANCE, (1,), TRANSACTION_TIME_ENDS)}))
    plan = planned(
        BALANCES,
        observed_write(BALANCES, "Balance", "update", _RESTATED, value="100.00"),
        ownership=owned,
    )
    assert len(plan.steps) == 0


def test_owning_another_row_lends_no_proof_to_an_unchanged_milestone_the_attempt_did_not_open() -> (
    None
):
    another = OpenedRows(frozenset({OwnedEndpoint(BALANCE, (2,), TRANSACTION_TIME_ENDS)}))
    plan = planned(
        BALANCES,
        observed_write(BALANCES, "Balance", "update", _RESTATED, value="100.00"),
        counts_unchanged_rows=False,
        ownership=another,
    )
    assert step_kinds(plan.steps) == ["PlannedClose", "PlannedInsert"]


def test_a_member_its_selection_does_not_declare_is_never_held() -> None:
    selection = inheritance.view(BALANCES).entity(BALANCE)
    assert selection is not None
    members = selection.member_selection
    row = balance_row("100.00")
    assert row.holds(members, {"value": Decimal("100.00")})
    assert not row.holds(members, {"value": Decimal("100.00"), "undeclared": 1})


@pytest.mark.parametrize(
    "members",
    [{"value": "150.00"}, {"value": "100.00", "acctNum": "B"}],
    ids=["changed", "one-of-two-members-changed"],
)
def test_an_update_changing_any_member_closes_and_chains(members: Mapping[str, object]) -> None:
    plan = planned(
        BALANCES, observed_write(BALANCES, "Balance", "update", _RESTATED, assigned=members)
    )
    assert step_kinds(plan.steps) == ["PlannedClose", "PlannedInsert"]


def test_a_terminate_is_never_unchanged() -> None:
    plan = planned(BALANCES, observed_write(BALANCES, "Balance", "terminate", _RESTATED))
    assert step_kinds(plan.steps) == ["PlannedClose"]


_NOTED = retained_state(SPANS, SPAN, span_row(JAN, INFINITY, 100, "a", {"note": "n1"}))
_UNNOTED = retained_state(SPANS, SPAN, span_row(JAN, INFINITY, 100, "a"))


@pytest.mark.parametrize(
    ("evidence", "members", "kept"),
    [
        (_NOTED, {"amount": 100}, True),
        (_NOTED, {"memo": {"note": "n1"}}, True),
        (_NOTED, {"memo": {"note": "n2"}}, False),
        (_NOTED, {"memo": None}, False),
        (_UNNOTED, {"memo": None}, True),
        (_UNNOTED, {"memo": {"note": None}}, False),
    ],
    ids=[
        "equal-scalar",
        "equal-whole-occurrence",
        "occurrence-with-another-member",
        "null-over-an-occurrence",
        "null-over-null",
        "an-occurrence-over-null",
    ],
)
def test_a_bitemporal_write_inside_its_rectangle_compares_every_assigned_member(
    evidence: RetainedObservation, members: Mapping[str, object], kept: bool
) -> None:
    plan = planned(
        SPANS,
        observed_write(
            SPANS,
            "SequenceSpan",
            "updateUntil",
            evidence,
            valid_from=MAR,
            until=JUN,
            assigned=members,
        ),
    )
    assert step_kinds(plan.steps) == (
        ["PlannedTemporalGuard"]
        if kept
        else ["PlannedClose", "PlannedInsert", "PlannedInsert", "PlannedInsert"]
    )
