"""What a temporal object's writes against its stored coverage settle and bind
to, stated as explicit operations, coverage reads, conditions, effects, and
evidence: observed, insertion-authorized, and target first arrivals of
Transaction-Time-Only and Bitemporal objects, a caller's one condition kept
across its own destruction, and a reinsertion ordered after the removal it
follows."""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable, Sequence
from decimal import Decimal

import pytest

from parallax.core import inheritance, temporal_read
from parallax.core._execution._planning import build_write_planner
from parallax.core._execution._unit_work.admission import WriteAdmission
from parallax.core._execution._unit_work.instructions import (
    PreparedKeyedInstruction,
    TargetMutation,
    prepare_wire_write,
)
from parallax.core._execution._unit_work.retain import (
    InsertionIdentity,
    ParticipationToken,
    ReadEvidence,
)
from parallax.core._execution._unit_work.write_items import (
    AdmittedWrite,
    TargetWrite,
    target_write,
)
from parallax.core.base import INFINITY
from parallax.core.metamodel import EntityIdentity, Metamodel
from parallax.core.temporal_read import TimeInterval
from parallax.core.unit_work import (
    KeyedMutation,
    KeyedWriteInstruction,
    MissingTargetError,
    RetainedObservation,
    TargetWriteInstruction,
    TransactionInstant,
    WritePlanningRequest,
    WritePreconditionError,
    admitted_write,
)
from parallax.core.write_plan import (
    SUPERSEDED,
    TERMINATED,
    ObjectKey,
    PlannedClose,
    PlannedInsert,
    PredecessorRow,
    TemporalObservation,
    WritePlan,
)
from parallax.core.write_plan.keys import TemporalObjectStateKey
from parallax.core.write_plan.plan import (
    OPEN_BITEMPORAL_ENDS,
    BoundRange,
    Openings,
    SettledWrite,
    TemporalRowCoordinates,
    WriteEffects,
    WriteGroup,
)
from parallax.core.write_plan.steps import (
    FAILED_PRECONDITION,
    Finite,
    PlannedStep,
    PlannedTemporalRemoval,
    PlannedTemporalRevision,
    TemporalGate,
)
from parallax.core.write_plan.steps import INFINITY as OPEN_END
from tests._support.clock_probes import instant_at
from tests._support.planner_probes import TEST_ACTOR_IDENTITY, admit, plan_steps, settled_writes
from tests.unit._corpus_model_support import corpus_records, formed
from tests.unit.core._execution._unit_work._acquired_rows_support import (
    alone,
    bind_held,
    coverage_read,
)
from tests.unit.core._execution._unit_work._temporal_targets_support import (
    ENTITY,
    FAMILIES,
    FEB,
    JAN,
    JUN,
    LATER,
    MAR,
    MAY,
    OBJECT,
    POSITION,
    SEP,
    START,
    T0,
    T1,
    rectangle,
)

_BALANCE = formed(corpus_records()["balance"])
_BALANCE_ENTITY = EntityIdentity("parallax.compatibility", "Balance")
_BALANCE_OBJECT = ObjectKey(_BALANCE_ENTITY, (("id", 1),))
_AT = "2024-10-01T00:00:00+00:00"
_INSTANT = dt.datetime.fromisoformat(_AT)


def _instant() -> TransactionInstant:
    return instant_at(_AT)


def _admission(meta: Metamodel) -> WriteAdmission:
    return WriteAdmission(meta, inserted_version=lambda _entity, _from: None, observations={})


def _unconfirmed(item: TargetWrite) -> TargetWrite:
    return item


def _plan(admission: WriteAdmission, meta: Metamodel) -> WritePlan:
    return build_write_planner(meta).finalize(
        WritePlanningRequest(
            actor_identity=TEST_ACTOR_IDENTITY,
            transaction_instant=_instant(),
            concurrency="optimistic",
            composed_writes=admission.composed_writes(),
            ownership=admission.ownership,
        )
    )


def _planned(meta: Metamodel, *writes: AdmittedWrite) -> WritePlan:
    admission = _admission(meta)
    for write in writes:
        admit(admission, write)
    return _plan(admission, meta)


def _bound(meta: Metamodel, settled: SettledWrite, rows: Sequence[PredecessorRow]) -> BoundRange:
    return bind_held(meta, alone(settled), rows, transaction_instant=_instant())


def _opened(steps: Iterable[PlannedStep], member: str = "value") -> list[tuple[object, ...]]:
    """Each row ``steps`` open: its Valid-Time window where it has one, and
    ``member``."""
    opened: list[tuple[object, ...]] = []
    for step in steps:
        if isinstance(step, PlannedInsert):
            for entry in step.entries:
                cells = {identity.name: value for identity, value in entry.row.attributes.items()}
                window = (cells["validStart"], cells["validEnd"]) if "validStart" in cells else ()
                opened.append((*window, cells[member]))
    return opened


