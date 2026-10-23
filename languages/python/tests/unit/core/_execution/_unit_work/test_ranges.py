"""Range settlement and binding (`m-unit-work` *Write Plan and Planned Steps*).

A range binds through one binding whether planning already knew its coverage or
the executor read it; a deferred range is data the unit of work binds under the
attempt's ownership as it stands then, recapturing no instant and decorating
each bound step once.
"""

from __future__ import annotations

import contextlib
import datetime as dt
from collections.abc import Iterable, Sequence
from types import FrameType
from typing import Any

import pytest

import parallax.core._execution._planning as planning_composition
from parallax.core import inheritance, temporal_read
from parallax.core._execution._planning import build_write_planner
from parallax.core._execution._unit_work import ranges as ranges_module
from parallax.core._execution._unit_work.acquisition import (
    AcquireRows,
    CoverageReadRequest,
    RowConsumer,
    RowRequest,
)
from parallax.core._execution._unit_work.instructions import (
    PreparedKeyedInstruction,
    PreparedTargetInstruction,
    prepare_wire_write,
)
from parallax.core._execution._unit_work.ranges import RangeBindings
from parallax.core._execution._unit_work.write_items import (
    AdmittedWrite,
    ComposedTemporalWrite,
    StateObservedWrite,
    TemporalContribution,
    target_write,
)
from parallax.core.base import INFINITY
from parallax.core.metamodel import EntityIdentity
from parallax.core.unit_work import (
    KeyedMutation,
    KeyedWriteInstruction,
    RetainedObservation,
    TargetWriteInstruction,
    TransactionInstant,
    WritePlanningRequest,
    WritePreconditionError,
    admitted_write,
)
from parallax.core.write_plan import (
    ObjectKey,
    PredecessorRow,
    TemporalObservation,
    VersionObservation,
    WritePlanningError,
)
from parallax.core.write_plan.keys import TemporalObjectStateKey, VersionedObjectStateKey
from parallax.core.write_plan.plan import (
    NO_TEMPORAL_WRITE_OWNERSHIP,
    BoundRange,
    Openings,
    SettledWrite,
    TemporalRowCoordinates,
    TemporalWriteOwnership,
    WriteGroup,
    WritePlan,
)
from parallax.core.write_plan.steps import INFINITY as OPEN_END
from parallax.core.write_plan.steps import (
    TERMINATED,
    Finite,
    PlannedClose,
    PlannedInsert,
    PlannedStep,
    PlannedTemporalRemoval,
    PlannedTemporalRevision,
    WriteRow,
)
from tests._support.clock_probes import CountingClock, instant_at
from tests._support.planner_probes import (
    TEST_ACTOR_IDENTITY,
    admitted_writes,
    plan_steps,
    settled_writes,
)
from tests.unit._corpus_model_support import model
from tests.unit.core._execution._reach_support import frames, reaches
from tests.unit.core._execution._unit_work._acquired_rows_support import (
    HeldRows,
    alone,
    bind_held,
    coverage_read,
    range_bindings,
)
from tests.unit.core._execution._unit_work._audit_support import RecordingAudit
from tests.unit.core._execution._unit_work._ownership_support import OpenedRows

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
    state = TemporalObjectStateKey(key, temporal_read.milestone_edge(shape, row, None))
    return RetainedObservation(state, TemporalObservation(predecessor=row), None)


def _update(
    evidence: RetainedObservation, valid_from: dt.datetime, until: dt.datetime
) -> AdmittedWrite:
    mutation: KeyedMutation = "amendUntil"
    prepared = prepare_wire_write(
        KeyedWriteInstruction(
            mutation, "SequenceSpan", ({"id": 1, "amount": 300},), valid_from, until
        ),
        _SPANS,
    )
    return admitted_write(prepared, evidence)


def _target(valid_from: dt.datetime, until: dt.datetime) -> AdmittedWrite:
    prepared = prepare_wire_write(
        TargetWriteInstruction(
            "amendUntil",
            "SequenceSpan",
            {"id": 1, "amount": 300},
            if_tx_start=_T0,
            valid_from=valid_from,
            until=until,
        ),
        _SPANS,
    )
    assert isinstance(prepared, PreparedTargetInstruction)
    return target_write(prepared, inheritance.view(_SPANS))


def _plan(
    *writes: AdmittedWrite,
    instant: TransactionInstant | None = None,
    ownership: TemporalWriteOwnership = NO_TEMPORAL_WRITE_OWNERSHIP,
) -> WritePlan:
    return build_write_planner(_SPANS).finalize(
        WritePlanningRequest(
            actor_identity=TEST_ACTOR_IDENTITY,
            transaction_instant=instant or instant_at(_PLANNED_AT.isoformat()),
            concurrency="optimistic",
            composed_writes=admitted_writes(_SPANS, list(writes)),
            ownership=ownership,
        )
    )


