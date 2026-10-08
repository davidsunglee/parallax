"""The per-predecessor rules one temporal unit expands each existing milestone by
(`m-temporal-write` *Temporal expansion*): reach, preservation, close cause and
gate, ownership disposal, successors, validation retirement, and the
new-lineage opening that shares their temporal stamping."""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable, Mapping
from decimal import Decimal

import pytest

from parallax.core import inheritance, temporal_read
from parallax.core.base import INFINITY
from parallax.core.metamodel import EntityIdentity, Metamodel
from parallax.core.temporal_read import TimeInterval
from parallax.core.temporal_write.coverage import NO_TRANSFORM, CoverageTransform
from parallax.core.temporal_write.expansion import (
    ExpansionRole,
    PredecessorExpander,
    PredecessorExpansion,
    TemporalFacts,
    opening,
)
from parallax.core.unit_work.strategy import NO_AUDIT, AuditDecoration
from parallax.core.write_plan import ObjectKey, PredecessorRow
from parallax.core.write_plan.keys import TemporalStateKey
from parallax.core.write_plan.plan import (
    NO_TEMPORAL_WRITE_OWNERSHIP,
    OPEN_BITEMPORAL_ENDS,
    TRANSACTION_TIME_ENDS,
    Derivation,
    OwnedEndpoint,
    TemporalWriteOwnership,
)
from parallax.core.write_plan.steps import (
    FAILED_PRECONDITION,
    NEW_LINEAGE,
    OPTIMISTIC_CONFLICT,
    SUPERSEDED,
    TERMINATED,
    UNGATED,
    CarriedFrom,
    ChangedFrom,
    Finite,
    PlannedClose,
    PlannedInsert,
    PlannedTemporalGuard,
    PlannedTemporalRemoval,
    PlannedTemporalRevision,
    PlannedWrite,
    TemporalGate,
)
from parallax.core.write_plan.steps import INFINITY as OPEN_END
from tests._support.clock_probes import inert_instant
from tests._support.planner_probes import TEST_ACTOR_IDENTITY
from tests.unit._corpus_model_support import model
from tests.unit.core.unit_work._ownership_support import OpenedRows

_SPANS = model("buffered-sequence-layout-twin-columns")
_BALANCES = model("balance")
_SPAN = EntityIdentity("parallax.compatibility", "SequenceSpan")
_BALANCE = EntityIdentity("parallax.compatibility", "Balance")
_T0 = dt.datetime(2023, 12, 1, tzinfo=dt.UTC)
_NOW = dt.datetime(2024, 11, 1, tzinfo=dt.UTC)
_JAN, _MAR, _JUN, _SEP, _OCT = (
    dt.datetime(2024, month, 1, tzinfo=dt.UTC) for month in (1, 3, 6, 9, 10)
)


def _facts(meta: Metamodel, entity: EntityIdentity) -> TemporalFacts:
    metadata = meta.entity(entity)
    view = inheritance.view(meta).entity(entity)
    shape = temporal_read.view(meta).shape(entity)
    assert metadata is not None and view is not None
    assert isinstance(shape, temporal_read.TransactionTimeOnly | temporal_read.Bitemporal)
    return TemporalFacts(entity=metadata, view=view, shape=shape, instant=_NOW)


_SPAN_FACTS = _facts(_SPANS, _SPAN)
_BALANCE_FACTS = _facts(_BALANCES, _BALANCE)


def _span(start: dt.datetime, end: object, amount: int = 100) -> PredecessorRow:
    return PredecessorRow(
        members={
            "id": 1,
            "amount": amount,
            "label": "a",
            "memo": None,
            "validStart": start,
            "validEnd": end,
            "txStart": _T0,
            "txEnd": INFINITY,
        }
    )


def _balance(value: str = "100.00") -> PredecessorRow:
    return PredecessorRow(
        members={
            "id": 1,
            "acctNum": "A",
            "value": Decimal(value),
            "txStart": _T0,
            "txEnd": INFINITY,
        }
    )


def _expansion(
    facts: TemporalFacts,
    transform: CoverageTransform,
    *,
    gated: bool = True,
    guards: bool = False,
    addressed: tuple[TimeInterval | None, ...] = (),
    derives: bool = False,
    ownership: TemporalWriteOwnership = NO_TEMPORAL_WRITE_OWNERSHIP,
) -> PredecessorExpander:
    return PredecessorExpander(
        facts,
        transform,
        key_attribute=facts.view.primary_key.identity,
        key_value=1,
        gated=gated,
        guards=guards,
        addressed=addressed,
        derives=derives,
        ownership=ownership,
        audit=AuditDecoration(NO_AUDIT, TEST_ACTOR_IDENTITY, inert_instant()),
    )


