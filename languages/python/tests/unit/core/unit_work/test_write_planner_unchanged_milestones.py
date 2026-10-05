"""Which milestones a temporal write leaves unchanged, and how planning keeps
them, driven at the planner seam without a database: one guard under Optimistic
where the dialect's count proves it, no statement under Locking or for a row the
attempt opened, and the ordinary close and successors everywhere else."""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable, Mapping, Sequence
from decimal import Decimal

import pytest

from parallax.core import inheritance, temporal_read
from parallax.core.base import INFINITY
from parallax.core.metamodel import EntityIdentity, Metamodel
from parallax.core.unit_work import (
    KeyedMutation,
    KeyedWrite,
    ObjectKey,
    PlannedClose,
    PlannedInsert,
    PlanningRequest,
    PredecessorRow,
    RetainedObservation,
    TargetWrite,
    TemporalObservation,
    buffered_write,
)
from parallax.core.unit_work.instructions import prepare_wire_write
from parallax.core.unit_work.materialized import BufferItem, target_write
from parallax.core.unit_work.plan import (
    NO_OWNERSHIP,
    OPEN_BITEMPORAL_ENDS,
    TRANSACTION_TIME_ENDS,
    BoundRange,
    ExecutionUnit,
    OwnedEndpoint,
    Ownership,
    WritePlan,
)
from parallax.core.unit_work.planned import INFINITY as OPEN_END
from parallax.core.unit_work.planned import (
    OPTIMISTIC_CONFLICT,
    ExactCount,
    Finite,
    PlannedTemporalGuard,
    PlannedWrite,
    TemporalGate,
)
from parallax.core.unit_work.planner import TemporalStateKey
from parallax.core.unit_work.write_planner import compose_writes
from parallax.snapshot.handle import build_write_planner
from tests._support.clock_probes import instant_at
from tests._support.planner_probes import TEST_ACTOR_IDENTITY
from tests.unit._corpus_model_support import model
from tests.unit.core.unit_work._ownership_support import OpenedRows

_SPANS = model("buffered-sequence-layout-twin-columns")
_BALANCES = model("balance")
_SPAN = EntityIdentity("parallax.compatibility", "SequenceSpan")
_BALANCE = EntityIdentity("parallax.compatibility", "Balance")
_T0 = dt.datetime(2023, 12, 1, tzinfo=dt.UTC)
_JAN, _MAR, _APR, _MAY, _JUN, _AUG, _OCT, _DEC = (
    dt.datetime(2024, month, 1, tzinfo=dt.UTC) for month in (1, 3, 4, 5, 6, 8, 10, 12)
)


def _span(
    start: dt.datetime, end: object, amount: int, label: str, memo: object = None
) -> PredecessorRow:
    return PredecessorRow(
        members={
            "id": 1,
            "amount": amount,
            "label": label,
            "memo": memo,
            "validStart": start,
            "validEnd": end,
            "txStart": _T0,
            "txEnd": INFINITY,
        }
    )


def _balance(value: str) -> PredecessorRow:
    return PredecessorRow(
        members={
            "id": 1,
            "acctNum": "A",
            "value": Decimal(value),
            "txStart": _T0,
            "txEnd": INFINITY,
        }
    )


def _retained(meta: Metamodel, entity: EntityIdentity, row: PredecessorRow) -> RetainedObservation:
    shape = temporal_read.view(meta).shape(entity)
    assert shape is not None
    key = ObjectKey(entity, (("id", 1),))
    state = TemporalStateKey(key, temporal_read.milestone_edge(shape, row, None))
    return RetainedObservation(state, TemporalObservation(predecessor=row), None)


def _observed(
    meta: Metamodel,
    entity: str,
    mutation: KeyedMutation,
    evidence: RetainedObservation,
    *,
    valid_from: dt.datetime | None = None,
    until: dt.datetime | None = None,
    assigned: Mapping[str, object] | None = None,
    **members: object,
) -> BufferItem:
    prepared = prepare_wire_write(
        KeyedWrite(
            mutation, entity, ({"id": 1, **(assigned or {}), **members},), valid_from, until
        ),
        meta,
    )
    return buffered_write(prepared, evidence)