def _deferred(plan: WritePlan) -> tuple[SettledWrite, CoverageReadRequest]:
    """``plan``'s one deferred write, and the coverage read the unit of work asks
    for when it binds that write's range."""
    (write,) = settled_writes(plan)
    assert write.deferred is not None
    return write, coverage_read(
        _SPANS, plan, transaction_instant=instant_at(_PLANNED_AT.isoformat())
    )


def _bind(
    settled: SettledWrite,
    rows: Sequence[PredecessorRow],
    *,
    ownership: TemporalWriteOwnership = NO_TEMPORAL_WRITE_OWNERSHIP,
    transaction_instant: TransactionInstant | None = None,
) -> BoundRange:
    return bind_held(
        _SPANS,
        alone(settled),
        rows,
        ownership=ownership,
        transaction_instant=transaction_instant or instant_at(_PLANNED_AT.isoformat()),
    )


def _windows(steps: Iterable[PlannedStep]) -> list[tuple[object, object, object]]:
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
    (planned,) = settled_writes(known)
    assert planned.deferred is None
    read, acquisition = _deferred(_plan(_update(head, _MAR, _SEP)))
    assert acquisition.terms[0].valid_time_windows == (temporal_read.TimeInterval(_JUN, _SEP),)

    bound = _bind(read, [_TAIL])

    assert bound.steps == plan_steps(known)
    # The changed parts of both originals hold the same complete state, so
    # they merge into one row; each original is still closed under its own
    # proof.
    assert _windows(bound.steps) == [
        (_JAN, _MAR, 100),
        (_MAR, _SEP, 300),
        (_SEP, INFINITY, 200),
    ]
    assert tuple(bound.changed) == tuple(planned.changed) == (head.key, tail.key)
    assert [tuple(bound.opened.fresh), tuple(bound.opened.continued)] == [
        tuple(planned.opened.fresh),
        (),
    ]
    assert (bound.removed, bound.derived, bound.current_outputs) == ((), (), ())
    # A deferred settled write's plan entry publishes nothing of its own.
    assert (tuple(read.changed), read.opened) == ((), Openings())


def test_a_read_that_found_no_row_binds_the_range_to_what_it_observed() -> None:
    head = _retained(_HEAD)
    settled, _acquisition = _deferred(_plan(_update(head, _MAR, _SEP)))

    bound = _bind(settled, [])

    assert [type(step) for step in bound.steps] == [PlannedClose, PlannedInsert, PlannedInsert]
    assert _windows(bound.steps) == [(_JAN, _MAR, 100), (_MAR, _JUN, 300)]
    assert tuple(bound.changed) == (head.key,)


def test_a_caller_start_the_read_did_not_find_fails_as_its_precondition() -> None:
    settled, _acquisition = _deferred(_plan(_target(_MAR, _SEP)))
    with pytest.raises(WritePreconditionError):
        _bind(settled, [])


def test_binding_reads_the_ownership_the_attempt_holds_when_it_binds() -> None:
    settled, _acquisition = _deferred(_plan(_target(_JUN, _SEP)))
    endpoint = TemporalRowCoordinates(_SPAN, (1,), (OPEN_END, OPEN_END))

    stored = _bind(settled, [_TAIL])
    owned = _bind(settled, [_TAIL], ownership=OpenedRows(frozenset({endpoint})))

    assert [type(step) for step in stored.steps] == [PlannedClose, PlannedInsert, PlannedInsert]
    # The same plan entry, bound once the attempt owns the row it starts from,
    # revises that row in place rather than closing it into history.
    assert [type(step) for step in owned.steps] == [PlannedTemporalRevision, PlannedInsert]
    assert tuple(owned.opened.fresh) == (
        TemporalRowCoordinates(_SPAN, (1,), (Finite(instant=_SEP), OPEN_END)),
    )
    assert tuple(owned.changed) == tuple(stored.changed) == (_retained(_TAIL).key,)