def _expand(
    expansion: PredecessorExpander,
    facts: TemporalFacts,
    predecessor: PredecessorRow,
    role: ExpansionRole = "coverage",
) -> PredecessorExpansion:
    return expansion.expand(
        predecessor,
        role=role,
        state=_state(facts, predecessor),
        coverage=temporal_read.valid_time_coverage(facts.shape, predecessor, None),
    )


def _state(facts: TemporalFacts, predecessor: PredecessorRow) -> TemporalStateKey:
    return TemporalStateKey(
        ObjectKey(facts.entity.identity, (("id", 1),)),
        temporal_read.milestone_edge(facts.shape, predecessor, None),
    )


def _assigning(
    window: TimeInterval | None, assigned: Mapping[str, object] | None
) -> CoverageTransform:
    return NO_TRANSFORM.followed_by(window, assigned, replaces=False)


def _kinds(steps: Iterable[PlannedWrite]) -> list[type[PlannedWrite]]:
    return [type(step) for step in steps]


def _cells(insert: PlannedWrite) -> dict[str, object]:
    assert isinstance(insert, PlannedInsert)
    (entry,) = insert.entries
    return {identity.name: value for identity, value in entry.row.attributes.items()}


def _windows(steps: Iterable[PlannedWrite]) -> list[tuple[object, object, object]]:
    return [
        (cells["validStart"], cells["validEnd"], cells["amount"])
        for cells in (_cells(step) for step in steps if isinstance(step, PlannedInsert))
    ]


def _endpoint(end: object) -> OwnedEndpoint:
    ends = OPEN_BITEMPORAL_ENDS if end is INFINITY else (Finite(instant=end), OPEN_END)
    return OwnedEndpoint(_SPAN, (1,), ends)


_STORED = _span(_JAN, INFINITY)


# --------------------------------------------------------------------------- #
# Reach, close cause, and successors over a predecessor the attempt found.    #
# --------------------------------------------------------------------------- #


def test_a_predecessor_the_transform_does_not_reach_is_left_alone() -> None:
    later = _span(_OCT, INFINITY)
    expanded = _expand(
        _expansion(_SPAN_FACTS, _assigning(TimeInterval(_MAR, _SEP), {"amount": 300})),
        _SPAN_FACTS,
        later,
    )
    assert expanded.steps == ()
    assert (tuple(expanded.changed), expanded.removed, expanded.derived) == ((), (), ())


def test_an_assignment_inside_a_stored_rectangle_closes_it_and_opens_three_successors() -> None:
    expanded = _expand(
        _expansion(_SPAN_FACTS, _assigning(TimeInterval(_MAR, _SEP), {"amount": 300})),
        _SPAN_FACTS,
        _STORED,
    )
    closing, *successors = expanded.steps
    assert isinstance(closing, PlannedClose)
    assert closing.cause is SUPERSEDED
    assert closing.concurrency == TemporalGate(
        start_attribute=_SPAN_FACTS.shape.transaction_time.start_attribute, observed_start=_T0
    )
    assert closing.affected_rows.on_shortfall == OPTIMISTIC_CONFLICT
    assert closing.target.end_values == OPEN_BITEMPORAL_ENDS
    assert _windows(successors) == [
        (_JAN, _MAR, 100),
        (_MAR, _SEP, 300),
        (_SEP, INFINITY, 100),
    ]
    origins = [type(step.entries[0].origin) for step in successors]  # type: ignore[union-attr]
    assert origins == [CarriedFrom, ChangedFrom, CarriedFrom]
    assert {(_cells(step)["txStart"], _cells(step)["txEnd"]) for step in successors} == {
        (_NOW, INFINITY)
    }
    assert _cells(successors[-1])["validEnd"] is INFINITY
    assert tuple(expanded.changed) == (_state(_SPAN_FACTS, _STORED),)
    assert tuple(expanded.opened.fresh) == (
        _endpoint(_MAR),
        _endpoint(_SEP),
        _endpoint(INFINITY),
    )
    assert (tuple(expanded.opened.continued), expanded.removed, expanded.concludes) == (
        (),
        (),
        None,
    )


