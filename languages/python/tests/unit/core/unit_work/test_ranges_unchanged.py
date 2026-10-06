"""Which originals a range leaves unchanged (`m-temporal-write` *Unchanged
milestones*), judged one by one through range settlement and binding."""

from __future__ import annotations

import datetime as dt

from parallax.core import inheritance, temporal_read
from parallax.core.base import INFINITY
from parallax.core.unit_work import (
    TargetWrite,
)
from parallax.core.unit_work.instructions import prepare_wire_write
from parallax.core.unit_work.materialized import target_write
from parallax.core.write_plan import (
    ObjectKey,
    PlannedClose,
    PredecessorRow,
)
from parallax.core.write_plan.keys import TemporalStateKey
from parallax.core.write_plan.plan import (
    OPEN_BITEMPORAL_ENDS,
    OwnedEndpoint,
)
from parallax.core.write_plan.steps import INFINITY as OPEN_END
from parallax.core.write_plan.steps import (
    Finite,
    PlannedTemporalGuard,
)
from tests.unit.core.unit_work._ownership_support import OpenedRows
from tests.unit.core.unit_work._unchanged_milestones_support import (
    APR,
    AUG,
    DEC,
    JAN,
    JUN,
    MAR,
    MAY,
    OCT,
    SPAN,
    SPANS,
    T0,
    bound_range,
    observed_write,
    opened_windows,
    planned,
    retained_state,
    span_row,
    step_kinds,
)

# --------------------------------------------------------------------------- #
# A range: each original it reaches is judged on its own.                      #
# --------------------------------------------------------------------------- #
_FIRST = span_row(JAN, APR, 100, "a")
_MIDDLE = span_row(MAY, AUG, 180, "b")
_LAST = span_row(AUG, DEC, 100, "c")
_FROM_MARCH = retained_state(SPANS, SPAN, _FIRST)


def test_a_range_keeps_each_unchanged_original_and_transforms_only_the_changed_one() -> None:
    unit, bound = bound_range(
        SPANS,
        planned(
            SPANS,
            observed_write(
                SPANS,
                "SequenceSpan",
                "updateUntil",
                _FROM_MARCH,
                valid_from=MAR,
                until=OCT,
                amount=100,
            ),
        ),
        [_FIRST, _MIDDLE, _LAST],
    )
    assert step_kinds(bound.steps) == [
        "PlannedTemporalGuard",
        "PlannedClose",
        "PlannedTemporalGuard",
        "PlannedInsert",
    ]
    first, close, last, _ = bound.steps
    assert isinstance(first, PlannedTemporalGuard) and isinstance(last, PlannedTemporalGuard)
    assert isinstance(close, PlannedClose)
    assert [step.target.end_values[0].instant for step in (first, close, last)] == [  # type: ignore[union-attr]
        APR,
        AUG,
        DEC,
    ]
    assert opened_windows(bound.steps) == [(MAY, AUG, 100)]
    shape = temporal_read.view(SPANS).shape(SPAN)
    assert shape is not None
    middle = TemporalStateKey(
        ObjectKey(SPAN, (("id", 1),)), temporal_read.milestone_edge(shape, _MIDDLE, None)
    )
    # The deferred unit's effects are the bound range's, never its plan entry's.
    assert (tuple(bound.changed), tuple(unit.changed)) == ((middle,), ())


def test_a_range_assigning_every_original_a_new_value_transforms_them_all() -> None:
    _, bound = bound_range(
        SPANS,
        planned(
            SPANS,
            observed_write(
                SPANS,
                "SequenceSpan",
                "updateUntil",
                _FROM_MARCH,
                valid_from=MAR,
                until=OCT,
                amount=120,
            ),
        ),
        [_FIRST, _MIDDLE, _LAST],
    )
    assert step_kinds(bound.steps).count("PlannedClose") == 3
    assert "PlannedTemporalGuard" not in step_kinds(bound.steps)