def test_every_milestone_a_binding_reads_is_its_own_state_of_one_shared_object_key() -> None:
    head = _retained(_HEAD)
    settled, _acquisition = _deferred(_plan(_update(head, _MAR, _SEP)))
    middle, tail = _span(_JUN, _JUL, 200), _span(_JUL, INFINITY, 250)

    bound = _bind(settled, [middle, tail])

    known, first, second = bound.changed
    assert known == head.key
    assert isinstance(first, TemporalObjectStateKey)
    assert isinstance(second, TemporalObjectStateKey)
    assert [state.milestone.valid_time for state in (first, second)] == [_JUN, _JUL]
    assert first.object is second.object
    assert first.object == ObjectKey(_SPAN, (("id", 1),))


def test_binding_stamps_the_instant_planning_resolved_and_reads_no_clock() -> None:
    head = _retained(_HEAD)
    planning = CountingClock([_PLANNED_AT])
    settled, _acquisition = _deferred(
        _plan(_update(head, _MAR, _SEP), instant=TransactionInstant(planning))
    )
    assert planning.calls == 1
    unread = CountingClock([])

    bound = _bind(settled, [_TAIL], transaction_instant=TransactionInstant(unread))

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
        id(step) for step in plan_steps(known) if isinstance(step, PlannedClose)
    )
    # Every produced row is finalized once, the two that then merge included,
    # and the merged row is not finalized again.
    assert [_row_window(row) for row in audit.rows] == _PRODUCED
    assert _windows(tuple(plan_steps(known))) == _MERGED

    audit.rows.clear()
    audit.closes.clear()
    settled, _acquisition = _deferred(_plan(_update(head, _MAR, _SEP)))
    assert (audit.rows, audit.closes) == ([], [])
    bound = _bind(settled, [_TAIL])
    assert sorted(map(id, audit.closes)) == sorted(
        id(step) for step in bound.steps if isinstance(step, PlannedClose)
    )
    assert [_row_window(row) for row in audit.rows] == _PRODUCED
    assert _windows(bound.steps) == _MERGED


_PRODUCED = [(_JAN, _MAR, 100), (_MAR, _JUN, 300), (_JUN, _SEP, 300), (_SEP, INFINITY, 200)]
_MERGED = [(_JAN, _MAR, 100), (_MAR, _SEP, 300), (_SEP, INFINITY, 200)]


def _row_window(row: WriteRow) -> tuple[object, object, object]:
    cells = {identity.name: value for identity, value in row.row.attributes.items()}
    return cells["validStart"], cells["validEnd"], cells["amount"]


@pytest.mark.parametrize(
    ("ownership", "retired"),
    [
        (NO_TEMPORAL_WRITE_OWNERSHIP, PlannedClose),
        (
            OpenedRows(
                frozenset({TemporalRowCoordinates(_SPAN, (1,), (Finite(instant=_JUN), OPEN_END))})
            ),
            PlannedTemporalRemoval,
        ),
    ],
    ids=["stored", "opened-by-the-attempt"],
)
def test_an_overlapped_observation_is_retired_by_whoever_owns_its_row(
    ownership: TemporalWriteOwnership, retired: type[PlannedStep]
) -> None:
    earlier = _retained(_span(_JAN, _JUN, 100))
    later = _retained(_span(_MAR, INFINITY, 200, tx_start=_T1))
    plan = _plan(_update(earlier, _MAR, _APR), _update(later, _MAY, _JUL), ownership=ownership)
    (write,) = settled_writes(plan)
    assert write.deferred is None
    validation, closing, *successors = plan_steps(plan)
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
    assert tuple(write.changed) == (earlier.key, later.key)
    assert tuple(write.removed) == (
        ()
        if retired is PlannedClose
        else (TemporalRowCoordinates(_SPAN, (1,), (Finite(instant=_JUN), OPEN_END)),)
    )


# --------------------------------------------------------------------------- #
# A lone keyed write enters range settlement as the admitted write it was     #
# buffered as: no composition of one write is built for it.                   #
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


def test_a_lone_observed_write_inside_its_predecessor_binds_at_once_from_its_own_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    head = _retained(_HEAD)
    built = _Compositions(monkeypatch)
    (buffered,) = admitted_writes(_SPANS, [_update(head, _MAR, _APR)])
    assert isinstance(buffered, StateObservedWrite)
    plan = _plan(buffered)
    assert built.built == 0
    (write,) = settled_writes(plan)
    assert write.deferred is None
    assert [type(step) for step in plan_steps(plan)] == [
        PlannedClose,
        PlannedInsert,
        PlannedInsert,
        PlannedInsert,
    ]
    assert _windows(tuple(plan_steps(plan))) == [
        (_JAN, _MAR, 100),
        (_MAR, _APR, 300),
        (_APR, _JUN, 100),
    ]
    assert tuple(write.changed) == (head.key,)