def test_a_destruction_terminates_the_rectangle_and_carries_only_what_survives() -> None:
    bounded = _span(_JAN, _OCT)
    expanded = _expand(
        _expansion(_SPAN_FACTS, _assigning(TimeInterval(_MAR, INFINITY), None)),
        _SPAN_FACTS,
        bounded,
    )
    closing, head = expanded.steps
    assert isinstance(closing, PlannedClose)
    assert closing.cause is TERMINATED
    assert closing.target.end_values == (Finite(instant=_OCT), OPEN_END)
    assert _windows((head,)) == [(_JAN, _MAR, 100)]


@pytest.mark.parametrize(
    ("assigned", "cause", "successors"),
    [({"value": Decimal("9.00")}, SUPERSEDED, 1), (None, TERMINATED, 0)],
    ids=["update", "terminate"],
)
def test_a_transaction_time_only_milestone_closes_and_chains_without_valid_time(
    assigned: Mapping[str, object] | None, cause: object, successors: int
) -> None:
    predecessor = _balance()
    expanded = _expand(
        _expansion(_BALANCE_FACTS, _assigning(None, assigned)), _BALANCE_FACTS, predecessor
    )
    closing, *chained = expanded.steps
    assert isinstance(closing, PlannedClose)
    assert closing.cause is cause
    assert closing.target.end_values == TRANSACTION_TIME_ENDS
    assert len(chained) == successors
    for step in chained:
        cells = _cells(step)
        assert (cells["value"], cells["txStart"], cells["txEnd"]) == (
            Decimal("9.00"),
            _NOW,
            INFINITY,
        )
        assert "validStart" not in cells
    assert tuple(expanded.changed) == (_state(_BALANCE_FACTS, predecessor),)


@pytest.mark.parametrize(
    ("gated", "shortfall"),
    [(True, FAILED_PRECONDITION), (False, None)],
    ids=["gated", "ungated"],
)
def test_a_starting_predecessors_gated_close_fails_as_its_callers_precondition(
    gated: bool, shortfall: object
) -> None:
    expanded = _expand(
        _expansion(_SPAN_FACTS, _assigning(TimeInterval(_MAR, _SEP), {"amount": 300}), gated=gated),
        _SPAN_FACTS,
        _STORED,
        "starting",
    )
    closing = expanded.steps[0]
    assert isinstance(closing, PlannedClose)
    if gated:
        assert closing.affected_rows.on_shortfall == shortfall
    else:
        assert closing.concurrency is UNGATED
        assert closing.affected_rows.on_shortfall != FAILED_PRECONDITION


# --------------------------------------------------------------------------- #
# Disposal of a row the attempt opened.                                        #
# --------------------------------------------------------------------------- #


def test_an_owned_rectangle_is_revised_into_the_successor_keeping_its_address() -> None:
    owned = OpenedRows(frozenset({_endpoint(INFINITY)}))
    expanded = _expand(
        _expansion(
            _SPAN_FACTS, _assigning(TimeInterval(_MAR, INFINITY), {"amount": 300}), ownership=owned
        ),
        _SPAN_FACTS,
        _STORED,
    )
    revision, head = expanded.steps
    assert isinstance(revision, PlannedTemporalRevision)
    assigned = {identity.name: value for identity, value in revision.assignments.attributes.items()}
    assert assigned == {"amount": 300, "validStart": _MAR}
    assert _windows((head,)) == [(_JAN, _MAR, 100)]
    assert tuple(expanded.opened.fresh) == (_endpoint(_MAR),)
    assert tuple(expanded.changed) == (_state(_SPAN_FACTS, _STORED),)
    assert expanded.removed == ()


def test_an_owned_rectangle_no_successor_keeps_is_removed_and_its_survivors_opened() -> None:
    owned = OpenedRows(frozenset({_endpoint(INFINITY)}))
    expanded = _expand(
        _expansion(_SPAN_FACTS, _assigning(TimeInterval(_MAR, INFINITY), None), ownership=owned),
        _SPAN_FACTS,
        _STORED,
    )
    removal, head = expanded.steps
    assert isinstance(removal, PlannedTemporalRemoval)
    assert _windows((head,)) == [(_JAN, _MAR, 100)]
    assert tuple(expanded.removed) == (_endpoint(INFINITY),)
    assert tuple(expanded.changed) == (_state(_SPAN_FACTS, _STORED),)


# --------------------------------------------------------------------------- #
# Unchanged predecessors: full coverage and effective equality.               #
# --------------------------------------------------------------------------- #

_RESTATING = _assigning(TimeInterval(_MAR, _SEP), {"amount": 100})


