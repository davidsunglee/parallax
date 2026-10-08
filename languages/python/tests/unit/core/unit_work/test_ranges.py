"""Range settlement and binding (`m-unit-work` *Write Plan and Planned Steps*).

A range binds through one binding whether planning already knew its coverage or
the executor read it; a deferred range is data the unit of work binds under the
attempt's ownership as it stands then, recapturing no instant and decorating
each bound step once.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
from collections.abc import Sequence
from typing import Any

import pytest

import parallax.core.execution._planning as planning_composition
from parallax.core import inheritance, temporal_read
from parallax.core.base import INFINITY
from parallax.core.execution._planning import build_write_planner
from parallax.core.metamodel import EntityIdentity
from parallax.core.unit_work import (
    KeyedMutation,
    KeyedWrite,
    RetainedObservation,
    TargetWrite,
    TransactionInstant,
    WritePlanningRequest,
    WritePreconditionError,
    buffered_write,
)
from parallax.core.unit_work.acquisition import CoverageReadRequest
from parallax.core.unit_work.instructions import (
    PreparedKeyedWrite,
    PreparedTargetWrite,
    prepare_wire_write,
)
from parallax.core.unit_work.materialized import (
    BufferItem,
    ComposedTemporalWrite,
    ObservedKeyedWrite,
    TemporalContribution,
    target_write,
)
from parallax.core.unit_work.uow import bind_deferred_range
from parallax.core.unit_work.write_planner import compose_writes
from parallax.core.write_plan import (
    ObjectKey,
    PredecessorRow,
    TemporalObservation,
    VersionObservation,
    WritePlanningError,
)
from parallax.core.write_plan.keys import TemporalStateKey
from parallax.core.write_plan.plan import (
    NO_TEMPORAL_WRITE_OWNERSHIP,
    BoundRange,
    CombinedSourceAuthority,
    DeferredRange,
    ExecutionUnit,
    Openings,
    OwnedEndpoint,
    TemporalWriteOwnership,
    WritePlan,
)
from parallax.core.write_plan.steps import INFINITY as OPEN_END
from parallax.core.write_plan.steps import (
    TERMINATED,
    Finite,
    PlannedClose,
    PlannedInsert,
    PlannedTemporalRemoval,
    PlannedTemporalRevision,
    PlannedWrite,
)
from tests._support.clock_probes import CountingClock, instant_at
from tests._support.planner_probes import TEST_ACTOR_IDENTITY
from tests.unit._corpus_model_support import model
from tests.unit.core.unit_work._acquired_rows_support import (
    HeldRows,
    bind_held,
    coverage_read,
)
from tests.unit.core.unit_work._audit_support import RecordingAudit
from tests.unit.core.unit_work._ownership_support import OpenedRows

_SPANS = model("buffered-sequence-layout-twin-columns")
_SPAN = EntityIdentity("parallax.compatibility", "SequenceSpan")
_T0 = dt.datetime(2023, 12, 1, tzinfo=dt.UTC)
_T1 = dt.datetime(2024, 2, 1, tzinfo=dt.UTC)
_PLANNED_AT = dt.datetime(2024, 11, 1, tzinfo=dt.UTC)
_JAN, _MAR, _APR, _MAY, _JUN, _JUL, _SEP = (
    dt.datetime(2024, month, 1, tzinfo=dt.UTC) for month in (1, 3, 4, 5, 6, 7, 9)
)


def _span(
    start: dt.datetime, end: object, amount: int, tx_start: dt.datetime = _T0
) -> PredecessorRow:
    return PredecessorRow(
        members={
            "id": 1,
            "amount": amount,
            "label": "a",
            "memo": None,
            "validStart": start,
            "validEnd": end,
            "txStart": tx_start,
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
    mutation: KeyedMutation = "amendUntil"
    prepared = prepare_wire_write(
        KeyedWrite(mutation, "SequenceSpan", ({"id": 1, "amount": 300},), valid_from, until),
        _SPANS,
    )
    return buffered_write(prepared, evidence)


def _target(valid_from: dt.datetime, until: dt.datetime) -> BufferItem:
    prepared = prepare_wire_write(
        TargetWrite(
            "amendUntil",
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


def _plan(
    *writes: BufferItem,
    instant: TransactionInstant | None = None,
    ownership: TemporalWriteOwnership = NO_TEMPORAL_WRITE_OWNERSHIP,
) -> WritePlan:
    return build_write_planner(_SPANS).finalize(
        WritePlanningRequest(
            actor_identity=TEST_ACTOR_IDENTITY,
            transaction_instant=instant or instant_at(_PLANNED_AT.isoformat()),
            concurrency="optimistic",
            buffered_writes=compose_writes(_SPANS, list(writes)),
            ownership=ownership,
        )
    )


def _deferred(plan: WritePlan) -> tuple[ExecutionUnit, CoverageReadRequest]:
    """``plan``'s one deferred unit, and the coverage read the unit of work asks
    for when it binds that unit's range."""
    (unit,) = plan.units
    assert unit.deferred is not None
    return unit, coverage_read(
        _SPANS, unit, transaction_instant=instant_at(_PLANNED_AT.isoformat())
    )


