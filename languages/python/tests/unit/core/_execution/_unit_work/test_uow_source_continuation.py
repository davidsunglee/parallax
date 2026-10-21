"""A Non-Temporal source's authority across this attempt's own completed writes,
at the unit-of-work seam (`m-unit-work` *Observation ownership and lifetime*).

Each case publishes Read Evidence as a read's retention does — registered with
the freshness its read captured — resolves it as a keyed verb does, and buffers
the write it licenses, over simulated step execution. What it grades is which
state each source reaches after a flush, which sources a completed write
leaves stale or ends, and how long the attempt keeps any of that: exactly as
long as a value or a pending or planned write reaches the evidence.
"""

from __future__ import annotations

import datetime as dt
import gc
import weakref
from collections.abc import Callable
from decimal import Decimal
from typing import Any

import pytest

from parallax.conformance._simulated_write_steps import SimulatedWriteSteps
from parallax.conformance.class_models import MODELS as CLASS_MODELS
from parallax.conformance.scripted_clock import FixedClock
from parallax.core import opt_lock
from parallax.core import predicate as predicate_algebra
from parallax.core._execution._planning import build_write_planner
from parallax.core._execution._transaction._lifetime import TxnAttemptLifetime
from parallax.core._execution._unit_work._write_ownership import (
    SourceRefusal,
    _ReadRegistration,  # pyright: ignore[reportPrivateUsage] - what a reachability count names
)
from parallax.core._execution._unit_work.instructions import (
    KeyedMutation,
    PredicateSelection,
    PredicateWriteInstruction,
    PreparedKeyedWrite,
    PreparedPredicateWrite,
    WriteAssignment,
    prepare_typed_write,
)
from parallax.core._execution._unit_work.write_items import ObservedKeyedWrite
from parallax.core.dialect import POSTGRES
from parallax.core.entity._model import model_of
from parallax.core.metamodel import EntityMetadata, Metamodel, entity_by_name
from parallax.core.unit_work import (
    KeyedWriteInstruction,
    ReadEvidence,
    RetainedObservation,
    RollbackOnlyError,
    TransactionSettings,
    UnitOfWork,
    WriteEvidenceError,
    buffered_write,
)
from parallax.core.write_plan import ObjectKey, VersionObservation
from parallax.core.write_plan.keys import VersionedObjectStateKey
from tests._support.planner_probes import TEST_ACTOR_IDENTITY
from tests.unit._corpus_identity_support import corpus_object_key
from tests.unit._corpus_model_support import corpus_records, formed
from tests.unit._gc_reachability import reachable_objects
from tests.unit.core._execution._unit_work._acquired_rows_support import HeldRows
from tests.unit.core._execution._unit_work._flush_support import ObservedSteps, statement_kinds

_ACCOUNT = formed(corpus_records()["account"])
_PERSON = model_of(CLASS_MODELS["person"])
_PAYMENT = model_of(CLASS_MODELS["payment"])


def _uow(
    meta: Metamodel,
    steps: Callable[..., tuple[object, ...]] | None = None,
    *,
    settings: TransactionSettings | None = None,
) -> tuple[UnitOfWork, SimulatedWriteSteps]:
    simulated = SimulatedWriteSteps(build_write_planner(meta).payloads, meta, POSTGRES)
    uow = UnitOfWork(
        settings=TransactionSettings() if settings is None else settings,
        lifetime=TxnAttemptLifetime(),
        clock=FixedClock(dt.datetime(2024, 6, 1, tzinfo=dt.UTC)),
        meta=meta,
        execute_write_steps=simulated if steps is None else steps,
        acquire_rows=HeldRows(meta),
        planner=build_write_planner(meta),
        actor_identity=TEST_ACTOR_IDENTITY,
        evidence_policy_for=opt_lock.view(meta).required_key,
    )
    return uow, simulated


def _entity(meta: Metamodel, name: str) -> EntityMetadata:
    entity = entity_by_name(meta, f"parallax.compatibility.{name}")
    assert entity is not None
    return entity


def _published(
    uow: UnitOfWork, key: ObjectKey, *, version: int | None = None, read_at: int | None = None
) -> ReadEvidence:
    """Evidence of ``key`` as a read capturing ``read_at`` publishes it: at its
    observed ``version``, or observation-free."""
    stamp = uow.freshness if read_at is None else read_at
    observation = None
    if version is not None:
        observation = uow.retain(
            RetainedObservation(
                VersionedObjectStateKey(key, version),
                VersionObservation(observed_version=version),
                uow.participation,
            ),
            read_at=stamp,
        )
    evidence = ReadEvidence(key.entity, key, uow.participation, observation)
    uow.register_read_evidence(evidence, read_at=stamp)
    return evidence