@pytest.mark.parametrize(
    ("gated", "ownership", "kinds"),
    [
        (True, NO_TEMPORAL_WRITE_OWNERSHIP, [PlannedTemporalGuard]),
        (False, NO_TEMPORAL_WRITE_OWNERSHIP, []),
        (True, OpenedRows(frozenset({_endpoint(INFINITY)})), []),
    ],
    ids=["optimistic-guard", "locking", "owned"],
)
def test_an_equal_bounded_assignment_keeps_the_rectangle_across_carried_head_and_tail(
    gated: bool, ownership: TemporalWriteOwnership, kinds: list[type[PlannedWrite]]
) -> None:
    expanded = _expand(
        _expansion(_SPAN_FACTS, _RESTATING, gated=gated, guards=True, ownership=ownership),
        _SPAN_FACTS,
        _STORED,
    )
    assert _kinds(expanded.steps) == kinds
    assert (tuple(expanded.changed), tuple(expanded.opened.fresh), expanded.removed) == ((), (), ())


def test_an_unchanged_rectangle_is_closed_where_no_guard_can_prove_it() -> None:
    expanded = _expand(_expansion(_SPAN_FACTS, _RESTATING, guards=False), _SPAN_FACTS, _STORED)
    assert _kinds(expanded.steps) == [PlannedClose, PlannedInsert, PlannedInsert, PlannedInsert]


@pytest.mark.parametrize(
    ("addressed", "role"),
    [((TimeInterval(_JUN, _OCT),), "coverage"), ((), "starting")],
    ids=["addressed-window", "starting"],
)
def test_a_rectangle_a_caller_addressed_is_revised_however_equal_its_values(
    addressed: tuple[TimeInterval | None, ...], role: ExpansionRole
) -> None:
    expanded = _expand(
        _expansion(_SPAN_FACTS, _RESTATING, guards=True, addressed=addressed),
        _SPAN_FACTS,
        _STORED,
        role,
    )
    assert _kinds(expanded.steps) == [PlannedClose, PlannedInsert, PlannedInsert, PlannedInsert]


def test_a_rectangle_part_of_which_is_destroyed_is_changed_whatever_else_holds() -> None:
    transform = _RESTATING.followed_by(TimeInterval(_SEP, _OCT), None, replaces=False)
    expanded = _expand(_expansion(_SPAN_FACTS, transform, guards=True), _SPAN_FACTS, _STORED)
    assert expanded.steps[0].cause is SUPERSEDED  # type: ignore[union-attr]
    assert _windows(expanded.steps) == [(_JAN, _MAR, 100), (_MAR, _SEP, 100), (_OCT, INFINITY, 100)]


# --------------------------------------------------------------------------- #
# Validation: an earlier observation retired through the same disposal.        #
# --------------------------------------------------------------------------- #


def test_a_validated_predecessor_that_existed_before_the_attempt_is_closed_as_terminated() -> None:
    reached_nowhere = _assigning(TimeInterval(_OCT, INFINITY), {"amount": 300})
    expanded = _expand(
        _expansion(_SPAN_FACTS, reached_nowhere), _SPAN_FACTS, _span(_JAN, _JUN), "validation"
    )
    (closing,) = expanded.steps
    assert isinstance(closing, PlannedClose)
    assert closing.cause is TERMINATED
    assert closing.concurrency.observed_start == _T0  # type: ignore[union-attr]
    assert closing.affected_rows.on_shortfall == OPTIMISTIC_CONFLICT
    assert tuple(expanded.changed) == (_state(_SPAN_FACTS, _span(_JAN, _JUN)),)
    assert (tuple(expanded.opened.fresh), expanded.removed) == ((), ())


def test_a_validated_predecessor_the_attempt_opened_is_removed_rather_than_closed() -> None:
    validated = _span(_JAN, _JUN)
    owned = OpenedRows(frozenset({_endpoint(_JUN)}))
    expanded = _expand(
        _expansion(
            _SPAN_FACTS, _assigning(TimeInterval(_MAR, _SEP), {"amount": 300}), ownership=owned
        ),
        _SPAN_FACTS,
        validated,
        "validation",
    )
    (removal,) = expanded.steps
    assert isinstance(removal, PlannedTemporalRemoval)
    assert removal.target.end_values == (Finite(instant=_JUN), OPEN_END)
    assert tuple(expanded.removed) == (_endpoint(_JUN),)
    assert tuple(expanded.changed) == (_state(_SPAN_FACTS, validated),)
    assert (tuple(expanded.opened.fresh), tuple(expanded.opened.continued)) == ((), ())


# --------------------------------------------------------------------------- #
# What a later unit of the flush relies on.                                    #
# --------------------------------------------------------------------------- #


