"""Range settlement and binding (`m-unit-work` *Write Plan and Planned Steps*).

A range binds through one binding whether planning already knew its coverage or
the executor read it; a deferred range is data the unit of work binds under the
attempt's ownership as it stands then, recapturing no instant and decorating
each bound step once.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from dataclasses import dataclass

import pytest

import parallax.snapshot.handle._planning as planning_composition
from parallax.core import inheritance, temporal_read
from parallax.core.base import INFINITY
from parallax.core.metamodel import EntityIdentity
from parallax.core.unit_work import (
    KeyedMutation,
    KeyedWrite,
    PlanningRequest,
    RetainedObservation,
    TargetWrite,
    TransactionInstant,
    WritePreconditionError,
    buffered_write,
)
from parallax.core.unit_work.instructions import PreparedTargetWrite, prepare_wire_write
from parallax.core.unit_work.materialized import BufferItem, target_write
from parallax.core.unit_work.strategy import ActorIdentity
from parallax.core.unit_work.write_planner import compose_writes
from parallax.core.write_plan import ObjectKey, PredecessorRow, TemporalObservation
from parallax.core.write_plan.keys import TemporalStateKey
from parallax.core.write_plan.plan import (
    NO_OWNERSHIP,
    BoundRange,
    ExecutionUnit,
    Openings,
    OwnedEndpoint,
    Ownership,
    RangeAcquisition,
    WritePlan,
)
from parallax.core.write_plan.steps import INFINITY as OPEN_END
from parallax.core.write_plan.steps import (
    Finite,
    PlannedClose,
    PlannedInsert,
    PlannedTemporalRevision,
    PlannedWrite,
)
from parallax.snapshot.handle import build_write_planner
from tests._support.clock_probes import CountingClock, instant_at
from tests._support.planner_probes import TEST_ACTOR_IDENTITY
from tests.unit._corpus_model_support import model
from tests.unit.core.unit_work._acquired_rows_support import acquired
from tests.unit.core.unit_work._ownership_support import OpenedRows

_SPANS = model("buffered-sequence-layout-twin-columns")
_SPAN = EntityIdentity("parallax.compatibility", "SequenceSpan")
_T0 = dt.datetime(2023, 12, 1, tzinfo=dt.UTC)
_PLANNED_AT = dt.datetime(2024, 11, 1, tzinfo=dt.UTC)
_JAN, _MAR, _JUN, _SEP = (dt.datetime(2024, month, 1, tzinfo=dt.UTC) for month in (1, 3, 6, 9))


def _span(start: dt.datetime, end: object, amount: int) -> PredecessorRow:
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


_HEAD = _span(_JAN, _JUN, 100)
_TAIL = _span(_JUN, INFINITY, 200)


def _retained(row: PredecessorRow) -> RetainedObservation:
    shape = temporal_read.view(_SPANS).shape(_SPAN)
    assert shape is not None
    key = ObjectKey(_SPAN, (("id", 1),))
    state = TemporalStateKey(key, temporal_read.milestone_edge(shape, row, None))
    return RetainedObservation(state, TemporalObservation(predecessor=row), None)


def _update(
    evidence: RetainedObservation, valid_from: dt.datetime, until: dt.datetime
) -> BufferItem:
    mutation: KeyedMutation = "updateUntil"
    prepared = prepare_wire_write(
        KeyedWrite(mutation, "SequenceSpan", ({"id": 1, "amount": 300},), valid_from, until),
        _SPANS,
    )
    return buffered_write(prepared, evidence)


def _target(valid_from: dt.datetime, until: dt.datetime) -> BufferItem:
    prepared = prepare_wire_write(
        TargetWrite(
            "updateUntil",
            "SequenceSpan",
            {"id": 1, "amount": 300},
            if_tx_start=_T0,
            valid_from=valid_from,
            until=until,
        ),
        _SPANS,
    )
    assert isinstance(prepared, PreparedTargetWrite)
    return target_write(prepared, inheritance.view(_SPANS))


def _plan(*writes: BufferItem, instant: TransactionInstant | None = None) -> WritePlan:
    return (
        build_write_planner(_SPANS)
        .finalize(
            PlanningRequest(
                actor_identity=TEST_ACTOR_IDENTITY,
                transaction_instant=instant or instant_at(_PLANNED_AT.isoformat()),
                concurrency="optimistic",
                buffered_writes=compose_writes(_SPANS, list(writes)),
            )
        )
        .plan
    )


def _deferred(plan: WritePlan) -> tuple[ExecutionUnit, RangeAcquisition]:
    (unit,) = plan.units
    assert unit.deferred is not None
    return unit, unit.deferred.acquisition


def _bind(
    unit: ExecutionUnit,
    rows: Sequence[PredecessorRow],
    *,
    ownership: Ownership = NO_OWNERSHIP,
    transaction_instant: TransactionInstant | None = None,
) -> BoundRange:
    deferred = unit.deferred
    assert deferred is not None
    return build_write_planner(_SPANS).bind_deferred(
        deferred,
        acquired(_SPANS, deferred.acquisition, rows),
        ownership=ownership,
        actor_identity=TEST_ACTOR_IDENTITY,
        transaction_instant=transaction_instant or instant_at(_PLANNED_AT.isoformat()),
    )


def _windows(steps: Sequence[PlannedWrite]) -> list[tuple[object, object, object]]:
    windows: list[tuple[object, object, object]] = []
    for step in steps:
        if isinstance(step, PlannedInsert):
            (entry,) = step.entries
            cells = {identity.name: value for identity, value in entry.row.attributes.items()}
            windows.append((cells["validStart"], cells["validEnd"], cells["amount"]))
    return windows


def test_a_range_binds_alike_whether_planning_knew_its_coverage_or_execution_read_it() -> None:
    head, tail = _retained(_HEAD), _retained(_TAIL)
    known = _plan(_update(head, _MAR, _JUN), _update(tail, _JUN, _SEP))
    (planned,) = known.units
    assert planned.deferred is None
    read, acquisition = _deferred(_plan(_update(head, _MAR, _SEP)))
    assert acquisition.valid_time_window == temporal_read.TimeInterval(_JUN, _SEP)

    bound = _bind(read, [_TAIL])

    assert bound.steps == tuple(known.steps)
    assert _windows(bound.steps) == [
        (_JAN, _MAR, 100),
        (_MAR, _JUN, 300),
        (_JUN, _SEP, 300),
        (_SEP, INFINITY, 200),
    ]
    assert tuple(bound.changed) == tuple(planned.changed) == (head.key, tail.key)
    assert [tuple(bound.opened.fresh), tuple(bound.opened.continued)] == [
        tuple(planned.opened.fresh),
        (),
    ]
    assert (bound.removed, bound.derived, bound.concludes) == ((), (), None)
    # A deferred unit's plan entry publishes nothing of its own beside its claim.
    assert (tuple(read.changed), read.opened, read.claim) == ((), Openings(), head)


def test_a_read_that_found_no_row_binds_the_range_to_what_it_observed() -> None:
    head = _retained(_HEAD)
    unit, _acquisition = _deferred(_plan(_update(head, _MAR, _SEP)))

    bound = _bind(unit, [])

    assert [type(step) for step in bound.steps] == [PlannedClose, PlannedInsert, PlannedInsert]
    assert _windows(bound.steps) == [(_JAN, _MAR, 100), (_MAR, _JUN, 300)]
    assert tuple(bound.changed) == (head.key,)


def test_a_caller_start_the_read_did_not_find_fails_as_its_precondition() -> None:
    unit, _acquisition = _deferred(_plan(_target(_MAR, _SEP)))
    with pytest.raises(WritePreconditionError):
        _bind(unit, [])


def test_binding_reads_the_ownership_the_attempt_holds_when_it_binds() -> None:
    unit, _acquisition = _deferred(_plan(_target(_JUN, _SEP)))
    endpoint = OwnedEndpoint(_SPAN, (1,), (OPEN_END, OPEN_END))

    stored = _bind(unit, [_TAIL])
    owned = _bind(unit, [_TAIL], ownership=OpenedRows(frozenset({endpoint})))

    assert [type(step) for step in stored.steps] == [PlannedClose, PlannedInsert, PlannedInsert]
    # The same plan entry, bound once the attempt owns the row it starts from,
    # revises that row in place rather than closing it into history.
    assert [type(step) for step in owned.steps] == [PlannedTemporalRevision, PlannedInsert]
    assert tuple(owned.opened.fresh) == (
        OwnedEndpoint(_SPAN, (1,), (Finite(instant=_SEP), OPEN_END)),
    )
    assert tuple(owned.changed) == tuple(stored.changed) == (_retained(_TAIL).key,)


def test_binding_stamps_the_instant_planning_resolved_and_reads_no_clock() -> None:
    head = _retained(_HEAD)
    planning = CountingClock([_PLANNED_AT])
    unit, _acquisition = _deferred(
        _plan(_update(head, _MAR, _SEP), instant=TransactionInstant(planning))
    )
    assert planning.calls == 1
    unread = CountingClock([])

    bound = _bind(unit, [_TAIL], transaction_instant=TransactionInstant(unread))

    assert unread.calls == 0
    stamped = {
        value
        for step in bound.steps
        if isinstance(step, PlannedInsert)
        for identity, value in step.entries[0].row.attributes.items()
        if identity.name == "txStart"
    }
    assert stamped == {_PLANNED_AT}


@dataclass(frozen=True, slots=True)
class _RecordingAudit:
    decorated: list[PlannedWrite]

    def decorate(
        self,
        step: PlannedWrite,
        *,
        actor_identity: ActorIdentity,
        transaction_instant: TransactionInstant,
    ) -> PlannedWrite:
        del actor_identity, transaction_instant
        self.decorated.append(step)
        return step


def test_every_bound_step_is_decorated_once_whether_the_range_bound_now_or_later(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audit = _RecordingAudit([])
    monkeypatch.setattr(planning_composition, "NO_AUDIT", audit)
    head, tail = _retained(_HEAD), _retained(_TAIL)

    known = _plan(_update(head, _MAR, _JUN), _update(tail, _JUN, _SEP))
    assert sorted(map(id, audit.decorated)) == sorted(map(id, known.steps))

    audit.decorated.clear()
    unit, _acquisition = _deferred(_plan(_update(head, _MAR, _SEP)))
    assert audit.decorated == []
    bound = _bind(unit, [_TAIL])
    assert sorted(map(id, audit.decorated)) == sorted(map(id, bound.steps))


def test_a_planner_binds_only_a_deferred_range_it_finalized() -> None:
    @dataclass(frozen=True, slots=True)
    class _Foreign:
        acquisition: RangeAcquisition

    _unit, acquisition = _deferred(_plan(_target(_MAR, _SEP)))
    with pytest.raises(TypeError, match="did not finalize"):
        build_write_planner(_SPANS).bind_deferred(
            _Foreign(acquisition),
            None,
            ownership=NO_OWNERSHIP,
            actor_identity=TEST_ACTOR_IDENTITY,
            transaction_instant=instant_at(_PLANNED_AT.isoformat()),
        )