def _plan(
    meta: Metamodel,
    *writes: BufferItem,
    concurrency: str = "optimistic",
    counts_unchanged_rows: bool = True,
    ownership: Ownership = NO_OWNERSHIP,
) -> WritePlan:
    return (
        build_write_planner(meta)
        .finalize(
            PlanningRequest(
                actor_identity=TEST_ACTOR_IDENTITY,
                transaction_instant=instant_at("2024-11-01T00:00:00+00:00"),
                concurrency=concurrency,  # type: ignore[arg-type]
                buffered_writes=compose_writes(meta, list(writes)),
                ownership=ownership,
                counts_unchanged_rows=counts_unchanged_rows,
            )
        )
        .plan
    )


def _bound(plan: WritePlan, rows: Sequence[PredecessorRow]) -> tuple[ExecutionUnit, BoundRange]:
    (unit,) = plan.units
    assert unit.deferred is not None
    return unit, unit.deferred.bind(rows)


def _kinds(steps: Iterable[PlannedWrite]) -> list[str]:
    return [type(step).__name__ for step in steps]


def _openings(steps: Sequence[PlannedWrite]) -> list[tuple[object, object, object]]:
    windows: list[tuple[object, object, object]] = []
    for step in steps:
        if isinstance(step, PlannedInsert):
            (entry,) = step.entries
            cells = {identity.name: value for identity, value in entry.row.attributes.items()}
            windows.append((cells["validStart"], cells["validEnd"], cells["amount"]))
    return windows


# --------------------------------------------------------------------------- #
# One observed milestone: the guard, and what stands in for it.               #
# --------------------------------------------------------------------------- #
_RESTATED = _retained(_BALANCES, _BALANCE, _balance("100.00"))


def test_an_update_restating_its_milestone_is_one_guard_on_the_observed_start() -> None:
    plan = _plan(_BALANCES, _observed(_BALANCES, "Balance", "update", _RESTATED, value="100.00"))
    (guard,) = plan.steps
    assert isinstance(guard, PlannedTemporalGuard)
    assert guard.target.end_values == TRANSACTION_TIME_ENDS
    assert isinstance(guard.concurrency, TemporalGate)
    assert guard.concurrency.observed_start == _T0
    assert guard.affected_rows == ExactCount(expected=1, on_shortfall=OPTIMISTIC_CONFLICT)
    (unit,) = plan.units
    # The claim is spent, and the state it observed is named changed by nobody.
    assert (unit.claim, tuple(unit.changed), unit.changed_exactly) == (_RESTATED, (), True)


def test_without_a_count_that_proves_it_an_unchanged_milestone_is_closed_and_chained() -> None:
    plan = _plan(
        _BALANCES,
        _observed(_BALANCES, "Balance", "update", _RESTATED, value="100.00"),
        counts_unchanged_rows=False,
    )
    assert _kinds(plan.steps) == ["PlannedClose", "PlannedInsert"]
    (unit,) = plan.units
    assert not unit.changed_exactly


def test_under_locking_the_held_lock_proves_an_unchanged_milestone_without_a_statement() -> None:
    plan = _plan(
        _BALANCES,
        _observed(_BALANCES, "Balance", "update", _RESTATED, value="100.00"),
        concurrency="locking",
        counts_unchanged_rows=False,
    )
    assert len(plan.steps) == 0
    (unit,) = plan.units
    assert (unit.claim, tuple(unit.changed), unit.changed_exactly) == (_RESTATED, (), True)


def test_a_milestone_the_attempt_opened_needs_no_statement_to_stay_unchanged() -> None:
    owned = OpenedRows(frozenset({OwnedEndpoint(_BALANCE, (1,), TRANSACTION_TIME_ENDS)}))
    plan = _plan(
        _BALANCES,
        _observed(_BALANCES, "Balance", "update", _RESTATED, value="100.00"),
        ownership=owned,
    )
    assert len(plan.steps) == 0


def test_owning_another_row_lends_no_proof_to_an_unchanged_milestone_the_attempt_did_not_open() -> (
    None
):
    another = OpenedRows(frozenset({OwnedEndpoint(_BALANCE, (2,), TRANSACTION_TIME_ENDS)}))
    plan = _plan(
        _BALANCES,
        _observed(_BALANCES, "Balance", "update", _RESTATED, value="100.00"),
        counts_unchanged_rows=False,
        ownership=another,
    )
    assert _kinds(plan.steps) == ["PlannedClose", "PlannedInsert"]


