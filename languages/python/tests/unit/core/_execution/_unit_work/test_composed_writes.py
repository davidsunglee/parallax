"""How a temporal object's observed writes compose at admission and what the
composition settles into, driven at the planner seam without a database."""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from decimal import Decimal

import pytest

from parallax.core import temporal_read
from parallax.core._execution._planning import build_write_planner
from parallax.core._execution._unit_work.admission import WriteAdmission
from parallax.core._execution._unit_work.instructions import (
    PreparedKeyedInstruction,
    prepare_wire_write,
)
from parallax.core._execution._unit_work.retain import ParticipationToken, ReadEvidence
from parallax.core._execution._unit_work.write_items import (
    ComposedTemporalWrite,
    StateObservedIntent,
    StateObservedWrite,
    TargetWrite,
)
from parallax.core._execution._unit_work.write_settlement import SettledWriteWithSource
from parallax.core.base import INFINITY
from parallax.core.metamodel import EntityIdentity
from parallax.core.unit_work import (
    AdmittedWrite,
    KeyedMutation,
    KeyedWriteInstruction,
    RetainedObservation,
    WriteEvidenceError,
    WritePlanningRequest,
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
    VersionObservation,
    WritePlanningError,
)
from parallax.core.write_plan.keys import (
    TemporalObjectStateKey,
    VersionedObjectStateKey,
    object_state_key_from_observation,
)
from parallax.core.write_plan.plan import (
    Openings,
    SettledWrite,
    TemporalRowCoordinates,
    WriteEffects,
    WriteGroup,
    WritePlan,
)
from parallax.core.write_plan.steps import INFINITY as OPEN_END
from parallax.core.write_plan.steps import PlannedStep
from tests._support.clock_probes import instant_at
from tests._support.planner_probes import (
    TEST_ACTOR_IDENTITY,
    admitted_writes,
    plan_steps,
    settled_writes,
)
from tests.unit._corpus_model_support import corpus_records, formed
from tests.unit.core._execution._unit_work._temporal_targets_support import (
    AUG,
    DEC,
    JAN,
    JUN,
    MAR,
    MAY,
    OBJECT,
    POSITION,
    SEP,
    START,
)

_BALANCE = formed(corpus_records()["balance"])
_ENTITY = EntityIdentity("parallax.compatibility", "Balance")
_OBJECT = ObjectKey(_ENTITY, (("id", 1),))
_JAN = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
_MAR = dt.datetime(2024, 3, 1, tzinfo=dt.UTC)


def _observation(tx_start: dt.datetime, value: str) -> RetainedObservation:
    """A retained observation of Balance 1's milestone opened at ``tx_start``."""
    observation = TemporalObservation(
        predecessor=PredecessorRow(
            members={
                "id": 1,
                "acctNum": "A",
                "value": Decimal(value),
                "txStart": tx_start,
                "txEnd": INFINITY,
            }
        )
    )
    shape = temporal_read.view(_BALANCE).shape(_ENTITY)
    assert shape is not None
    state = TemporalObjectStateKey(
        _OBJECT, temporal_read.milestone_edge(shape, observation.predecessor, None)
    )
    return RetainedObservation(state, observation, None)


_STALE = _observation(_JAN, "100.00")
_CURRENT = _observation(_MAR, "120.00")


_PARTICIPATION = ParticipationToken()


def _source(observation: RetainedObservation) -> ReadEvidence:
    return ReadEvidence(_ENTITY, _OBJECT, _PARTICIPATION, observation)


def _write(
    mutation: KeyedMutation,
    evidence: RetainedObservation,
    *,
    source: ReadEvidence | None = None,
    **members: object,
) -> StateObservedWrite:
    prepared = prepare_wire_write(
        KeyedWriteInstruction(mutation, "Balance", ({"id": 1, **members},)), _BALANCE
    )
    item = admitted_write(prepared, evidence, evidence.key.object, source=source)
    assert isinstance(item, StateObservedWrite)
    return item