def test_a_range_under_locking_states_nothing_for_its_unchanged_originals() -> None:
    _, bound = bound_range(
        SPANS,
        planned(
            SPANS,
            observed_write(
                SPANS,
                "SequenceSpan",
                "updateUntil",
                _FROM_MARCH,
                valid_from=MAR,
                until=OCT,
                amount=100,
            ),
            concurrency="locking",
        ),
        [_FIRST, _MIDDLE, _LAST],
    )
    assert step_kinds(bound.steps) == ["PlannedClose", "PlannedInsert"]


def test_a_net_equal_composition_leaves_its_original_unchanged() -> None:
    whole = retained_state(SPANS, SPAN, span_row(JAN, INFINITY, 100, "a"))
    plan = planned(
        SPANS,
        observed_write(
            SPANS, "SequenceSpan", "updateUntil", whole, valid_from=MAR, until=JUN, amount=150
        ),
        observed_write(
            SPANS, "SequenceSpan", "updateUntil", whole, valid_from=MAR, until=JUN, amount=100
        ),
    )
    assert step_kinds(plan.steps) == ["PlannedTemporalGuard"]


def test_an_original_part_of_which_the_composition_destroys_is_changed() -> None:
    first = span_row(JAN, JUN, 100, "a")
    second = span_row(JUN, INFINITY, 100, "b")
    plan = planned(
        SPANS,
        observed_write(
            SPANS,
            "SequenceSpan",
            "updateUntil",
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
    # [October, December) as well, so it is closed and reopened around the hole.
    assert step_kinds(plan.steps) == [
        "PlannedTemporalGuard",
        "PlannedClose",
        "PlannedInsert",
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
            "updateUntil",
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
    assert step_kinds(plan.steps) == ["PlannedTemporalGuard", "PlannedClose", "PlannedInsert"]


def test_a_window_a_caller_addressed_is_revised_however_equal_its_values() -> None:
    whole = retained_state(SPANS, SPAN, span_row(JAN, INFINITY, 100, "a"))
    target = target_write(
        prepare_wire_write(
            TargetWrite(
                "updateUntil",
                "SequenceSpan",
                {"id": 1, "amount": 100},
                if_tx_start=T0,
                valid_from=MAR,
                until=JUN,
            ),
            SPANS,
        ),
        inheritance.view(SPANS),
    )
    plan = planned(
        SPANS,
        observed_write(
            SPANS, "SequenceSpan", "updateUntil", whole, valid_from=MAR, until=JUN, amount=100
        ),
        target,
    )
    assert step_kinds(plan.steps) == [
        "PlannedClose",
        "PlannedInsert",
        "PlannedInsert",
        "PlannedInsert",
    ]


def test_an_owned_original_a_range_leaves_unchanged_is_neither_split_nor_revised() -> None:
    instant = dt.datetime(2024, 11, 1, tzinfo=dt.UTC)
    owned_row = PredecessorRow(
        members={**dict(span_row(JAN, JUN, 100, "a").members), "txStart": instant}
    )
    later = span_row(JUN, INFINITY, 100, "b")
    owned = OpenedRows(frozenset({OwnedEndpoint(SPAN, (1,), (Finite(instant=JUN), OPEN_END))}))
    _, bound = bound_range(
        SPANS,
        planned(
            SPANS,
            observed_write(
                SPANS,
                "SequenceSpan",
                "update",
                retained_state(SPANS, SPAN, owned_row),
                valid_from=MAR,
                amount=100,
            ),
            ownership=owned,
        ),
        [owned_row, later],
        ownership=owned,
    )
    # The row the attempt opened needs nothing; the one before it, a guard.
    assert step_kinds(bound.steps) == ["PlannedTemporalGuard"]
    (guard,) = bound.steps
    assert guard.target.end_values == OPEN_BITEMPORAL_ENDS  # type: ignore[union-attr]
