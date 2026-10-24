"""The attempt's source authority at its own interface (`m-unit-work`
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
from parallax.core._execution._planning import build_write_planner
from parallax.core._execution._transaction._lifetime import TxnAttemptLifetime
from parallax.core._execution._unit_work.admission import WriteAdmission
from parallax.core._execution._unit_work.instructions import (
    PreparedKeyedInstruction,
    prepare_wire_write,
)
from parallax.core._execution._unit_work.retain import NO_INSERTION_AUTHORITY, InsertionIdentity
from parallax.core._execution._unit_work.source_authority import SourceAuthority
from parallax.core._execution._unit_work.uow import EscapedTransactionError, RollbackOnlyError
from parallax.core._execution._unit_work.write_items import InsertionAuthorizedWrite
from parallax.core.base import INFINITY
from parallax.core.dialect import POSTGRES
from parallax.core.entity._model import model_of
from parallax.core.metamodel import EntityIdentity, EntityMetadata, Metamodel, entity_by_name
from parallax.core.opt_lock import view as opt_lock_view
from parallax.core.temporal_read import Pin, TimeInterval
from parallax.core.unit_work import (
    KeyedWriteInstruction,
    ReadEvidence,
    RetainedObservation,
    TransactionSettings,
    UnitOfWork,
    WriteEvidenceError,
    admitted_write,
)
from parallax.core.write_plan import ObjectKey, VersionObservation
from parallax.core.write_plan.keys import VersionedObjectStateKey
from parallax.core.write_plan.plan import (
    OPEN_BITEMPORAL_ENDS,
    AllocatedOpening,
    Derivation,
    DerivedRow,
    Openings,
    TemporalRowCoordinates,
    WriteEffects,
)
from parallax.core.write_plan.steps import INFINITY as PLANNED_INFINITY
from parallax.core.write_plan.steps import Finite
from tests._support.planner_probes import TEST_ACTOR_IDENTITY
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


def _authority(
    meta: Metamodel,
    *,
    lifetime: TxnAttemptLifetime | None = None,
    version_after: Callable[[EntityIdentity, int | None], int | None] | None = None,
) -> SourceAuthority:
    return SourceAuthority(
        meta,
        lifetime=TxnAttemptLifetime() if lifetime is None else lifetime,
        concurrency="optimistic",
        evidence_policy_for=opt_lock_view(meta).required_key,
        version_after=(lambda _entity, version: 1 if version is None else version + 1)
        if version_after is None
        else version_after,
    )


def _entity(meta: Metamodel, name: str) -> EntityMetadata:
    entity = entity_by_name(meta, f"parallax.compatibility.{name}")
    assert entity is not None
    return entity


def _account(key: int) -> ObjectKey:
    return corpus_object_key("Account", ("id", key))


def _person(key: int) -> ObjectKey:
    return corpus_object_key("Person", ("id", key))


def _versioned(authority: SourceAuthority, key: ObjectKey, version: int) -> RetainedObservation:
    return RetainedObservation(
        VersionedObjectStateKey(key, version),
        VersionObservation(observed_version=version),
        authority.participation,
    )


def _resolved(
    authority: SourceAuthority, meta: Metamodel, source: ReadEvidence | None, key: ObjectKey
) -> object:
    try:
        return authority.resolve_read_evidence(
            _entity(meta, key.entity.name), source, mutation="amend", object_key=key
        )
    except WriteEvidenceError as refused:
        return refused.code


# --------------------------------------------------------------------------- #
# Only the operations that always refused an ended attempt refuse it.         #
# --------------------------------------------------------------------------- #
def _doomed(lifetime: TxnAttemptLifetime) -> None:
    lifetime.doom(RuntimeError("doomed"))


@pytest.mark.parametrize(
    ("end", "refusal"),
    [(TxnAttemptLifetime.close, EscapedTransactionError), (_doomed, RollbackOnlyError)],
    ids=["closed", "doomed"],
)
def test_an_ended_attempt_refuses_what_a_read_or_verb_asks_and_still_publishes_completion(
    end: Callable[[TxnAttemptLifetime], None], refusal: type[Exception]
) -> None:
    lifetime = TxnAttemptLifetime()
    authority = _authority(_PERSON, lifetime=lifetime)
    participation = authority.participation
    evidence = ReadEvidence(_person(1).entity, _person(1), participation, None)
    end(lifetime)
    for asked in (
        lambda: authority.participation,
        lambda: authority.freshness,
        lambda: authority.retain(
            RetainedObservation(VersionedObjectStateKey(_person(1), 1), VersionObservation(1), None)
        ),
        lambda: authority.resolve_read_evidence(
            _entity(_PERSON, "Person"), evidence, mutation="amend", object_key=_person(1)
        ),
        lambda: authority.insertion_authority(InsertionIdentity(_person(1))),
    ):
        with pytest.raises(refusal):
            asked()
    # Publication, the target and binding queries, and completion never refused.
    authority.register_read_evidence(evidence, read_at=0)
    assert not authority.has_live_observation(VersionedObjectStateKey(_person(1), 1))
    assert authority.is_unchanged_since(_person(1), 0)
    authority.complete_write(WriteEffects(changed=(_person(1),)), ())
    assert not authority.is_unchanged_since(_person(1), 0)


# --------------------------------------------------------------------------- #
# One observed state, one live observation.                                   #
# --------------------------------------------------------------------------- #
def test_a_reread_answers_the_live_observation_and_a_stale_read_is_never_indexed() -> None:
    authority = _authority(_ACCOUNT)
    first = authority.retain(_versioned(authority, _account(1), 3))
    assert authority.retain(_versioned(authority, _account(1), 3)) is first
    assert authority.has_live_observation(first.key)
    read_at = authority.freshness
    authority.complete_write(WriteEffects(changed=(first.key,)), ())
    assert first.invalidated
    assert not authority.has_live_observation(first.key)
    # Built from rows read before the change, a reread is stale and not indexed;
    # a fresh read of the state is indexed in the invalidated one's place.
    late = authority.retain(_versioned(authority, _account(1), 3), read_at=read_at)
    assert late.invalidated
    fresh = authority.retain(_versioned(authority, _account(1), 3))
    assert not fresh.invalidated and fresh is not first
    assert authority.retain(_versioned(authority, _account(1), 3)) is fresh


def test_only_an_actual_change_advances_freshness() -> None:
    authority = _authority(_PERSON)
    authority.complete_write(WriteEffects(), ())
    assert authority.freshness == 0
    authority.complete_write(WriteEffects(changed=(_person(1), _person(2))), ())
    assert authority.freshness == 1
    assert not authority.is_unchanged_since(_person(2), 0)
    assert authority.is_unchanged_since(_person(2), 1)
    assert authority.is_unchanged_since(_person(3), 0)


# --------------------------------------------------------------------------- #
# A source resolves once, against this attempt's completed writes.            #
# --------------------------------------------------------------------------- #
def test_a_source_of_another_participation_or_none_is_unavailable() -> None:
    authority = _authority(_PERSON)
    foreign = ReadEvidence(_person(1).entity, _person(1), _authority(_PERSON).participation, None)
    assert _resolved(authority, _PERSON, foreign, _person(1)) == "write-evidence-unavailable"
    assert _resolved(authority, _PERSON, None, _person(1)) == "write-evidence-unavailable"
    own = ReadEvidence(_person(1).entity, _person(1), authority.participation, None)
    assert _resolved(authority, _PERSON, own, _person(1)) == _person(1)


def test_an_optimistic_source_without_an_observation_is_unavailable() -> None:
    authority = _authority(_ACCOUNT)
    evidence = ReadEvidence(_account(1).entity, _account(1), authority.participation, None)
    assert _resolved(authority, _ACCOUNT, evidence, _account(1)) == "write-evidence-unavailable"


def test_a_versioned_source_continues_from_the_version_completion_produced_once() -> None:
    produced: list[int | None] = []

    def version_after(entity: EntityIdentity, version: int | None) -> int | None:
        del entity
        produced.append(version)
        return 1 if version is None else version + 1

    authority = _authority(_ACCOUNT, version_after=version_after)
    observation = authority.retain(_versioned(authority, _account(1), 4))
    source = ReadEvidence(_account(1).entity, _account(1), authority.participation, observation)
    assert _resolved(authority, _ACCOUNT, source, _account(1)) == observation.key
    state = VersionedObjectStateKey(_account(1), 4)
    authority.complete_write(WriteEffects(changed=(state,), advanced=(state,)), ())
    assert produced == [4]
    assert _resolved(authority, _ACCOUNT, source, _account(1)) == VersionedObjectStateKey(
        _account(1), 5
    )
    authority.complete_write(WriteEffects(changed=(_account(1),), destroyed=(_account(1),)), ())
    assert _resolved(authority, _ACCOUNT, source, _account(1)) == "write-evidence-consumed"


def _temporal_source(authority: SourceAuthority, valid_time: dt.datetime) -> ReadEvidence:
    observation = authority.retain(retained(rectangle(JAN, INFINITY, "100.00")))
    return ReadEvidence(
        ENTITY, OBJECT, authority.participation, observation, Pin(valid_time=valid_time)
    )


def test_a_temporal_source_continues_only_at_a_pin_its_changed_state_still_holds() -> None:
    authority = _authority(POSITION)
    kept, lost = _temporal_source(authority, JAN), _temporal_source(authority, MAR)
    assert kept.observation is lost.observation
    observation = kept.observation
    assert observation is not None
    assert _resolved(authority, POSITION, lost, OBJECT) is observation
    head = TemporalRowCoordinates(ENTITY, (1,), (Finite(instant=_FEB), PLANNED_INFINITY))
    # Terminated from February on: the part before it survives.
    authority.complete_write(
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
        (),
    )
    assert observation.invalidated
    assert _resolved(authority, POSITION, kept, OBJECT) is observation
    assert _resolved(authority, POSITION, lost, OBJECT) == "write-evidence-consumed"


def test_a_stale_temporal_source_no_completion_recorded_reaches_nothing() -> None:
    authority = _authority(POSITION)
    stale = retained(rectangle(JAN, INFINITY, "100.00"))
    stale.invalidate()
    source = ReadEvidence(ENTITY, OBJECT, authority.participation, stale, Pin(valid_time=JAN))
    assert _resolved(authority, POSITION, source, OBJECT) == "write-evidence-consumed"


# --------------------------------------------------------------------------- #
# Completion, planning views, and the insertion transitions.                  #
# --------------------------------------------------------------------------- #
def test_completion_owns_the_rows_it_opened_under_the_keys_the_database_allocated() -> None:
    authority = _authority(POSITION)
    opening = AllocatedOpening(ENTITY, OPEN_BITEMPORAL_ENDS)
    authority.complete_write(WriteEffects(opened=Openings(allocated=(opening,))), (42,))
    live = authority.planning_ownership(concluding=False)
    assert live.owns(TemporalRowCoordinates(ENTITY, (42,), OPEN_BITEMPORAL_ENDS))


def test_a_flush_borrows_one_live_ownership_or_one_reusable_concluding_view_of_it() -> None:
    authority = _authority(POSITION)
    live = authority.planning_ownership(concluding=False)
    concluding = authority.planning_ownership(concluding=True)
    assert authority.planning_ownership(concluding=False) is live
    assert authority.planning_ownership(concluding=True) is concluding
    observation = authority.retain(retained(rectangle(JAN, INFINITY, "100.00")))
    assert live.demanded(observation.key, None)
    assert not concluding.demanded(observation.key, None)
    # The view is no snapshot: what completes later is what it answers.
    row = TemporalRowCoordinates(ENTITY, (1,), OPEN_BITEMPORAL_ENDS)
    authority.complete_write(WriteEffects(opened=Openings(fresh=(row,))), ())
    assert concluding.owns(row)


def _position_insert() -> PreparedKeyedInstruction:
    prepared = prepare_wire_write(
        KeyedWriteInstruction(
            "insert", "Position", ({"id": 1, "acctNum": "A", "value": "1.00"},), JAN
        ),
        POSITION,
    )
    assert isinstance(prepared, PreparedKeyedInstruction)
    return prepared


def test_an_insertion_stands_until_a_completed_removal_of_its_rows_and_its_history_stays() -> None:
    authority = _authority(POSITION)
    admission = WriteAdmission(POSITION, authority=authority)
    identity = admission.admit_insert(
        admitted_write(_position_insert(), None, OBJECT), insertion_advice=None
    )
    assert identity is not None
    assert authority.insertion_authority(identity) == TimeInterval(JAN, INFINITY)
    admission.drain_planned()
    row = TemporalRowCoordinates(ENTITY, (1,), OPEN_BITEMPORAL_ENDS)
    authority.complete_write(WriteEffects(opened=Openings(continued=(row,))), ())
    termination = prepare_wire_write(
        KeyedWriteInstruction("terminate", "Position", ({"id": 1},), JAN), POSITION
    )
    assert isinstance(termination, PreparedKeyedInstruction)
    write = authority.resolve_insertion_authorized_write(
        InsertionAuthorizedWrite(termination, OBJECT, identity)
    )
    assert write.claim_scope is None  # a temporal write claims by object instead
    authority.complete_write(WriteEffects(removed=(row,)), ())
    assert authority.insertion_authority(identity) is NO_INSERTION_AUTHORITY
    assert authority.has_admitted_insertion(OBJECT)


# --------------------------------------------------------------------------- #
# Clearing forgets the attempt's facts, never its identity or its count.      #
# --------------------------------------------------------------------------- #
def test_clearing_forgets_every_fact_but_keeps_participation_and_freshness() -> None:
    authority = _authority(_PERSON)
    participation = authority.participation
    read_at = authority.freshness
    stale = ReadEvidence(_person(1).entity, _person(1), participation, None)
    authority.complete_write(WriteEffects(changed=(_person(1),), destroyed=(_person(1),)), ())
    authority.register_read_evidence(stale, read_at=read_at)
    insert = prepare_wire_write(
        KeyedWriteInstruction("insert", "Person", ({"id": 9, "name": "Ada"},)), _PERSON
    )
    assert isinstance(insert, PreparedKeyedInstruction)
    identity = WriteAdmission(_PERSON, authority=authority).admit_insert(
        admitted_write(insert, None, _person(9)), insertion_advice=None
    )
    assert identity is not None
    assert _resolved(authority, _PERSON, stale, _person(1)) == "write-evidence-consumed"
    authority.clear()
    assert authority.participation is participation
    assert authority.freshness == 1
    assert authority.is_unchanged_since(_person(1), 0)
    assert _resolved(authority, _PERSON, stale, _person(1)) == _person(1)
    assert authority.insertion_authority(identity) is NO_INSERTION_AUTHORITY
    assert not authority.has_admitted_insertion(_person(9))


def test_a_unit_of_works_authority_holds_nothing_of_its_shell_or_execution() -> None:
    planner = build_write_planner(_ACCOUNT)
    simulated = SimulatedWriteSteps(planner.payloads, _ACCOUNT, POSTGRES)
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
        evidence_policy_for=opt_lock_view(_ACCOUNT).required_key,
    )
    authority = uow.source_authority
    authority.retain(_versioned(authority, _account(1), 1))
    reached = reachable_objects(authority)
    shell = (uow, simulated, uow.acquire_rows, uow.clock)
    assert not any(held is part for held in reached for part in shell)
    assert not any(isinstance(held, UnitOfWork | WriteAdmission) for held in reached)