def _plan(*writes: StateObservedWrite) -> WritePlan:
    return build_write_planner(_BALANCE).finalize(
        WritePlanningRequest(
            actor_identity=TEST_ACTOR_IDENTITY,
            transaction_instant=instant_at("2024-06-01T00:00:00+00:00"),
            concurrency="optimistic",
            composed_writes=admitted_writes(_BALANCE, writes),
        )
    )


def test_two_observations_of_one_transaction_time_row_validate_the_earlier() -> None:
    # Two observations of one Transaction-Time-Only row cannot both be current:
    # the later-authored one is the milestone the composition rewrites, and the
    # earlier is closed on its own gated address first, so a stale condition
    # fails before anything opens. The one write keeps both sources' evidence.
    stale, current = _source(_STALE), _source(_CURRENT)
    plan = _plan(
        _write("amend", _STALE, source=stale, value="150.00"),
        _write("amend", _CURRENT, source=current, value="175.00"),
    )
    steps = list(plan_steps(plan))
    assert [type(step) for step in steps] == [PlannedClose, PlannedClose, PlannedInsert]
    assert [step.cause for step in steps if isinstance(step, PlannedClose)] == [
        TERMINATED,
        SUPERSEDED,
    ]
    successor = steps[2]
    assert isinstance(successor, PlannedInsert)
    (entry,) = successor.entries
    assert {ident.name: value for ident, value in entry.row.attributes.items()}["value"] == (
        Decimal("175.00")
    )
    (write,) = settled_writes(plan)
    assert isinstance(write, SettledWriteWithSource)
    assert [id(evidence) for evidence in write.source_evidence] == [id(stale), id(current)]


def test_terminations_through_two_observations_compose_to_destruction_alone() -> None:
    # A composition that assigns nothing destroys the row it reaches and opens
    # nothing, ordered as a destructive write.
    stale, current = _observation(_JAN, "100.00"), _observation(_MAR, "120.00")
    composed = admitted_writes(_BALANCE, [_write("terminate", stale), _write("terminate", current)])
    (write,) = composed
    assert isinstance(write, ComposedTemporalWrite) and write.phase == "delete"
    steps = list(plan_steps(_plan(_write("terminate", stale), _write("terminate", current))))
    assert [type(step) for step in steps] == [PlannedClose, PlannedClose]


def test_a_termination_after_an_update_through_another_observation_ends_the_row() -> None:
    stale, current = _observation(_JAN, "100.00"), _observation(_MAR, "120.00")
    steps = list(
        plan_steps(
            _plan(
                _write("amend", stale, value="150.00"),
                _write("terminate", current),
                _write("terminate", current),
            )
        )
    )
    assert [type(step) for step in steps] == [PlannedClose, PlannedClose]


def test_a_repeated_termination_of_one_observation_adds_nothing() -> None:
    current = _observation(_MAR, "120.00")
    (write,) = admitted_writes(
        _BALANCE, [_write("terminate", current), _write("terminate", current)]
    )
    assert isinstance(write, ComposedTemporalWrite)
    (intent,) = write.intents
    assert isinstance(intent, StateObservedIntent)
    assert intent.intent.kind == "destructive"
    assert intent.retained_observation is current


def test_an_assignment_after_a_destruction_over_its_coverage_is_refused() -> None:
    # An assignment after a destruction over the same coverage resurrects
    # nothing, so admission refuses it rather than composing or keeping both.
    stale, current = _observation(_JAN, "100.00"), _observation(_MAR, "120.00")
    with pytest.raises(WriteEvidenceError) as refused:
        admitted_writes(
            _BALANCE, [_write("terminate", stale), _write("amend", current, value="1.00")]
        )
    assert refused.value.code == "write-evidence-already-claimed"


