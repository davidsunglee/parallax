"""What a temporal object's writes against its stored coverage settle and bind
to, stated as explicit operations, coverage reads, conditions, effects, and
evidence: observed and target first arrivals of Transaction-Time-Only and
Bitemporal objects, and a caller's one condition kept across its own
destruction."""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Iterable, Sequence
from decimal import Decimal

import pytest

from parallax.core import ConflictError
from parallax.core._execution._planning import build_write_planner
from parallax.core._execution._unit_work.admission import WriteAdmission
from parallax.core._execution._unit_work.evidence import (
    ParticipationToken,
    ReadEvidence,
)
from parallax.core._execution._unit_work.instructions import (
    PreparedKeyedInstruction,
    TargetMutation,
    prepare_wire_write,
)
from parallax.core._execution._unit_work.ranges import DeferredRange
from parallax.core._execution._unit_work.write_items import (
    AdmittedWrite,
    CallerConditioned,
    LicensedWrite,
    target_write,
)
from parallax.core._execution._unit_work.write_plan import SettledWrite, WritePlan
from parallax.core.internal import inheritance, temporal_read
from parallax.core.internal.base import INFINITY
from parallax.core.internal.metamodel import AttributeIdentity, EntityIdentity, Metamodel
from parallax.core.internal.planned_step import (
    SUPERSEDED,
    TERMINATED,
    ObjectKey,
    PlannedClose,
    PlannedInsert,
    PredecessorRow,
    TemporalObservation,
)
from parallax.core.internal.planned_step.keys import TemporalObjectStateKey
from parallax.core.internal.planned_step.steps import (
    FAILED_PRECONDITION,
    Finite,
    PlannedStep,
    PlannedTemporalRemoval,
    TemporalGate,
)
from parallax.core.internal.planned_step.steps import INFINITY as OPEN_END
from parallax.core.internal.planned_step.write_effects import (
    NO_TEMPORAL_WRITE_OWNERSHIP,
    OPEN_BITEMPORAL_ENDS,
    TRANSACTION_TIME_ENDS,
    TemporalRowCoordinates,
    TemporalWriteOwnership,
)
from parallax.core.internal.temporal_read import TimeInterval
from parallax.core.internal.unit_work import (
    TEMPORAL_CONFLICT,
    KeyedMutation,
    KeyedWriteInstruction,
    RetainedObservation,
    TargetWriteInstruction,
    TransactionInstant,
    WritePlanningRequest,
    WritePreconditionError,
    admitted_write,
)
from tests._support.bindings import bound_model
from tests._support.clock_probes import instant_at
from tests._support.errors import raises_code
from tests._support.planner_probes import (
    TEST_ACTOR_IDENTITY,
    admit,
    deferred_ranges,
    plan_steps,
    settled_writes,
    write_admission,
)
from tests._support.write_preparation import write_preparation_of
from tests.unit._corpus_model_support import corpus_records, formed
from tests.unit.core._execution._unit_work._acquired_rows_support import (
    alone,
    bind_held,
    coverage_read,
)
from tests.unit.core._execution._unit_work._ownership_support import OpenedRows
from tests.unit.core._execution._unit_work._temporal_targets_support import (
    FAMILIES,
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


def _instant() -> TransactionInstant:
    return instant_at(_AT)


def _plan(
    admission: WriteAdmission,
    meta: Metamodel,
    ownership: TemporalWriteOwnership = NO_TEMPORAL_WRITE_OWNERSHIP,
) -> WritePlan:
    return build_write_planner(bound_model(meta)).finalize(
        WritePlanningRequest(
            actor_identity=TEST_ACTOR_IDENTITY,
            transaction_instant=_instant(),
            preference="optimistic",
            composed_writes=admission.composed_writes(),
            ownership=ownership,
        )
    )


def _planned(meta: Metamodel, *writes: AdmittedWrite) -> WritePlan:
    admission = write_admission(meta)
    for write in writes:
        admit(admission, write)
    return _plan(admission, meta)


def _bound(meta: Metamodel, settled: DeferredRange, rows: Sequence[PredecessorRow]) -> SettledWrite:
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
        write_preparation_of(POSITION),
    )
    assert isinstance(prepared, PreparedKeyedInstruction)
    return prepared