def _position(
    mutation: KeyedMutation, valid_from: dt.datetime, until: dt.datetime | None, **members: object
) -> PreparedKeyedInstruction:
    prepared = prepare_wire_write(
        KeyedWriteInstruction(mutation, "Position", ({"id": 1, **members},), valid_from, until),
        POSITION,
    )
    assert isinstance(prepared, PreparedKeyedInstruction)
    return prepared


def _balance(mutation: KeyedMutation, **members: object) -> PreparedKeyedInstruction:
    prepared = prepare_wire_write(
        KeyedWriteInstruction(mutation, "Balance", ({"id": 1, **members},)), _BALANCE
    )
    assert isinstance(prepared, PreparedKeyedInstruction)
    return prepared


def _balance_row(value: str, tx_start: dt.datetime = T0) -> PredecessorRow:
    return PredecessorRow(
        members={
            "id": 1,
            "acctNum": "A",
            "value": Decimal(value),
            "txStart": tx_start,
            "txEnd": INFINITY,
        }
    )


def _balance_observed(row: PredecessorRow) -> RetainedObservation:
    shape = temporal_read.view(_BALANCE).shape(_BALANCE_ENTITY)
    assert shape is not None
    state = TemporalObjectStateKey(_BALANCE_OBJECT, temporal_read.milestone_edge(shape, row, None))
    return RetainedObservation(state, TemporalObservation(predecessor=row), None)


def _source(key: ObjectKey, observation: RetainedObservation) -> ReadEvidence:
    return ReadEvidence(key.entity, key, ParticipationToken(), observation)


def _gate(close: PlannedClose) -> object:
    concurrency = close.concurrency
    assert isinstance(concurrency, TemporalGate)
    return concurrency.observed_start


# --------------------------------------------------------------------------- #
# An observed write: its predecessor known from the read, or read for the rest. #
# --------------------------------------------------------------------------- #
def test_an_observed_bitemporal_write_inside_its_rectangle_binds_at_planning() -> None:
    source = _source(OBJECT, START)
    plan = _planned(
        POSITION,
        admitted_write(
            _position("amendUntil", MAR, MAY, value="150.00"), START, OBJECT, source=source
        ),
    )
    (write,) = settled_writes(plan)
    assert write.deferred is None
    close, *opened = plan_steps(plan)
    assert isinstance(close, PlannedClose)
    assert (close.cause, _gate(close)) == (SUPERSEDED, T0)
    assert close.target.end_values == (Finite(instant=JUN), OPEN_END)
    assert _opened(opened) == [
        (JAN, MAR, Decimal("100.00")),
        (MAR, MAY, Decimal("150.00")),
        (MAY, JUN, Decimal("100.00")),
    ]
    assert tuple(write.changed) == (START.key,)
    assert tuple(map(id, write.source_evidence)) == (id(source),)


def test_an_observed_bitemporal_write_past_its_rectangle_reads_the_rest_at_execution() -> None:
    source = _source(OBJECT, START)
    plan = _planned(
        POSITION,
        admitted_write(
            _position("amendUntil", MAR, SEP, value="150.00"), START, OBJECT, source=source
        ),
    )
    (write,) = settled_writes(plan)
    assert write.deferred is not None
    assert tuple(map(id, write.source_evidence)) == (id(source),)
    (term,) = coverage_read(POSITION, alone(write), transaction_instant=_instant()).terms
    assert term.valid_time_windows == (TimeInterval(JUN, SEP),)
    bound = _bound(POSITION, write, [rectangle(JUN, INFINITY, "200.00")])
    closes = [step for step in bound.steps if isinstance(step, PlannedClose)]
    assert [close.target.end_values for close in closes] == [
        (Finite(instant=JUN), OPEN_END),
        OPEN_BITEMPORAL_ENDS,
    ]
    assert _opened(bound.steps) == [
        (JAN, MAR, Decimal("100.00")),
        (MAR, SEP, Decimal("150.00")),
        (SEP, INFINITY, Decimal("200.00")),
    ]
    assert tuple(bound.changed) == (START.key, LATER.key)


