"""Which milestones a temporal write leaves unchanged (`m-temporal-write`
*Unchanged milestones*): a lone observed write's one original, and each
original a composition reaches, judged one by one, and how planning keeps
them."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from parallax.core import inheritance
from parallax.core._execution._unit_work.instructions import prepare_wire_write
from parallax.core._execution._unit_work.write_items import target_write
from parallax.core.base import INFINITY
from parallax.core.unit_work import (
    TargetWriteInstruction,
)
from parallax.core.write_plan.observe import AssignedComparison
from parallax.core.write_plan.plan import (
    TRANSACTION_TIME_ENDS,
    TemporalRowCoordinates,
)
from parallax.core.write_plan.steps import (
    FAILED_PRECONDITION,
    OPTIMISTIC_CONFLICT,
    ExactCount,
    PlannedTemporalGuard,
    PlannedTemporalRevision,
    TemporalGate,
)
from tests._support.planner_probes import plan_steps, settled_writes
from tests._support.write_preparation import write_preparation_of
from tests.unit.core._execution._unit_work._ownership_support import OpenedRows
from tests.unit.core._execution._unit_work._unchanged_milestones_support import (
    BALANCE,
    BALANCES,
    DEC,
    JAN,
    JUN,
    MAR,
    NOW,
    OCT,
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
# A range: each original it reaches is judged on its own.                      #
# --------------------------------------------------------------------------- #


def test_an_original_part_of_which_the_composition_destroys_is_changed() -> None:
    first = span_row(JAN, JUN, 100, "a")
    second = span_row(JUN, INFINITY, 100, "b")
    plan = planned(
        SPANS,
        observed_write(
            SPANS,
            "SequenceSpan",
            "amendUntil",
            retained_state(SPANS, SPAN, first),
            valid_from=MAR,
            until=dt.datetime(2024, 9, 1, tzinfo=dt.UTC),
            amount=100,
        ),
        observed_write(
            SPANS,
            "SequenceSpan",
            "terminateUntil",
            retained_state(SPANS, SPAN, second),
            valid_from=OCT,
            until=DEC,
        ),
    )
    # The first original only takes its own amount; the second loses
    # [October, December) as well, so it is closed and reopened around the hole,
    # its equal [June, September) and [September, October) as one row.
    assert step_kinds(plan_steps(plan)) == [
        "PlannedTemporalGuard",
        "PlannedClose",
        "PlannedInsert",
        "PlannedInsert",
    ]


def test_an_original_whose_start_the_composition_destroys_is_changed() -> None:
    first = span_row(JAN, JUN, 100, "a")
    second = span_row(JUN, INFINITY, 100, "b")
    plan = planned(
        SPANS,
        observed_write(
            SPANS,
            "SequenceSpan",
            "amendUntil",
            retained_state(SPANS, SPAN, first),
            valid_from=MAR,
            until=JUN,
            amount=100,
        ),
        observed_write(
            SPANS,
            "SequenceSpan",
            "terminateUntil",
            retained_state(SPANS, SPAN, second),
            valid_from=JUN,
            until=OCT,
        ),
    )
    # What survives of the second original no longer begins where it did.
    assert step_kinds(plan_steps(plan)) == ["PlannedTemporalGuard", "PlannedClose", "PlannedInsert"]


def test_a_window_a_target_keeps_a_milestone_it_leaves_unchanged() -> None:
    whole = retained_state(SPANS, SPAN, span_row(JAN, INFINITY, 100, "a"))
    target = target_write(
        prepare_wire_write(
            TargetWriteInstruction(
                "amendUntil",
                "SequenceSpan",
                {"id": 1, "amount": 100},
                if_tx_start=T0,
                valid_from=MAR,
                until=JUN,
            ),
            write_preparation_of(SPANS),
        ),
        inheritance.inheritance_facet_of(SPANS),
    )
    plan = planned(
        SPANS,
        observed_write(
            SPANS, "SequenceSpan", "amendUntil", whole, valid_from=MAR, until=JUN, amount=100
        ),
        target,
    )
    # The caller's start is the rectangle kept, so its guard binds the stated
    # start and a shortfall against it is that caller's failed precondition.
    (guard,) = plan_steps(plan)
    assert isinstance(guard, PlannedTemporalGuard)
    assert guard.concurrency.observed_start == T0
    assert guard.affected_rows == ExactCount(expected=1, on_shortfall=FAILED_PRECONDITION)


# --------------------------------------------------------------------------- #
# One observed milestone: the guard, and what stands in for it.               #
# --------------------------------------------------------------------------- #
_RESTATED = retained_state(BALANCES, BALANCE, balance_row("100.00"))


def test_without_a_count_that_proves_it_an_unchanged_milestone_is_closed_and_chained() -> None:
    plan = planned(
        BALANCES,
        observed_write(BALANCES, "Balance", "amend", _RESTATED, value="100.00"),
        counts_unchanged_rows=False,
    )
    assert step_kinds(plan_steps(plan)) == ["PlannedClose", "PlannedInsert"]
    (write,) = settled_writes(plan)
    # Closing it changes the observed state, which the write names itself.
    assert tuple(write.changed) == (_RESTATED.key,)


def test_under_locking_the_held_lock_proves_an_unchanged_milestone_without_a_statement() -> None:
    plan = planned(
        BALANCES,
        observed_write(BALANCES, "Balance", "amend", _RESTATED, value="100.00"),
        concurrency="locking",
        counts_unchanged_rows=False,
    )
    assert len(plan_steps(plan)) == 0
    (write,) = settled_writes(plan)
    assert tuple(write.changed) == ()


_REOPENED = OpenedRows(frozenset({TemporalRowCoordinates(BALANCE, (1,), TRANSACTION_TIME_ENDS)}))


def test_a_milestone_the_attempt_opened_needs_no_statement_to_stay_unchanged() -> None:
    opened = retained_state(BALANCES, BALANCE, balance_row("100.00", NOW))
    plan = planned(
        BALANCES,
        observed_write(BALANCES, "Balance", "amend", opened, value="100.00"),
        ownership=_REOPENED,
    )
    assert len(plan_steps(plan)) == 0


def test_an_earlier_milestone_at_an_address_the_attempt_reopened_is_not_proven_by_ownership() -> (
    None
):
    plan = planned(
        BALANCES,
        observed_write(BALANCES, "Balance", "amend", _RESTATED, value="100.00"),
        ownership=_REOPENED,
    )
    (revision,) = plan_steps(plan)
    assert isinstance(revision, PlannedTemporalRevision)
    assert isinstance(revision.concurrency, TemporalGate)
    assert revision.concurrency.observed_start == T0
    assert revision.affected_rows == ExactCount(expected=1, on_shortfall=OPTIMISTIC_CONFLICT)


def test_a_stale_start_at_an_address_the_attempt_reopened_is_its_callers_precondition() -> None:
    target = target_write(
        prepare_wire_write(
            TargetWriteInstruction(
                "amend", "Balance", {"id": 1, "value": "100.00"}, if_tx_start=T0
            ),
            write_preparation_of(BALANCES),
        ),
        inheritance.inheritance_facet_of(BALANCES),
    )
    plan = planned(
        BALANCES,
        observed_write(BALANCES, "Balance", "amend", _RESTATED, value="100.00"),
        target,
        ownership=_REOPENED,
    )
    (revision,) = plan_steps(plan)
    assert isinstance(revision, PlannedTemporalRevision)
    assert isinstance(revision.concurrency, TemporalGate)
    assert revision.concurrency.observed_start == T0
    assert revision.affected_rows == ExactCount(expected=1, on_shortfall=FAILED_PRECONDITION)


def test_owning_another_row_lends_no_proof_to_an_unchanged_milestone_the_attempt_did_not_open() -> (
    None
):
    another = OpenedRows(frozenset({TemporalRowCoordinates(BALANCE, (2,), TRANSACTION_TIME_ENDS)}))
    plan = planned(
        BALANCES,
        observed_write(BALANCES, "Balance", "amend", _RESTATED, value="100.00"),
        counts_unchanged_rows=False,
        ownership=another,
    )
    assert step_kinds(plan_steps(plan)) == ["PlannedClose", "PlannedInsert"]


def test_a_member_its_selection_does_not_declare_is_never_held() -> None:
    selection = inheritance.inheritance_facet_of(BALANCES).entity(BALANCE)
    assert selection is not None
    members = selection.member_selection
    row = balance_row("100.00")
    assert row.holds(AssignedComparison(members, {"value": Decimal("100.00")}))
    assert not row.holds(AssignedComparison(members, {"value": Decimal("100.00"), "undeclared": 1}))