@pytest.mark.parametrize(
    ("first", "second"),
    [("terminate", "terminate"), ("amend", "terminate"), ("amend", "amend")],
    ids=["deduplicated", "superseded", "coalesced"],
)
def test_every_equal_but_distinct_source_of_one_observation_survives_its_writes_composing(
    first: KeyedMutation, second: KeyedMutation
) -> None:
    current = _observation(_MAR, "120.00")
    earlier, later = _source(current), _source(current)
    assert earlier == later and earlier is not later
    (write,) = settled_writes(
        _plan(
            _write(first, current, source=earlier, value="1.00")
            if first == "amend"
            else _write(first, current, source=earlier),
            _write(second, current, source=later, value="2.00")
            if second == "amend"
            else _write(second, current, source=later),
        )
    )
    assert isinstance(write, SettledWriteWithSource)
    assert sorted(map(id, write.source_evidence)) == sorted((id(earlier), id(later)))


def test_a_bitemporal_write_carrying_no_temporal_observation_is_refused_as_unobserved() -> None:
    # Only a Temporal Observation states a predecessor a range could start
    # from, so any other evidence reaches the ordinary required-observation
    # refusal rather than a range.
    model = formed(corpus_records()["position"])
    prepared = prepare_wire_write(
        KeyedWriteInstruction(
            "amend",
            "Position",
            ({"id": 1, "value": "1.00"},),
            dt.datetime(2024, 3, 1, tzinfo=dt.UTC),
        ),
        model,
    )
    position = ObjectKey(prepared.target.identity, (("id", 1),))
    unobserved = RetainedObservation(
        VersionedObjectStateKey(position, 1), VersionObservation(observed_version=1), None
    )
    write = admitted_write(prepared, unobserved, position)
    assert isinstance(write, StateObservedWrite)
    with pytest.raises(WritePlanningError, match="requires the Temporal Observation"):
        build_write_planner(model).finalize(
            WritePlanningRequest(
                actor_identity=TEST_ACTOR_IDENTITY,
                transaction_instant=instant_at("2024-06-01T00:00:00+00:00"),
                concurrency="optimistic",
                composed_writes=admitted_writes(model, [write]),
            )
        )


def test_two_observed_rectangles_bind_at_planning_when_they_cover_the_range() -> None:
    # Two reads of one object observed two disjoint rectangles that together
    # cover everything both writes request, so the composition binds at
    # planning: each rectangle closes once, then every piece opens, the equal
    # 150 pieces either side of June as one row.
    model = formed(corpus_records()["position"])
    jun, aug = dt.datetime(2024, 6, 1, tzinfo=dt.UTC), dt.datetime(2024, 8, 1, tzinfo=dt.UTC)

    def rectangle(start: dt.datetime, end: object, value: str) -> TemporalObservation:
        return TemporalObservation(
            predecessor=PredecessorRow(
                members={
                    "id": 1,
                    "acctNum": "A",
                    "value": Decimal(value),
                    "validStart": start,
                    "validEnd": end,
                    "txStart": _JAN,
                    "txEnd": INFINITY,
                }
            )
        )

    position = EntityIdentity("parallax.compatibility", "Position")
    shape = temporal_read.view(model).shape(position)
    assert shape is not None

    def update(valid_from: dt.datetime, value: str, observed: TemporalObservation) -> AdmittedWrite:
        prepared = prepare_wire_write(
            KeyedWriteInstruction("amend", "Position", ({"id": 1, "value": value},), valid_from),
            model,
        )
        state = object_state_key_from_observation(
            ObjectKey(position, (("id", 1),)), observed, shape
        )
        return admitted_write(prepared, RetainedObservation(state, observed, None), state.object)

    writes = admitted_writes(
        model,
        [
            update(_MAR, "150.00", rectangle(_JAN, jun, "100.00")),
            update(aug, "300.00", rectangle(jun, INFINITY, "200.00")),
        ],
    )
    plan = build_write_planner(model).finalize(
        WritePlanningRequest(
            actor_identity=TEST_ACTOR_IDENTITY,
            transaction_instant=instant_at("2024-10-01T00:00:00+00:00"),
            concurrency="optimistic",
            composed_writes=writes,
        )
    )
    assert [type(step) for step in plan_steps(plan)] == [PlannedClose] * 2 + [PlannedInsert] * 3
    (write,) = settled_writes(plan)
    assert write.deferred is None