def _write(
    uow: UnitOfWork,
    meta: Metamodel,
    source: ReadEvidence,
    mutation: KeyedMutation,
    **members: object,
) -> None:
    entity = _entity(meta, source.entity.name)
    key = source.object_key
    instruction = prepare_typed_write(
        KeyedWriteInstruction(
            mutation, entity.identity.name, ({**dict(key.primary_key), **members},)
        ),
        meta,
    )
    assert isinstance(instruction, PreparedKeyedWrite)
    settled = uow.resolve_read_evidence(entity, source, mutation=mutation, object_key=key)
    uow.buffer(buffered_write(instruction, settled, source=source))


def _refusal(write: Callable[[], None]) -> str:
    with pytest.raises(WriteEvidenceError) as refused:
        write()
    return refused.value.code


def _flush(uow: UnitOfWork) -> None:
    uow.read(lambda: None)


def _registrations(uow: UnitOfWork) -> int:
    gc.collect()
    return sum(isinstance(held, _ReadRegistration) for held in reachable_objects(uow))


def _account(key: int) -> ObjectKey:
    return corpus_object_key("Account", ("id", key))


def _person(key: int) -> ObjectKey:
    return corpus_object_key("Person", ("id", key))


# --------------------------------------------------------------------------- #
# Versioned sources continue at the version an own completed update produced. #
# --------------------------------------------------------------------------- #
def test_a_versioned_source_settles_against_the_version_its_completed_write_produced() -> None:
    uow, simulated = _uow(_ACCOUNT)
    source = _published(uow, _account(1), version=4)
    _write(uow, _ACCOUNT, source, "amend", owner="Ada")
    _flush(uow)
    assert uow.resolve_read_evidence(
        _entity(_ACCOUNT, "Account"), source, mutation="amend", object_key=_account(1)
    ) == VersionedObjectStateKey(_account(1), 5)
    _write(uow, _ACCOUNT, source, "amend", owner="Bo")
    uow.flush(trigger="pre_commit")
    assert [statement.binds[1:] for statement in simulated.statements] == [
        (5, 1, 4),
        (6, 1, 5),
    ]


def test_an_old_and_a_fresh_source_of_one_produced_version_share_one_claim() -> None:
    uow, simulated = _uow(_ACCOUNT)
    old = _published(uow, _account(1), version=1)
    _write(uow, _ACCOUNT, old, "amend", owner="Ada")
    _flush(uow)
    fresh = _published(uow, _account(1), version=2)
    _write(uow, _ACCOUNT, old, "amend", owner="Bo")
    _write(uow, _ACCOUNT, fresh, "amend", balance=Decimal("9.00"))
    composed = uow._admission.composed_writes()  # pyright: ignore[reportPrivateUsage] - the buffer the two writes coalesced into
    (merged,) = composed
    assert isinstance(merged, ObservedKeyedWrite)
    assert merged.scope == VersionedObjectStateKey(_account(1), 2)
    assert merged.retained_observation is not fresh.observation
    assert merged.source_evidence == (old, fresh)
    # A destruction through either source now refuses the other's assignment.
    _write(uow, _ACCOUNT, fresh, "delete")
    assert _refusal(lambda: _write(uow, _ACCOUNT, old, "amend", owner="Cy")) == (
        "write-evidence-already-claimed"
    )
    uow.flush(trigger="pre_commit")
    assert statement_kinds(simulated.statements) == ["update", "delete"]


def test_a_versioned_source_read_before_its_states_completed_change_is_stale() -> None:
    uow, _simulated = _uow(_ACCOUNT)
    read_at = uow.freshness
    source = _published(uow, _account(1), version=1)
    _write(uow, _ACCOUNT, source, "amend", owner="Ada")
    _flush(uow)
    late = _published(uow, _account(1), version=1, read_at=read_at)
    assert _refusal(lambda: _write(uow, _ACCOUNT, late, "amend", owner="Bo")) == (
        "write-evidence-consumed"
    )
    _write(uow, _ACCOUNT, source, "amend", owner="Cy")


def test_a_locking_versioned_source_carrying_no_observation_settles_against_nothing() -> None:
    # Locking needs no observation to admit the source, and the planner's
    # required-observation rule refuses the write it would settle.
    uow, _simulated = _uow(_ACCOUNT, settings=TransactionSettings(concurrency="locking"))
    evidence = ReadEvidence(_account(1).entity, _account(1), uow.participation, None)
    account = _entity(_ACCOUNT, "Account")
    assert (
        uow.resolve_read_evidence(account, evidence, mutation="amend", object_key=_account(1))
        is None
    )