@pytest.mark.parametrize(
    ("mutation", "members", "steps", "opened"),
    [
        ("amend", {"value": "175.00"}, [PlannedClose, PlannedInsert], [(Decimal("175.00"),)]),
        ("terminate", {}, [PlannedClose], []),
    ],
    ids=["update", "terminate"],
)
def test_an_observed_transaction_time_write_closes_its_observed_row_at_planning(
    mutation: KeyedMutation,
    members: dict[str, object],
    steps: list[type[PlannedStep]],
    opened: list[tuple[object, ...]],
) -> None:
    observed = _balance_observed(_balance_row("100.00"))
    source = _source(_BALANCE_OBJECT, observed)
    plan = _planned(
        _BALANCE,
        admitted_write(_balance(mutation, **members), observed, _BALANCE_OBJECT, source=source),
    )
    (write,) = settled_writes(plan)
    assert write.deferred is None
    planned = plan_steps(plan)
    assert [type(step) for step in planned] == steps
    close = planned[0]
    assert isinstance(close, PlannedClose)
    assert (close.cause, _gate(close)) == (
        SUPERSEDED if mutation == "amend" else TERMINATED,
        T0,
    )
    assert _opened(planned) == opened
    assert tuple(write.changed) == (observed.key,)
    assert tuple(map(id, write.source_evidence)) == (id(source),)


# --------------------------------------------------------------------------- #
# A target write: its caller's start gates the row it finds.                  #
# --------------------------------------------------------------------------- #
def _balance_target(tx_start: dt.datetime, **members: object) -> TargetWrite:
    return target_write(
        prepare_wire_write(
            TargetWriteInstruction("amend", "Balance", {"id": 1, **members}, if_tx_start=tx_start),
            _BALANCE,
        ),
        inheritance.view(_BALANCE),
    )


def test_a_transaction_time_target_binds_the_row_its_caller_named() -> None:
    (write,) = settled_writes(_planned(_BALANCE, _balance_target(T0, value="175.00")))
    assert write.deferred is not None
    assert write.source_evidence == ()
    bound = _bound(_BALANCE, write, [_balance_row("100.00")])
    close, opened = bound.steps
    assert isinstance(close, PlannedClose)
    assert close.affected_rows.on_shortfall == FAILED_PRECONDITION
    assert _opened([opened]) == [(Decimal("175.00"),)]


@pytest.mark.parametrize(
    "rows",
    [pytest.param([], id="no-row"), pytest.param([_balance_row("100.00", T1)], id="restated")],
)
def test_a_transaction_time_target_whose_row_moved_on_binds_nothing(
    rows: list[PredecessorRow],
) -> None:
    (write,) = settled_writes(_planned(_BALANCE, _balance_target(T0, value="175.00")))
    with pytest.raises(WritePreconditionError) as refused:
        _bound(_BALANCE, write, rows)
    assert refused.value.expected == T0


def _position_target(mutation: TargetMutation, **members: object) -> TargetWrite:
    return target_write(
        prepare_wire_write(
            TargetWriteInstruction(
                mutation,
                "Position",
                {"id": 1, **members},
                if_tx_start=T0,
                valid_from=MAR,
                until=SEP,
            ),
            POSITION,
        ),
        FAMILIES,
    )


def test_a_target_assignment_and_its_destruction_over_one_window_state_one_condition() -> None:
    (write,) = settled_writes(
        _planned(
            POSITION,
            _position_target("amendUntil", value="150.00"),
            _position_target("terminateUntil"),
        )
    )
    assert write.deferred is not None
    stored = [rectangle(JAN, JUN, "100.00"), rectangle(JUN, INFINITY, "200.00")]
    bound = _bound(POSITION, write, stored)
    closes = [step for step in bound.steps if isinstance(step, PlannedClose)]
    # Only the rectangle holding the window's start stands under the caller's
    # condition, which the two writes state once.
    assert [close.affected_rows.on_shortfall == FAILED_PRECONDITION for close in closes] == [
        True,
        False,
    ]
    assert _opened(bound.steps) == [
        (JAN, MAR, Decimal("100.00")),
        (SEP, INFINITY, Decimal("200.00")),
    ]
    with pytest.raises(WritePreconditionError) as refused:
        _bound(POSITION, write, [rectangle(JAN, JUN, "100.00", tx_start=T1)])
    assert refused.value.expected == T0


# --------------------------------------------------------------------------- #
# A write a flushed insertion authorized revises the row the attempt opened.   #
# --------------------------------------------------------------------------- #
def _stored_insertion(
    meta: Metamodel,
    insert: PreparedKeyedInstruction,
    key: ObjectKey,
    opened: TemporalRowCoordinates,
) -> tuple[WriteAdmission, InsertionIdentity]:
    """An admission whose insertion of ``key`` flushed and opened ``opened``,
    and the identity buffering that insertion issued."""
    admission = _admission(meta)
    identity = admission.admit_insert(admitted_write(insert, None, key), insertion_advice=None)
    assert identity is not None
    admission.drain_planned()
    admission.complete(WriteEffects(opened=Openings(continued=(opened,))), (), at=1)
    return admission, identity