def test_a_lone_write_reaching_past_what_it_observed_reads_only_the_rest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    head = _retained(_HEAD)
    built = _Compositions(monkeypatch)
    _settled, acquisition = _deferred(_plan(_update(head, _MAR, _SEP)))
    assert built.built == 0
    assert acquisition.terms[0].valid_time_windows == (temporal_read.TimeInterval(_JUN, _SEP),)


@pytest.mark.parametrize("observation", [None, VersionObservation(observed_version=1)])
def test_a_temporal_write_holding_no_temporal_observation_is_refused_before_the_instant(
    observation: VersionObservation | None,
) -> None:
    prepared = prepare_wire_write(
        KeyedWriteInstruction(
            "amendUntil", "SequenceSpan", ({"id": 1, "amount": 300},), _MAR, _APR
        ),
        _SPANS,
    )
    assert isinstance(prepared, PreparedKeyedInstruction)
    item: AdmittedWrite = (
        prepared
        if observation is None
        else StateObservedWrite(
            prepared,
            RetainedObservation(
                VersionedObjectStateKey(ObjectKey(_SPAN, (("id", 1),)), 1), observation, None
            ),
        )
    )
    clock = CountingClock([_PLANNED_AT])
    with pytest.raises(WritePlanningError, match="closes the current milestone"):
        _plan(item, instant=TransactionInstant(clock))
    assert clock.calls == 0


# --------------------------------------------------------------------------- #
# A flush's scoped binding: one range bound per advance, its references       #
# dropped however the scope ends.                                              #
# --------------------------------------------------------------------------- #
class _Failed(Exception):
    pass


def _answering(held: AcquireRows, answers: list[object]) -> AcquireRows:
    """``held``'s answers, each recorded in ``answers`` as it is handed back."""

    def acquire[Request: RowRequest, Result](
        request: Request, consumer: RowConsumer[Request, Result], /
    ) -> Result:
        answer = held(request, consumer)
        answers.append(answer)
        return answer

    return acquire


def _scoped(settled: SettledWrite, acquire: AcquireRows) -> RangeBindings:
    return range_bindings(
        _SPANS,
        alone(settled),
        acquire,
        start=0,
        stop=1,
        transaction_instant=instant_at(_PLANNED_AT.isoformat()),
    )


def _binding_frames(failure: BaseException) -> list[FrameType]:
    return [
        frame
        for frame in frames(failure.__traceback__, module=ranges_module.__file__)
        if frame.f_code.co_qualname.startswith(f"{RangeBindings.__name__}.")
    ]


def test_a_range_is_read_and_bound_only_once_the_flush_advances_to_it() -> None:
    settled, _acquisition = _deferred(_plan(_update(_retained(_HEAD), _MAR, _SEP)))
    held = HeldRows(_SPANS, [_TAIL])
    with _scoped(settled, held) as bindings:
        assert held.requests == []
        bound = next(bindings)
        assert [type(request) for request in held.requests] == [CoverageReadRequest]
        assert next(bindings, None) is None
        assert next(bindings, None) is None
    assert _windows(bound.steps) == _MERGED


@pytest.mark.parametrize("leaves", ["break", "raise"])
def test_a_flush_leaving_its_bindings_leaves_them_holding_no_row_the_range_read(
    leaves: str,
) -> None:
    settled, _acquisition = _deferred(_plan(_update(_retained(_HEAD), _MAR, _SEP)))
    answers: list[object] = []
    bound: list[WriteGroup] = []
    bindings = _scoped(settled, _answering(HeldRows(_SPANS, [_TAIL]), answers))
    with contextlib.suppress(_Failed), bindings:
        for each in bindings:
            bound.append(each)
            if leaves == "raise":
                raise _Failed
            break
    (rows,) = answers
    assert rows is not None
    assert not reaches([bindings], rows)
    assert next(bindings, None) is None
    # What the bound group carries is the flush's, and stays usable.
    (each,) = bound
    assert _windows(each.steps) == _MERGED


def test_a_failed_binding_leaves_neither_its_bindings_nor_their_frames_holding_its_rows() -> None:
    settled, _acquisition = _deferred(_plan(_target(_MAR, _SEP)))
    answers: list[object] = []
    stored = HeldRows(_SPANS, [_span(_JAN, _JUN, 100, tx_start=_T1)])
    bindings = _scoped(settled, _answering(stored, answers))
    with pytest.raises(WritePreconditionError) as raised, bindings:
        next(bindings)
    (rows,) = answers
    owned = _binding_frames(raised.value)
    assert owned
    assert not reaches([bindings, *owned], rows)
    assert next(bindings, None) is None