def test_two_writes_one_insertion_authorized_coalesce_into_one() -> None:
    uow, simulated = _uow(_PERSON)
    insertion = prepare_typed_write(
        KeyedWriteInstruction("insert", "Person", ({"id": 5, "name": "New"},)), _PERSON
    )
    assert isinstance(insertion, PreparedKeyedWrite)
    uow.buffer(insertion)
    _flush(uow)
    identity = uow.insertion_identity(_person(5))
    assert identity is not None
    for name in ("First", "Second"):
        amendment = prepare_typed_write(
            KeyedWriteInstruction("amend", "Person", ({"id": 5, "name": name},)), _PERSON
        )
        assert isinstance(amendment, PreparedKeyedWrite)
        uow.buffer(buffered_write(amendment, None, authority=identity))
    uow.flush(trigger="pre_commit")
    assert [statement.binds for statement in simulated.statements][1:] == [("Second", 5)]


# --------------------------------------------------------------------------- #
# Unversioned sources: lock authority continues; publication freshness holds. #
# --------------------------------------------------------------------------- #
def test_an_unversioned_source_published_from_rows_read_before_a_keyed_update_is_stale() -> None:
    uow, simulated = _uow(_PERSON)
    read_at = uow.freshness
    earlier = _published(uow, _person(1))
    _write(uow, _PERSON, earlier, "amend", name="Ada")
    _flush(uow)
    delayed = _published(uow, _person(1), read_at=read_at)
    assert _refusal(lambda: _write(uow, _PERSON, delayed, "amend", name="Bo")) == (
        "write-evidence-consumed"
    )
    fresh = _published(uow, _person(1))
    _write(uow, _PERSON, earlier, "amend", name="Cy")
    _write(uow, _PERSON, fresh, "amend", name="Di")
    uow.flush(trigger="pre_commit")
    assert [statement.binds for statement in simulated.statements] == [("Ada", 1), ("Di", 1)]


def test_a_page_read_before_a_deletion_stays_stale_after_its_demand_and_a_reinsertion() -> None:
    uow, _simulated = _uow(_PERSON)
    read_at = uow.freshness
    deleted = _published(uow, _person(1))
    _write(uow, _PERSON, deleted, "delete")
    _flush(uow)
    held = weakref.ref(deleted)
    del deleted
    gc.collect()
    assert held() is None
    insertion = prepare_typed_write(
        KeyedWriteInstruction("insert", "Person", ({"id": 1, "name": "New"},)), _PERSON
    )
    assert isinstance(insertion, PreparedKeyedWrite)
    uow.buffer(insertion)
    _flush(uow)
    delayed = _published(uow, _person(1), read_at=read_at)
    assert _refusal(lambda: _write(uow, _PERSON, delayed, "amend", name="Bo")) == (
        "write-evidence-consumed"
    )
    _write(uow, _PERSON, _published(uow, _person(1)), "amend", name="Fresh")


def test_every_key_a_collapsed_deletion_batch_removes_ends_its_sources() -> None:
    uow, simulated = _uow(_PERSON)
    read_at = uow.freshness
    sources = [_published(uow, _person(key)) for key in (1, 2)]
    for source in sources:
        _write(uow, _PERSON, source, "delete")
    _flush(uow)
    assert statement_kinds(simulated.statements) == ["delete"]
    for key, source in zip((1, 2), sources, strict=True):
        assert _refusal(lambda source=source: _write(uow, _PERSON, source, "amend", name="X")) == (
            "write-evidence-consumed"
        )
        delayed = _published(uow, _person(key), read_at=read_at)
        assert _refusal(
            lambda delayed=delayed: _write(uow, _PERSON, delayed, "amend", name="Y")
        ) == ("write-evidence-consumed")


def test_a_subtypes_completed_write_changes_its_concrete_entitys_object() -> None:
    uow, _simulated = _uow(_PAYMENT)
    card = corpus_object_key("CardPayment", ("id", 1))
    root = corpus_object_key("Payment", ("id", 1))
    read_at = uow.freshness
    _write(uow, _PAYMENT, _published(uow, card), "amend", amount=Decimal("2.00"))
    _flush(uow)
    assert uow._admission.resolve_source(_published(uow, card, read_at=read_at)) is (  # pyright: ignore[reportPrivateUsage] - the registration the delayed publication made
        SourceRefusal.STALE
    )
    assert uow._admission.resolve_source(_published(uow, root, read_at=read_at)) == root  # pyright: ignore[reportPrivateUsage] - the family root names another object


def test_a_readless_write_neither_ends_nor_stales_a_source() -> None:
    uow, _simulated = _uow(_PERSON)
    read_at = uow.freshness
    source = _published(uow, _person(1))
    predicate = prepare_typed_write(
        PredicateWriteInstruction(
            "amend",
            PredicateSelection(
                "Person",
                predicate_algebra.Comparison("eq", predicate_algebra.FieldSubject("Person.id"), 1),
            ),
            assignments=(WriteAssignment("Person.name", "Readless"),),
        ),
        _PERSON,
    )
    assert isinstance(predicate, PreparedPredicateWrite)
    uow.buffer_predicate(predicate)
    _flush(uow)
    later = _published(uow, _person(1), read_at=read_at)
    _write(uow, _PERSON, source, "amend", name="Source")
    _write(uow, _PERSON, later, "amend", name="Later")