def test_a_member_its_selection_does_not_declare_is_never_held() -> None:
    selection = inheritance.view(_BALANCES).entity(_BALANCE)
    assert selection is not None
    members = selection.member_selection
    row = _balance("100.00")
    assert row.holds(members, {"value": Decimal("100.00")})
    assert not row.holds(members, {"value": Decimal("100.00"), "undeclared": 1})


@pytest.mark.parametrize(
    "members",
    [{"value": "150.00"}, {"value": "100.00", "acctNum": "B"}],
    ids=["changed", "one-of-two-members-changed"],
)
def test_an_update_changing_any_member_closes_and_chains(members: Mapping[str, object]) -> None:
    plan = _plan(_BALANCES, _observed(_BALANCES, "Balance", "update", _RESTATED, assigned=members))
    assert _kinds(plan.steps) == ["PlannedClose", "PlannedInsert"]


def test_a_terminate_is_never_unchanged() -> None:
    plan = _plan(_BALANCES, _observed(_BALANCES, "Balance", "terminate", _RESTATED))
    assert _kinds(plan.steps) == ["PlannedClose"]


_NOTED = _retained(_SPANS, _SPAN, _span(_JAN, INFINITY, 100, "a", {"note": "n1"}))
_UNNOTED = _retained(_SPANS, _SPAN, _span(_JAN, INFINITY, 100, "a"))


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
    plan = _plan(
        _SPANS,
        _observed(
            _SPANS,
            "SequenceSpan",
            "updateUntil",
            evidence,
            valid_from=_MAR,
            until=_JUN,
            assigned=members,
        ),
    )
    assert _kinds(plan.steps) == (
        ["PlannedTemporalGuard"]
        if kept
        else ["PlannedClose", "PlannedInsert", "PlannedInsert", "PlannedInsert"]
    )


# --------------------------------------------------------------------------- #
# A range: each original it reaches is judged on its own.                      #
# --------------------------------------------------------------------------- #
_FIRST = _span(_JAN, _APR, 100, "a")
_MIDDLE = _span(_MAY, _AUG, 180, "b")
_LAST = _span(_AUG, _DEC, 100, "c")
_FROM_MARCH = _retained(_SPANS, _SPAN, _FIRST)


def test_a_range_keeps_each_unchanged_original_and_transforms_only_the_changed_one() -> None:
    unit, bound = _bound(
        _plan(
            _SPANS,
            _observed(
                _SPANS,
                "SequenceSpan",
                "updateUntil",
                _FROM_MARCH,
                valid_from=_MAR,
                until=_OCT,
                amount=100,
            ),
        ),
        [_FIRST, _MIDDLE, _LAST],
    )
    assert _kinds(bound.steps) == [
        "PlannedTemporalGuard",
        "PlannedClose",
        "PlannedTemporalGuard",
        "PlannedInsert",
    ]
    first, close, last, _ = bound.steps
    assert isinstance(first, PlannedTemporalGuard) and isinstance(last, PlannedTemporalGuard)
    assert isinstance(close, PlannedClose)
    assert [step.target.end_values[0].instant for step in (first, close, last)] == [  # type: ignore[union-attr]
        _APR,
        _AUG,
        _DEC,
    ]
    assert _openings(bound.steps) == [(_MAY, _AUG, 100)]
    shape = temporal_read.view(_SPANS).shape(_SPAN)
    assert shape is not None
    middle = TemporalStateKey(
        ObjectKey(_SPAN, (("id", 1),)), temporal_read.milestone_edge(shape, _MIDDLE, None)
    )
    assert (bound.changed, unit.changed_exactly) == ((middle,), True)


def test_a_range_assigning_every_original_a_new_value_transforms_them_all() -> None:
    _, bound = _bound(
        _plan(
            _SPANS,
            _observed(
                _SPANS,
                "SequenceSpan",
                "updateUntil",
                _FROM_MARCH,
                valid_from=_MAR,
                until=_OCT,
                amount=120,
            ),
        ),
        [_FIRST, _MIDDLE, _LAST],
    )
    assert _kinds(bound.steps).count("PlannedClose") == 3
    assert "PlannedTemporalGuard" not in _kinds(bound.steps)