def _position_write(
    mutation: KeyedMutation,
    valid_from: dt.datetime,
    until: dt.datetime | None,
    **members: object,
) -> PreparedKeyedInstruction:
    prepared = prepare_wire_write(
        KeyedWriteInstruction(mutation, "Position", ({"id": 1, **members},), valid_from, until),
        POSITION,
    )
    assert isinstance(prepared, PreparedKeyedInstruction)
    return prepared


def _opened_rows(steps: Sequence[PlannedStep]) -> list[tuple[object, object, object]]:
    return [
        (cells["validStart"], cells["validEnd"], cells["value"])
        for step in steps
        if isinstance(step, PlannedInsert)
        for entry in step.entries
        for cells in [{ident.name: value for ident, value in entry.row.attributes.items()}]
    ]


def test_a_read_corrects_its_stored_period_beside_an_independent_pending_opening() -> None:
    # Position 1 is stored over [January, June). The attempt read it at March,
    # then inserted an independent [August, December) and, while that insert is
    # pending, corrected March to May through the read and August to September
    # through the insertion. The opening opens its own two pieces; the
    # correction closes the stored rectangle it observed and keeps its source.
    admission = WriteAdmission(
        POSITION, inserted_version=lambda _entity, _from: None, observations={}
    )
    confirm = _unconditioned
    admission.admit(
        admitted_write(
            _position_write("insertUntil", AUG, DEC, acctNum="N", value="300.00"), None, OBJECT
        ),
        confirm_target=confirm,
    )
    source = ReadEvidence(OBJECT.entity, OBJECT, _PARTICIPATION, START)
    admission.admit(
        admitted_write(
            _position_write("amendUntil", MAR, MAY, value="150.00"), START, OBJECT, source=source
        ),
        confirm_target=confirm,
    )
    identity = admission.insertion_identity(OBJECT)
    assert identity is not None
    admission.admit(
        admitted_write(
            _position_write("amendUntil", AUG, SEP, value="350.00"),
            None,
            OBJECT,
            authority=identity,
        ),
        confirm_target=confirm,
    )
    plan = build_write_planner(POSITION).finalize(
        WritePlanningRequest(
            actor_identity=TEST_ACTOR_IDENTITY,
            transaction_instant=instant_at("2024-10-01T00:00:00+00:00"),
            concurrency="optimistic",
            composed_writes=admission.composed_writes(),
            ownership=admission.ownership,
        )
    )
    opening, correction = settled_writes(plan)
    assert (opening.deferred, correction.deferred) == (None, None)
    steps = plan_steps(plan)
    assert [type(step) for step in steps] == [
        *[PlannedInsert] * 2,
        PlannedClose,
        *[PlannedInsert] * 3,
    ]
    assert _opened_rows(steps) == [
        (AUG, SEP, Decimal("350.00")),
        (SEP, DEC, Decimal("300.00")),
        (JAN, MAR, Decimal("100.00")),
        (MAR, MAY, Decimal("150.00")),
        (MAY, JUN, Decimal("100.00")),
    ]
    close = steps[2]
    assert isinstance(close, PlannedClose)
    assert close.cause is SUPERSEDED
    assert tuple(correction.changed) == (START.key,)
    assert not isinstance(opening, SettledWriteWithSource)
    assert isinstance(correction, SettledWriteWithSource)
    assert tuple(map(id, correction.source_evidence)) == (id(source),)


def _unconditioned(item: TargetWrite) -> TargetWrite:
    raise AssertionError(f"no target write is admitted, but {item!r} was")


# --------------------------------------------------------------------------- #
# A destruction superseding an observed run executes where it was authored.    #
# --------------------------------------------------------------------------- #
def _balance_key(balance_id: int) -> ObjectKey:
    return ObjectKey(_ENTITY, (("id", balance_id),))