# --------------------------------------------------------------------------- #
# A registration lasts exactly as long as something reaches the evidence.     #
# --------------------------------------------------------------------------- #
def _reinserted(uow: UnitOfWork, key: int) -> None:
    """Delete person ``key`` through a source and insert it again, both
    completed, after which every publication of it registers its evidence."""
    _write(uow, _PERSON, _published(uow, _person(key)), "delete")
    _flush(uow)
    insertion = prepare_typed_write(
        KeyedWriteInstruction("insert", "Person", ({"id": key, "name": "Again"},)), _PERSON
    )
    assert isinstance(insertion, PreparedKeyedWrite)
    uow.buffer(insertion)
    _flush(uow)


def test_only_a_stale_publication_or_one_of_a_deleted_object_registers() -> None:
    uow, _simulated = _uow(_PERSON)
    read_at = uow.freshness
    held = [_published(uow, _person(key)) for key in (1, 2)]
    _write(uow, _PERSON, held[0], "amend", name="Ada")
    _flush(uow)
    _reinserted(uow, 3)
    assert _registrations(uow) == 0
    held.extend(_published(uow, _person(key)) for key in (1, 2))
    assert _registrations(uow) == 0
    held.append(_published(uow, _person(1), read_at=read_at))
    held.append(_published(uow, _person(3)))
    assert _registrations(uow) == 2


def test_equal_evidence_keeps_two_registrations_and_each_releases_with_its_last_carrier() -> None:
    uow, _simulated = _uow(_PERSON)
    _reinserted(uow, 1)
    first = _published(uow, _person(1))
    second = ReadEvidence(first.entity, first.object_key, first.participation, None)
    assert second == first
    uow.register_read_evidence(second, read_at=uow.freshness)
    assert _registrations(uow) == 2
    del first
    assert _registrations(uow) == 1
    # The survivor keeps its own read's judgment.
    _write(uow, _PERSON, second, "amend", name="Kept")
    del second
    _flush(uow)
    assert _registrations(uow) == 0


def test_a_pending_or_planned_write_keeps_its_source_until_released() -> None:
    seen: list[tuple[bool, int]] = []
    uow: UnitOfWork | None = None
    held: list[weakref.ref[ReadEvidence]] = []

    def observe(_position: int, _steps: object) -> None:
        assert uow is not None
        if held:
            gc.collect()
            seen.append((held[-1]() is not None, _registrations(uow)))

    simulated = SimulatedWriteSteps(build_write_planner(_PERSON).payloads, _PERSON, POSTGRES)
    uow, _ = _uow(_PERSON, ObservedSteps(simulated, observe=observe))
    _reinserted(uow, 1)
    source = _published(uow, _person(1))
    held.append(weakref.ref(source))
    _write(uow, _PERSON, source, "amend", name="Ada")
    del source
    gc.collect()
    assert held[-1]() is not None and _registrations(uow) == 1
    _flush(uow)
    assert seen == [(True, 1)]
    assert held[-1]() is None and _registrations(uow) == 0


def test_a_failed_group_neither_advances_nor_ends_its_sources_and_a_traceback_holds_them() -> None:
    failure = RuntimeError("the group failed")
    simulated = SimulatedWriteSteps(build_write_planner(_ACCOUNT).payloads, _ACCOUNT, POSTGRES)
    uow, _ = _uow(_ACCOUNT, ObservedSteps(simulated, failing=0, failure=failure))
    source = _published(uow, _account(1), version=1)
    held = weakref.ref(source)
    _write(uow, _ACCOUNT, source, "delete")
    with pytest.raises(RuntimeError, match="the group failed") as raised:
        _flush(uow)
    assert uow._admission.resolve_source(source) == VersionedObjectStateKey(_account(1), 1)  # pyright: ignore[reportPrivateUsage] - nothing published for the failed group
    with pytest.raises(RollbackOnlyError):
        _flush(uow)
    del source
    gc.collect()
    # The traceback still reaches the plan, which keeps the evidence it settled.
    assert held() is not None
    traceback: Any = raised.value.__traceback__
    assert traceback is not None
    raised.value.__traceback__ = None
    del raised, traceback
    gc.collect()
    assert held() is None


def test_discarding_the_attempt_releases_every_registration_an_escaped_source_had() -> None:
    uow, _simulated = _uow(_PERSON)
    _reinserted(uow, 1)
    escaped = _published(uow, _person(1))
    assert _registrations(uow) == 1
    uow.discard()
    assert _registrations(uow) == 0
    assert not any(held is uow for held in reachable_objects(escaped))
