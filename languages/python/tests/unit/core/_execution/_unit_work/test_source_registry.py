"""The attempt's source registry at its own interface (`m-unit-work`
*Observation ownership and lifetime*, *Insertion authority*): which of its
operations an ended attempt refuses, how it interns observations, what it
resolves a source to, what one completion publishes, which ownership view a
flush plans under, and what clearing forgets. Reads, buffering, and
execution reaching it through their own seams are the unit-of-work suites'.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable

import pytest

from parallax.conformance._simulated_write_steps import SimulatedWriteSteps
from parallax.conformance.class_models import MODELS as CLASS_MODELS
from parallax.conformance.scripted_clock import FixedClock
from parallax.core import UsageError
from parallax.core._execution._planning import build_write_planner
from parallax.core._execution._transaction._lifetime import (
    TRANSACTION_ESCAPED,
    TRANSACTION_ROLLBACK_ONLY,
    TxnAttemptLifetime,
)
from parallax.core._execution._unit_work._write_ownership import NO_INSERTION_AUTHORITY
from parallax.core._execution._unit_work.admission import WriteAdmission
from parallax.core._execution._unit_work.evidence import InsertionIdentity
from parallax.core._execution._unit_work.instructions import (
    PreparedKeyedInstruction,
)
from parallax.core._execution._unit_work.preparation import WIRE
from parallax.core._execution._unit_work.source_registry import SourceRegistry
from parallax.core.internal.base import INFINITY
from parallax.core.internal.dialect import POSTGRES
from parallax.core.internal.entity._model import model_of
from parallax.core.internal.metamodel import CompiledEntity, Metamodel, entity_by_name
from parallax.core.internal.planned_step import ObjectKey, VersionObservation
from parallax.core.internal.planned_step.keys import VersionedObjectStateKey
from parallax.core.internal.planned_step.steps import INFINITY as PLANNED_INFINITY
from parallax.core.internal.planned_step.steps import Finite
from parallax.core.internal.planned_step.write_effects import (
    OPEN_BITEMPORAL_ENDS,
    Derivation,
    DerivedRow,
    Openings,
    TemporalRowCoordinates,
    WriteEffects,
)
from parallax.core.internal.temporal_read import Pin, TimeInterval
from parallax.core.internal.unit_work import (
    KeyedWriteInstruction,
    ReadEvidence,
    RetainedObservation,
    TransactionSettings,
    UnitOfWork,
    admitted_write,
)
from tests._support.bindings import bound_model
from tests._support.errors import raises_code
from tests._support.planner_probes import TEST_ACTOR_IDENTITY
from tests._support.write_preparation import prepare_instruction, write_preparation_of
from tests.unit._corpus_identity_support import corpus_object_key
from tests.unit._corpus_model_support import corpus_records, formed
from tests.unit._gc_reachability import reachable_objects
from tests.unit.core._execution._unit_work._acquired_rows_support import HeldRows
from tests.unit.core._execution._unit_work._temporal_targets_support import (
    ENTITY,
    JAN,
    MAR,
    OBJECT,
    POSITION,
    rectangle,
    retained,
)

_ACCOUNT = formed(corpus_records()["account"])
_PERSON = model_of(CLASS_MODELS["person"])
_FEB = dt.datetime(2024, 2, 1, tzinfo=dt.UTC)


def _registry(
    meta: Metamodel,
    *,
    lifetime: TxnAttemptLifetime | None = None,
) -> SourceRegistry:
    return SourceRegistry(
        meta,
        lifetime=TxnAttemptLifetime() if lifetime is None else lifetime,
        preference="optimistic",
    )


def _entity(meta: Metamodel, name: str) -> CompiledEntity:
    entity = entity_by_name(meta, f"parallax.compatibility.{name}")
    assert entity is not None
    return entity


def _account(key: int) -> ObjectKey:
    return corpus_object_key("Account", ("id", key))


def _person(key: int) -> ObjectKey:
    return corpus_object_key("Person", ("id", key))


def _versioned(registry: SourceRegistry, key: ObjectKey, version: int) -> RetainedObservation:
    return RetainedObservation(
        VersionedObjectStateKey(key, version),
        VersionObservation(observed_version=version),
        registry.participation,
    )


def _resolved(
    registry: SourceRegistry, meta: Metamodel, source: ReadEvidence | None, key: ObjectKey
) -> object:
    try:
        return registry.resolve_read_evidence(
            _entity(meta, key.entity.name), source, mutation="amend", object_key=key
        )
    except UsageError as refused:
        return refused.code


# --------------------------------------------------------------------------- #
# Only these operations refuse an ended attempt.                              #
# --------------------------------------------------------------------------- #
def _doomed(lifetime: TxnAttemptLifetime) -> None:
    lifetime.doom(RuntimeError("doomed"))


@pytest.mark.parametrize(
    ("end", "refusal"),
    [(TxnAttemptLifetime.close, TRANSACTION_ESCAPED), (_doomed, TRANSACTION_ROLLBACK_ONLY)],
    ids=["closed", "doomed"],
)
def test_an_ended_attempt_refuses_what_a_read_or_verb_asks_and_still_publishes_completion(
    end: Callable[[TxnAttemptLifetime], None], refusal: str
) -> None:
    lifetime = TxnAttemptLifetime()
    registry = _registry(_PERSON, lifetime=lifetime)
    participation = registry.participation
    evidence = ReadEvidence(_person(1).entity, _person(1), participation, None)
    end(lifetime)
    for asked in (
        lambda: registry.participation,
        lambda: registry.freshness,
        lambda: registry.retain(
            RetainedObservation(VersionedObjectStateKey(_person(1), 1), VersionObservation(1), None)
        ),
        lambda: registry.resolve_read_evidence(
            _entity(_PERSON, "Person"), evidence, mutation="amend", object_key=_person(1)
        ),
        lambda: registry.insertion_anchor(InsertionIdentity(_person(1))),
    ):
        with raises_code(UsageError, refusal):
            asked()
    # Publication, the target and binding queries, and completion do not refuse.
    registry.register_read_evidence(evidence, read_at=0)
    assert not registry.has_live_observation(VersionedObjectStateKey(_person(1), 1))
    assert registry.is_unchanged_since(_person(1), 0)
    registry.complete_write(WriteEffects(changed=(_person(1),)))
    assert not registry.is_unchanged_since(_person(1), 0)


# --------------------------------------------------------------------------- #
# One observed state, one live observation.                                   #
# --------------------------------------------------------------------------- #
def test_a_reread_answers_the_live_observation_and_a_stale_read_is_never_indexed() -> None:
    registry = _registry(_ACCOUNT)
    first = registry.retain(_versioned(registry, _account(1), 3))
    assert registry.retain(_versioned(registry, _account(1), 3)) is first
    assert registry.has_live_observation(first.key)
    read_at = registry.freshness
    registry.complete_write(WriteEffects(changed=(first.key,)))
    assert first.invalidated
    assert not registry.has_live_observation(first.key)
    # Built from rows read before the change, a reread is stale and not indexed;
    # a fresh read of the state is indexed in the invalidated one's place.
    late = registry.retain(_versioned(registry, _account(1), 3), read_at=read_at)
    assert late.invalidated
    fresh = registry.retain(_versioned(registry, _account(1), 3))
    assert not fresh.invalidated and fresh is not first
    assert registry.retain(_versioned(registry, _account(1), 3)) is fresh


def test_only_an_actual_change_advances_freshness() -> None:
    registry = _registry(_PERSON)
    registry.complete_write(WriteEffects())
    assert registry.freshness == 0
    registry.complete_write(WriteEffects(changed=(_person(1), _person(2))))
    assert registry.freshness == 1
    assert not registry.is_unchanged_since(_person(2), 0)
    assert registry.is_unchanged_since(_person(2), 1)
    assert registry.is_unchanged_since(_person(3), 0)


# --------------------------------------------------------------------------- #
# A source resolves once, against this attempt's completed writes.            #
# --------------------------------------------------------------------------- #
def test_a_source_of_another_participation_or_none_is_unavailable() -> None:
    registry = _registry(_PERSON)
    foreign = ReadEvidence(_person(1).entity, _person(1), _registry(_PERSON).participation, None)
    assert _resolved(registry, _PERSON, foreign, _person(1)) == "write-evidence-unavailable"
    assert _resolved(registry, _PERSON, None, _person(1)) == "write-evidence-unavailable"
    own = ReadEvidence(_person(1).entity, _person(1), registry.participation, None)
    assert _resolved(registry, _PERSON, own, _person(1)) == _person(1)


def test_an_optimistic_source_without_an_observation_is_unavailable() -> None:
    registry = _registry(_ACCOUNT)
    evidence = ReadEvidence(_account(1).entity, _account(1), registry.participation, None)
    assert _resolved(registry, _ACCOUNT, evidence, _account(1)) == "write-evidence-unavailable"


def _temporal_source(registry: SourceRegistry, valid_time: dt.datetime) -> ReadEvidence:
    observation = registry.retain(retained(rectangle(JAN, INFINITY, "100.00")))
    return ReadEvidence(
        ENTITY, OBJECT, registry.participation, observation, Pin(valid_time=valid_time)
    )


def test_a_temporal_source_continues_only_at_a_pin_its_changed_state_still_holds() -> None:
    registry = _registry(POSITION)
    kept, lost = _temporal_source(registry, JAN), _temporal_source(registry, MAR)
    assert kept.observation is lost.observation
    observation = kept.observation
    assert observation is not None
    assert _resolved(registry, POSITION, lost, OBJECT) is observation
    head = TemporalRowCoordinates(ENTITY, (1,), (Finite(instant=_FEB), PLANNED_INFINITY))
    # Terminated from February on: the part before it survives.
    registry.complete_write(
        WriteEffects(
            changed=(observation.key,),
            opened=Openings(fresh=(head,)),
            derived=(
                Derivation(
                    observation.key,
                    TimeInterval(JAN, INFINITY),
                    None,
                    (DerivedRow(head, TimeInterval(JAN, _FEB), TimeInterval(JAN, _FEB)),),
                ),
            ),
        ),
    )
    assert observation.invalidated
    assert _resolved(registry, POSITION, kept, OBJECT) is observation
    assert _resolved(registry, POSITION, lost, OBJECT) == "write-evidence-consumed"


def test_a_stale_temporal_source_no_completion_recorded_reaches_nothing() -> None:
    registry = _registry(POSITION)
    stale = retained(rectangle(JAN, INFINITY, "100.00"))
    stale.invalidate()
    source = ReadEvidence(ENTITY, OBJECT, registry.participation, stale, Pin(valid_time=JAN))
    assert _resolved(registry, POSITION, source, OBJECT) == "write-evidence-consumed"


# --------------------------------------------------------------------------- #
# Completion, planning views, and the insertion transitions.                  #
# --------------------------------------------------------------------------- #
def test_a_flush_borrows_one_live_ownership_or_one_reusable_concluding_view_of_it() -> None:
    registry = _registry(POSITION)
    live = registry.planning_ownership(concluding=False)
    concluding = registry.planning_ownership(concluding=True)
    assert registry.planning_ownership(concluding=False) is live
    assert registry.planning_ownership(concluding=True) is concluding
    observation = registry.retain(retained(rectangle(JAN, INFINITY, "100.00")))
    assert live.demanded(observation.key, None)
    assert not concluding.demanded(observation.key, None)
    # The view is no snapshot: what completes later is what it answers.
    row = TemporalRowCoordinates(ENTITY, (1,), OPEN_BITEMPORAL_ENDS)
    registry.complete_write(WriteEffects(opened=Openings(fresh=(row,))))
    assert concluding.owns(row)


def _position_insert() -> PreparedKeyedInstruction:
    prepared = prepare_instruction(
        KeyedWriteInstruction(
            "insert", "Position", {"id": 1, "acctNum": "A", "value": "1.00"}, JAN
        ),
        write_preparation_of(POSITION),
        WIRE,
    )
    assert isinstance(prepared, PreparedKeyedInstruction)
    return prepared


def test_an_insertion_stands_until_a_completed_removal_of_its_rows_and_its_history_stays() -> None:
    registry = _registry(POSITION)
    admission = WriteAdmission(POSITION, registry=registry)
    identity = admission.admit_insert(
        admitted_write(_position_insert(), None, OBJECT), insertion_advice=None
    )
    assert identity is not None
    assert registry.insertion_anchor(identity) == TimeInterval(JAN, INFINITY)
    admission.drain_planned()
    row = TemporalRowCoordinates(ENTITY, (1,), OPEN_BITEMPORAL_ENDS)
    registry.complete_write(WriteEffects(opened=Openings(continued=(row,))))
    termination = prepare_instruction(
        KeyedWriteInstruction("terminate", "Position", {"id": 1}, JAN),
        write_preparation_of(POSITION),
        WIRE,
    )
    assert isinstance(termination, PreparedKeyedInstruction)
    write = registry.resolve_insertion_authorized_write(
        admitted_write(termination, None, OBJECT, insertion=identity)
    )
    assert write.claim_scope is None  # a temporal write claims by object instead
    registry.complete_write(WriteEffects(removed=(row,)))
    assert registry.insertion_anchor(identity) is NO_INSERTION_AUTHORITY
    assert registry.has_admitted_insertion(OBJECT)


# --------------------------------------------------------------------------- #
# Clearing forgets the attempt's facts, never its identity or its count.      #
# --------------------------------------------------------------------------- #
def test_clearing_forgets_every_fact_but_keeps_participation_and_freshness() -> None:
    registry = _registry(_PERSON)
    participation = registry.participation
    read_at = registry.freshness
    stale = ReadEvidence(_person(1).entity, _person(1), participation, None)
    registry.complete_write(WriteEffects(changed=(_person(1),), destroyed=(_person(1),)))
    registry.register_read_evidence(stale, read_at=read_at)
    insert = prepare_instruction(
        KeyedWriteInstruction("insert", "Person", {"id": 9, "name": "Ada"}),
        write_preparation_of(_PERSON),
        WIRE,
    )
    assert isinstance(insert, PreparedKeyedInstruction)
    identity = WriteAdmission(_PERSON, registry=registry).admit_insert(
        admitted_write(insert, None, _person(9)), insertion_advice=None
    )
    assert identity is not None
    assert _resolved(registry, _PERSON, stale, _person(1)) == "write-evidence-consumed"
    registry.clear()
    assert registry.participation is participation
    assert registry.freshness == 1
    assert registry.is_unchanged_since(_person(1), 0)
    assert _resolved(registry, _PERSON, stale, _person(1)) == _person(1)
    assert registry.insertion_anchor(identity) is NO_INSERTION_AUTHORITY
    assert not registry.has_admitted_insertion(_person(9))


def test_a_unit_of_works_registry_holds_nothing_of_its_shell_or_execution() -> None:
    planner = build_write_planner(bound_model(_ACCOUNT))
    simulated = SimulatedWriteSteps(planner.payloads, bound_model(_ACCOUNT), POSTGRES)
    uow = UnitOfWork(
        settings=TransactionSettings(),
        lifetime=TxnAttemptLifetime(),
        clock=FixedClock(_FEB),
        meta=_ACCOUNT,
        execute_write_steps=simulated,
        execute_counted_step=simulated.counted,
        acquire_rows=HeldRows(_ACCOUNT),
        planner=planner,
        actor_identity=TEST_ACTOR_IDENTITY,
    )
    registry = uow.source_registry
    registry.retain(_versioned(registry, _account(1), 1))
    reached = reachable_objects(registry)
    shell = (uow, simulated, uow.acquire_rows, uow.clock)
    assert not any(held is part for held in reached for part in shell)
    assert not any(isinstance(held, UnitOfWork | WriteAdmission) for held in reached)