def _balance_observation(balance_id: int) -> RetainedObservation:
    row = PredecessorRow(
        members={
            "id": balance_id,
            "acctNum": "A",
            "value": Decimal("120.00"),
            "txStart": _MAR,
            "txEnd": INFINITY,
        }
    )
    shape = temporal_read.view(_BALANCE).shape(_ENTITY)
    assert shape is not None
    state = TemporalObjectStateKey(
        _balance_key(balance_id), temporal_read.milestone_edge(shape, row, None)
    )
    return RetainedObservation(state, TemporalObservation(predecessor=row), None)


def _balance(
    mutation: KeyedMutation, balance_id: int, **members: object
) -> PreparedKeyedInstruction:
    prepared = prepare_wire_write(
        KeyedWriteInstruction(mutation, "Balance", ({"id": balance_id, **members},)), _BALANCE
    )
    assert isinstance(prepared, PreparedKeyedInstruction)
    return prepared


def _observed_balance(
    mutation: KeyedMutation, observation: RetainedObservation, **members: object
) -> AdmittedWrite:
    ((_, balance_id),) = observation.key.object.primary_key
    assert isinstance(balance_id, int)
    return admitted_write(
        _balance(mutation, balance_id, **members), observation, observation.key.object
    )


def _closed(plan: WritePlan) -> list[tuple[object, ...]]:
    """The key of each row ``plan`` closes at planning, in execution order."""
    return [step.target.key_values for step in plan_steps(plan) if isinstance(step, PlannedClose)]


def _unconfirmed(item: TargetWrite) -> TargetWrite:
    return item


def _unversioned(entity: EntityIdentity, advanced_from: int | None) -> int | None:
    del entity, advanced_from
    return None


def _admission() -> WriteAdmission:
    return WriteAdmission(_BALANCE, inserted_version=_unversioned, observations={})


def _admitted_plan(admission: WriteAdmission) -> WritePlan:
    return build_write_planner(_BALANCE).finalize(
        WritePlanningRequest(
            actor_identity=TEST_ACTOR_IDENTITY,
            transaction_instant=instant_at("2024-06-01T00:00:00+00:00"),
            concurrency="optimistic",
            composed_writes=admission.composed_writes(),
            ownership=admission.ownership,
        )
    )


def test_a_superseding_destruction_follows_a_same_rank_destruction_authored_before_it() -> None:
    first, other = _balance_observation(1), _balance_observation(3)
    admission = _admission()
    for write in (
        _observed_balance("amend", first, value="150.00"),
        _observed_balance("terminate", other),
        _observed_balance("terminate", first),
    ):
        admission.admit(write, confirm_target=_unconfirmed)
    # Ordering keeps authored order among same-rank deletions, and the run's
    # destruction was authored last.
    assert _closed(_admitted_plan(admission)) == [(3,), (1,)]


def test_a_superseding_destruction_after_a_reinsertion_executes_after_that_reinsertion() -> None:
    admission = _admission()
    stored = _balance_key(2)
    admission.admit(
        admitted_write(_balance("insert", 2, acctNum="A", value="1.00"), None, stored),
        confirm_target=_unconfirmed,
    )
    admission.drain_planned()
    admission.complete(
        WriteEffects(
            opened=Openings(continued=(TemporalRowCoordinates(_ENTITY, (2,), (OPEN_END,)),))
        ),
        (),
        at=1,
    )
    identity = admission.insertion_identity(stored)
    assert identity is not None
    observed = _balance_observation(1)
    for write in (
        _observed_balance("amend", observed, value="150.00"),
        admitted_write(_balance("terminate", 2), None, stored, authority=identity),
        admitted_write(_balance("insert", 2, acctNum="B", value="2.00"), None, stored),
        _observed_balance("terminate", observed),
    ):
        admission.admit(write, confirm_target=_unconfirmed)
    removal, reinsertion, termination = _admitted_plan(admission).entries
    assert isinstance(removal, SettledWrite) and removal.deferred is not None
    assert isinstance(reinsertion, WriteGroup)
    assert [type(step) for step in reinsertion.steps] == [PlannedInsert]
    assert isinstance(termination, WriteGroup)
    assert [
        step.target.key_values for step in termination.steps if isinstance(step, PlannedClose)
    ] == [(1,)]