def _bind(
    unit: ExecutionUnit,
    rows: Sequence[PredecessorRow],
    *,
    ownership: TemporalWriteOwnership = NO_TEMPORAL_WRITE_OWNERSHIP,
    transaction_instant: TransactionInstant | None = None,
) -> BoundRange:
    return bind_held(
        _SPANS,
        unit,
        rows,
        ownership=ownership,
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
    assert acquisition.valid_time_windows == (temporal_read.TimeInterval(_JUN, _SEP),)

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


def test_every_produced_row_and_close_is_audited_once_whether_the_range_bound_now_or_later(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Audit belongs to settlement, so a range finalizes each row it produces and
    # stamps each close it emits when it binds, at planning or at execution
    # alike, and the steps it answers are exactly what the hooks returned.
    audit = RecordingAudit()
    monkeypatch.setattr(planning_composition, "NO_AUDIT", audit)
    head, tail = _retained(_HEAD), _retained(_TAIL)

    known = _plan(_update(head, _MAR, _JUN), _update(tail, _JUN, _SEP))
    assert sorted(map(id, audit.closes)) == sorted(
        id(step) for step in known.steps if isinstance(step, PlannedClose)
    )
    assert sorted(map(id, audit.rows)) == sorted(
        id(step.entries[0]) for step in known.steps if isinstance(step, PlannedInsert)
    )

    audit.rows.clear()
    audit.closes.clear()
    unit, _acquisition = _deferred(_plan(_update(head, _MAR, _SEP)))
    assert (audit.rows, audit.closes) == ([], [])
    bound = _bind(unit, [_TAIL])
    assert sorted(map(id, audit.closes)) == sorted(
        id(step) for step in bound.steps if isinstance(step, PlannedClose)
    )
    assert sorted(map(id, audit.rows)) == sorted(
        id(step.entries[0]) for step in bound.steps if isinstance(step, PlannedInsert)
    )


def test_a_deferred_range_its_planner_did_not_finalize_is_refused_before_any_read() -> None:
    class _Foreign(DeferredRange):
        __slots__ = ()

    held = HeldRows(_SPANS)
    with pytest.raises(TypeError, match="did not finalize"):
        bind_deferred_range(
            _Foreign(),
            acquire_rows=held,
            planner=build_write_planner(_SPANS),
            ownership=NO_TEMPORAL_WRITE_OWNERSHIP,
            actor_identity=TEST_ACTOR_IDENTITY,
            transaction_instant=instant_at(_PLANNED_AT.isoformat()),
        )
    assert held.requests == []


@pytest.mark.parametrize(
    ("ownership", "retired"),
    [
        (NO_TEMPORAL_WRITE_OWNERSHIP, PlannedClose),
        (
            OpenedRows(frozenset({OwnedEndpoint(_SPAN, (1,), (Finite(instant=_JUN), OPEN_END))})),
            PlannedTemporalRemoval,
        ),
    ],
    ids=["stored", "opened-by-the-attempt"],
)
def test_an_overlapped_observation_is_retired_by_whoever_owns_its_row(
    ownership: TemporalWriteOwnership, retired: type[PlannedWrite]
) -> None:
    earlier = _retained(_span(_JAN, _JUN, 100))
    later = _retained(_span(_MAR, INFINITY, 200, tx_start=_T1))
    plan = _plan(_update(earlier, _MAR, _APR), _update(later, _MAY, _JUL), ownership=ownership)
    (unit,) = plan.units
    assert unit.deferred is None
    validation, closing, *successors = plan.steps
    # The earlier observation is only validated: it retires its own row ahead
    # of the later one's close, and every successor derives from the later one.
    assert type(validation) is retired
    assert validation.target.end_values == (Finite(instant=_JUN), OPEN_END)  # type: ignore[union-attr]
    if isinstance(validation, PlannedClose):
        assert validation.cause is TERMINATED
    assert isinstance(closing, PlannedClose)
    assert closing.concurrency.observed_start == _T1  # type: ignore[union-attr]
    assert _windows(successors) == [
        (_MAR, _APR, 300),
        (_APR, _MAY, 200),
        (_MAY, _JUL, 300),
        (_JUL, INFINITY, 200),
    ]
    assert tuple(unit.changed) == (earlier.key, later.key)
    assert tuple(unit.removed) == (
        ()
        if retired is PlannedClose
        else (OwnedEndpoint(_SPAN, (1,), (Finite(instant=_JUN), OPEN_END)),)
    )


# --------------------------------------------------------------------------- #
# A lone keyed write enters range settlement as the carrier it was buffered   #
# in: no composition of one write is built for it.                             #
# --------------------------------------------------------------------------- #
class _Compositions:
    """Counts the compositions and contributions built from now on."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.built = 0
        for composing in (ComposedTemporalWrite, TemporalContribution):
            original = composing.__init__

            def counting(
                composed: object, *args: object, _original: Any = original, **kwargs: object
            ) -> None:
                self.built += 1
                _original(composed, *args, **kwargs)

            monkeypatch.setattr(composing, "__init__", counting)


def test_a_lone_observed_write_inside_its_predecessor_binds_at_once_from_its_own_carrier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    head = _retained(_HEAD)
    built = _Compositions(monkeypatch)
    (buffered,) = compose_writes(_SPANS, [_update(head, _MAR, _APR)])
    assert isinstance(buffered, ObservedKeyedWrite)
    plan = _plan(buffered)
    assert built.built == 0
    (unit,) = plan.units
    assert unit.deferred is None
    assert unit.claim is head
    assert [type(step) for step in plan.steps] == [
        PlannedClose,
        PlannedInsert,
        PlannedInsert,
        PlannedInsert,
    ]
    assert _windows(tuple(plan.steps)) == [
        (_JAN, _MAR, 100),
        (_MAR, _APR, 300),
        (_APR, _JUN, 100),
    ]
    assert tuple(unit.changed) == (head.key,)


def test_a_lone_write_reaching_past_what_it_observed_reads_only_the_rest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    head = _retained(_HEAD)
    built = _Compositions(monkeypatch)
    unit, acquisition = _deferred(_plan(_update(head, _MAR, _SEP)))
    assert built.built == 0
    assert acquisition.valid_time_windows == (temporal_read.TimeInterval(_JUN, _SEP),)
    assert unit.claim is head


@pytest.mark.parametrize("observation", [None, VersionObservation(observed_version=1)])
def test_a_temporal_write_holding_no_temporal_observation_is_refused_before_the_instant(
    observation: VersionObservation | None,
) -> None:
    prepared = prepare_wire_write(
        KeyedWrite("amendUntil", "SequenceSpan", ({"id": 1, "amount": 300},), _MAR, _APR),
        _SPANS,
    )
    assert isinstance(prepared, PreparedKeyedWrite)
    item: BufferItem = (
        prepared if observation is None else ObservedKeyedWrite(prepared, observation)
    )
    clock = CountingClock([_PLANNED_AT])
    with pytest.raises(WritePlanningError, match="closes the current milestone"):
        _plan(item, instant=TransactionInstant(clock))
    assert clock.calls == 0


def test_a_lone_observed_write_spends_every_twinned_observation_of_its_state() -> None:
    claim, twin = _retained(_HEAD), _retained(_HEAD)
    (buffered,) = compose_writes(_SPANS, [_update(claim, _MAR, _APR)])
    assert isinstance(buffered, ObservedKeyedWrite)
    (unit,) = _plan(dataclasses.replace(buffered, twins=(twin, claim))).units
    assert unit.claim == CombinedSourceAuthority((claim, twin))