def _balance(mutation: KeyedMutation, **members: object) -> PreparedKeyedInstruction:
    prepared = prepare_wire_write(
        KeyedWriteInstruction(mutation, "Balance", ({"id": 1, **members},)),
        write_preparation_of(_BALANCE),
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
    shape = temporal_read.temporal_facet_of(_BALANCE).shape(_BALANCE_ENTITY)
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
    assert not deferred_ranges(plan)
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
    (write,) = deferred_ranges(plan)
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
    assert not deferred_ranges(plan)
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
def _balance_target(
    tx_start: dt.datetime, mutation: TargetMutation = "amend", **members: object
) -> LicensedWrite[CallerConditioned]:
    return target_write(
        prepare_wire_write(
            TargetWriteInstruction(mutation, "Balance", {"id": 1, **members}, if_tx_start=tx_start),
            write_preparation_of(_BALANCE),
        ),
        inheritance.inheritance_facet_of(_BALANCE),
    )


def test_a_transaction_time_target_binds_the_row_its_caller_named() -> None:
    (write,) = deferred_ranges(_planned(_BALANCE, _balance_target(T0, value="175.00")))
    assert write.source_evidence == ()
    bound = _bound(_BALANCE, write, [_balance_row("100.00")])
    close, opened = bound.steps
    assert isinstance(close, PlannedClose)
    assert close.affected_rows.on_shortfall == FAILED_PRECONDITION
    assert _opened([opened]) == [(Decimal("175.00"),)]


def test_a_transaction_time_target_finding_no_row_binds_nothing() -> None:
    (write,) = deferred_ranges(_planned(_BALANCE, _balance_target(T0, value="175.00")))
    with pytest.raises(WritePreconditionError) as refused:
        _bound(_BALANCE, write, [])
    assert refused.value.expected == T0


def _stated_milestone(tx_start: dt.datetime) -> TemporalObjectStateKey:
    return TemporalObjectStateKey(_BALANCE_OBJECT, temporal_read.Edge(tx_time=tx_start))


_OWNED_BALANCE = OpenedRows(
    frozenset({TemporalRowCoordinates(_BALANCE_ENTITY, (1,), TRANSACTION_TIME_ENDS)})
)


@pytest.mark.parametrize(
    "writes",
    [
        lambda: [_balance_target(T0, "terminate")],
        lambda: [_balance_target(T0, value="175.00"), _balance_target(T0, "terminate")],
    ],
    ids=["termination", "amendment-then-termination"],
)
def test_an_optimistic_transaction_time_target_assigning_nothing_binds_from_its_stated_start(
    writes: Callable[[], list[LicensedWrite[CallerConditioned]]],
) -> None:
    plan = _planned(_BALANCE, *writes())
    (write,) = settled_writes(plan)
    assert not deferred_ranges(plan)
    (close,) = plan_steps(plan)
    assert isinstance(close, PlannedClose)
    assert (close.cause, _gate(close)) == (TERMINATED, T0)
    assert close.affected_rows.on_shortfall == FAILED_PRECONDITION
    assert tuple(write.changed) == (_stated_milestone(T0),)


def test_a_transaction_time_termination_of_an_owned_row_removes_it_from_its_stated_start() -> None:
    admission = write_admission(_BALANCE)
    admit(admission, _balance_target(T0, "terminate"))
    plan = _plan(admission, _BALANCE, _OWNED_BALANCE)
    (write,) = settled_writes(plan)
    (removal,) = plan_steps(plan)
    assert isinstance(removal, PlannedTemporalRemoval)
    assert removal.concurrency == TemporalGate(
        start_attribute=AttributeIdentity(_BALANCE_ENTITY, "txStart"), observed_start=T0
    )
    assert removal.affected_rows.on_shortfall == FAILED_PRECONDITION
    assert tuple(write.removed) == tuple(_OWNED_BALANCE.coordinates)


@pytest.mark.parametrize(
    "tx_start",
    [instant_at(_AT).value(), instant_at("2024-11-01T00:00:00+00:00").value()],
    ids=["equal", "later"],
)
def test_a_termination_stating_a_start_its_instant_cannot_follow_is_refused_at_planning(
    tx_start: dt.datetime,
) -> None:
    with raises_code(ConflictError, TEMPORAL_CONFLICT):
        _planned(_BALANCE, _balance_target(tx_start, "terminate"))


def _position_target(
    mutation: TargetMutation, **members: object
) -> LicensedWrite[CallerConditioned]:
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
            write_preparation_of(POSITION),
        ),
        FAMILIES,
    )


def test_a_target_assignment_and_its_destruction_over_one_window_state_one_condition() -> None:
    (write,) = deferred_ranges(
        _planned(
            POSITION,
            _position_target("amendUntil", value="150.00"),
            _position_target("terminateUntil"),
        )
    )
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