def test_a_deriving_expansion_records_each_successor_by_address_and_coverage() -> None:
    expansion = _expansion(
        _SPAN_FACTS, _assigning(TimeInterval(_MAR, _SEP), {"amount": 300}), derives=True
    )
    (derivation,) = _expand(expansion, _SPAN_FACTS, _STORED).derived
    assert derivation == Derivation(
        original=_state(_SPAN_FACTS, _STORED),
        valid_time_coverage=TimeInterval(_JAN, INFINITY),
        owned=None,
        rows=(
            (_endpoint(_MAR), TimeInterval(_JAN, _MAR)),
            (_endpoint(_SEP), TimeInterval(_MAR, _SEP)),
            (_endpoint(INFINITY), TimeInterval(_SEP, INFINITY)),
        ),
    )
    (validated,) = _expand(expansion, _SPAN_FACTS, _span(_JAN, _JUN), "validation").derived
    assert (validated.original, validated.owned, validated.rows) == (
        _state(_SPAN_FACTS, _span(_JAN, _JUN)),
        None,
        (),
    )
    assert (
        _expand(
            _expansion(_SPAN_FACTS, _assigning(TimeInterval(_MAR, _SEP), {"amount": 300})),
            _SPAN_FACTS,
            _STORED,
        ).derived
        == ()
    )


# --------------------------------------------------------------------------- #
# Shared values: one bindable predecessor, one resolution per mapping.         #
# --------------------------------------------------------------------------- #


def test_only_an_emitted_successor_prepares_the_bindable_predecessor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared: list[PredecessorRow] = []
    original = PredecessorRow.with_bindable_document

    def counting(row: PredecessorRow) -> PredecessorRow:
        bindable = original(row)
        prepared.append(bindable)
        return bindable

    monkeypatch.setattr(PredecessorRow, "with_bindable_document", counting)
    assigning = _expansion(_SPAN_FACTS, _assigning(TimeInterval(_MAR, _SEP), {"amount": 300}))
    successors = _expand(assigning, _SPAN_FACTS, _STORED).steps[1:]
    (bindable,) = prepared
    assert {id(step.entries[0].origin.predecessor) for step in successors} == {id(bindable)}  # type: ignore[union-attr]

    prepared.clear()
    _expand(assigning, _SPAN_FACTS, _span(_JAN, _JUN), "validation")
    _expand(
        _expansion(_SPAN_FACTS, _assigning(TimeInterval(_JAN, INFINITY), None)),
        _SPAN_FACTS,
        _STORED,
    )
    revised = _expand(
        _expansion(
            _SPAN_FACTS,
            _assigning(TimeInterval(_JAN, INFINITY), {"amount": 300}),
            ownership=OpenedRows(frozenset({_endpoint(INFINITY)})),
        ),
        _SPAN_FACTS,
        _STORED,
    )
    assert _kinds(revised.steps) == [PlannedTemporalRevision]
    assert prepared == []


def test_an_assignment_mapping_is_resolved_once_however_many_successors_share_it() -> None:
    transform = _assigning(TimeInterval(_MAR, _SEP), {"amount": 300})
    expansion = _expansion(_SPAN_FACTS, transform)
    (segment,) = transform.segments
    assert segment.assigned is not None
    resolved = expansion.assignments(segment.assigned)
    _expand(expansion, _SPAN_FACTS, _span(_JAN, _JUN))
    _expand(expansion, _SPAN_FACTS, _span(_JUN, INFINITY))
    assert expansion.assignments(segment.assigned) is resolved


# --------------------------------------------------------------------------- #
# New lineage.                                                                 #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("facts", "window", "expected"),
    [
        (_SPAN_FACTS, TimeInterval(_MAR, INFINITY), {"validStart": _MAR, "validEnd": INFINITY}),
        (_SPAN_FACTS, TimeInterval(_MAR, _SEP), {"validStart": _MAR, "validEnd": _SEP}),
        (_BALANCE_FACTS, None, {}),
    ],
    ids=["open", "bounded", "transaction-time-only"],
)
def test_an_opening_stamps_its_coverage_and_a_fresh_transaction_time_on_authored_state(
    facts: TemporalFacts, window: TimeInterval | None, expected: Mapping[str, object]
) -> None:
    key = facts.view.primary_key.identity
    entry = opening(facts, {key: 7}, {}, window)
    assert entry.origin is NEW_LINEAGE
    cells = {identity.name: value for identity, value in entry.row.attributes.items()}
    assert cells == {"id": 7, **expected, "txStart": _NOW, "txEnd": INFINITY}