def test_a_range_under_locking_states_nothing_for_its_unchanged_originals() -> None:
    _, bound = _bound(
        _plan(
            _SPANS,
            _observed(
                _SPANS,
                "SequenceSpan",
                "updateUntil",
                _FROM_MARCH,
                valid_from=_MAR,
                until=_OCT,
                amount=100,
            ),
            concurrency="locking",
        ),
        [_FIRST, _MIDDLE, _LAST],
    )
    assert _kinds(bound.steps) == ["PlannedClose", "PlannedInsert"]


def test_a_net_equal_composition_leaves_its_original_unchanged() -> None:
    whole = _retained(_SPANS, _SPAN, _span(_JAN, INFINITY, 100, "a"))
    plan = _plan(
        _SPANS,
        _observed(
            _SPANS, "SequenceSpan", "updateUntil", whole, valid_from=_MAR, until=_JUN, amount=150
        ),
        _observed(
            _SPANS, "SequenceSpan", "updateUntil", whole, valid_from=_MAR, until=_JUN, amount=100
        ),
    )
    assert _kinds(plan.steps) == ["PlannedTemporalGuard"]


def test_an_original_part_of_which_the_composition_destroys_is_changed() -> None:
    first = _span(_JAN, _JUN, 100, "a")
    second = _span(_JUN, INFINITY, 100, "b")
    plan = _plan(
        _SPANS,
        _observed(
            _SPANS,
            "SequenceSpan",
            "updateUntil",
            _retained(_SPANS, _SPAN, first),
            valid_from=_MAR,
            until=dt.datetime(2024, 9, 1, tzinfo=dt.UTC),
            amount=100,
        ),
        _observed(
            _SPANS,
            "SequenceSpan",
            "terminateUntil",
            _retained(_SPANS, _SPAN, second),
            valid_from=_OCT,
            until=_DEC,
        ),
    )
    # The first original only takes its own amount; the second loses
    # [October, December) as well, so it is closed and reopened around the hole.
    assert _kinds(plan.steps) == [
        "PlannedTemporalGuard",
        "PlannedClose",
        "PlannedInsert",
        "PlannedInsert",
        "PlannedInsert",
    ]


def test_a_window_a_caller_addressed_is_revised_however_equal_its_values() -> None:
    whole = _retained(_SPANS, _SPAN, _span(_JAN, INFINITY, 100, "a"))
    target = target_write(
        prepare_wire_write(
            TargetWrite(
                "updateUntil",
                "SequenceSpan",
                {"id": 1, "amount": 100},
                if_tx_start=_T0,
                valid_from=_MAR,
                until=_JUN,
            ),
            _SPANS,
        ),
        inheritance.view(_SPANS),
    )
    plan = _plan(
        _SPANS,
        _observed(
            _SPANS, "SequenceSpan", "updateUntil", whole, valid_from=_MAR, until=_JUN, amount=100
        ),
        target,
    )
    assert _kinds(plan.steps) == ["PlannedClose", "PlannedInsert", "PlannedInsert", "PlannedInsert"]


def test_an_owned_original_a_range_leaves_unchanged_is_neither_split_nor_revised() -> None:
    instant = dt.datetime(2024, 11, 1, tzinfo=dt.UTC)
    owned_row = PredecessorRow(
        members={**dict(_span(_JAN, _JUN, 100, "a").members), "txStart": instant}
    )
    later = _span(_JUN, INFINITY, 100, "b")
    owned = OpenedRows(frozenset({OwnedEndpoint(_SPAN, (1,), (Finite(instant=_JUN), OPEN_END))}))
    _, bound = _bound(
        _plan(
            _SPANS,
            _observed(
                _SPANS,
                "SequenceSpan",
                "update",
                _retained(_SPANS, _SPAN, owned_row),
                valid_from=_MAR,
                amount=100,
            ),
            ownership=owned,
        ),
        [owned_row, later],
    )
    # The row the attempt opened needs nothing; the one before it, a guard.
    assert _kinds(bound.steps) == ["PlannedTemporalGuard"]
    (guard,) = bound.steps
    assert guard.target.end_values == OPEN_BITEMPORAL_ENDS  # type: ignore[union-attr]