def _authorized(
    admission: WriteAdmission, identity: InsertionIdentity, prepared: PreparedKeyedInstruction
) -> WriteAdmission:
    admission.admit(
        admitted_write(prepared, None, identity.object_key, authority=identity),
        confirm_target=_unconfirmed,
    )
    return admission


_POSITION_OPENED = TemporalRowCoordinates(ENTITY, (1,), OPEN_BITEMPORAL_ENDS)
_BALANCE_OPENED = TemporalRowCoordinates(_BALANCE_ENTITY, (1,), (OPEN_END,))


def test_a_bitemporal_write_a_flushed_insertion_authorized_revises_its_row_from_the_anchor() -> (
    None
):
    admission, identity = _stored_insertion(
        POSITION,
        _position("insert", FEB, None, acctNum="A", value="100.00"),
        OBJECT,
        _POSITION_OPENED,
    )
    _authorized(admission, identity, _position("amendUntil", FEB, JUN, value="150.00"))
    (write,) = settled_writes(_plan(admission, POSITION))
    assert write.deferred is not None
    assert write.source_evidence == ()
    (term,) = coverage_read(POSITION, alone(write), transaction_instant=_instant()).terms
    assert term.valid_time_windows == (TimeInterval(FEB, JUN),)
    owned = rectangle(FEB, INFINITY, "100.00", tx_start=_INSTANT)
    bound = bind_held(
        POSITION,
        alone(write),
        [owned],
        transaction_instant=_instant(),
        ownership=admission.ownership,
    )
    assert not any(isinstance(step, PlannedClose) for step in bound.steps)
    (revision,) = (step for step in bound.steps if isinstance(step, PlannedTemporalRevision))
    assert revision.target.end_values == OPEN_BITEMPORAL_ENDS
    assert _opened(bound.steps) == [(FEB, JUN, Decimal("150.00"))]


def test_a_bitemporal_write_whose_insertion_anchor_has_no_row_fails_its_target() -> None:
    admission, identity = _stored_insertion(
        POSITION,
        _position("insert", FEB, None, acctNum="A", value="100.00"),
        OBJECT,
        _POSITION_OPENED,
    )
    _authorized(admission, identity, _position("amendUntil", FEB, JUN, value="150.00"))
    (write,) = settled_writes(_plan(admission, POSITION))
    with pytest.raises(MissingTargetError):
        bind_held(
            POSITION,
            alone(write),
            [rectangle(MAR, INFINITY, "100.00", tx_start=_INSTANT)],
            transaction_instant=_instant(),
            ownership=admission.ownership,
        )


@pytest.mark.parametrize(
    ("mutation", "members", "step"),
    [
        ("amend", {"value": "175.00"}, PlannedTemporalRevision),
        ("terminate", {}, PlannedTemporalRemoval),
    ],
    ids=["update", "terminate"],
)
def test_a_transaction_time_write_a_flushed_insertion_authorized_revises_its_own_row(
    mutation: KeyedMutation, members: dict[str, object], step: type[PlannedStep]
) -> None:
    admission, identity = _stored_insertion(
        _BALANCE,
        _balance("insert", acctNum="A", value="100.00"),
        _BALANCE_OBJECT,
        _BALANCE_OPENED,
    )
    _authorized(admission, identity, _balance(mutation, **members))
    (write,) = settled_writes(_plan(admission, _BALANCE))
    assert write.deferred is not None
    assert write.source_evidence == ()
    bound = bind_held(
        _BALANCE,
        alone(write),
        [_balance_row("100.00", _INSTANT)],
        transaction_instant=_instant(),
        ownership=admission.ownership,
    )
    # The row is the attempt's own, so it is revised or removed in place and
    # nothing opens beside it.
    assert [type(each) for each in bound.steps] == [step]


# --------------------------------------------------------------------------- #
# A reinsertion executes after the removal of everything it replaces.         #
# --------------------------------------------------------------------------- #
def test_a_reinsertion_follows_the_removal_of_its_earlier_insertion() -> None:
    admission, identity = _stored_insertion(
        POSITION,
        _position("insert", FEB, None, acctNum="A", value="100.00"),
        OBJECT,
        _POSITION_OPENED,
    )
    _authorized(admission, identity, _position("terminate", FEB, None))
    admission.admit_insert(
        admitted_write(_position("insert", FEB, None, acctNum="B", value="300.00"), None, OBJECT),
        insertion_advice=None,
    )
    plan = _plan(admission, POSITION)
    removal, reinsertion = plan.entries
    # An insert ordinarily runs ahead of every removal; this one follows it.
    assert isinstance(removal, SettledWrite) and removal.deferred is not None
    assert isinstance(reinsertion, WriteGroup)
    assert _opened(reinsertion.steps, "acctNum") == [(FEB, INFINITY, "B")]
