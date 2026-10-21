"""Leaving a Non-Temporal source unregistered answers as registering it would.

Ownership registers a Non-Temporal source only where its publication cannot
answer as read before every later deletion of its object: one published
stale, or one of an object a completed deletion removed. Each script runs
twice over simulated step execution, once as production registers and once
registering every source exactly, and after every step each live source must
reach the same state, or meet the same refusal, in both.
"""

from __future__ import annotations

import datetime as dt
import gc
from collections.abc import Callable
from decimal import Decimal

import pytest

from parallax.conformance._simulated_write_steps import SimulatedWriteSteps
from parallax.conformance.class_models import MODELS as CLASS_MODELS
from parallax.conformance.scripted_clock import FixedClock
from parallax.core import opt_lock
from parallax.core._execution._planning import build_write_planner
from parallax.core._execution._transaction._lifetime import TxnAttemptLifetime
from parallax.core._execution._unit_work._write_ownership import (
    SourceRefusal,
    WriteOwnership,
    _ReadRegistration,  # pyright: ignore[reportPrivateUsage] - the registration exact registering makes
)
from parallax.core._execution._unit_work.instructions import (
    KeyedMutation,
    PreparedKeyedWrite,
    prepare_typed_write,
)
from parallax.core.dialect import POSTGRES
from parallax.core.entity._model import model_of
from parallax.core.metamodel import Metamodel, entity_by_name
from parallax.core.unit_work import (
    KeyedWriteInstruction,
    ReadEvidence,
    RetainedObservation,
    TransactionSettings,
    UnitOfWork,
    buffered_write,
)
from parallax.core.write_plan import ObjectKey, VersionObservation
from parallax.core.write_plan.keys import ObjectStateKey, VersionedObjectStateKey
from tests._support.planner_probes import TEST_ACTOR_IDENTITY
from tests.unit._corpus_identity_support import corpus_object_key
from tests.unit._corpus_model_support import corpus_records, formed
from tests.unit._gc_reachability import reachable_objects
from tests.unit.core._execution._unit_work._acquired_rows_support import HeldRows

_ACCOUNT = formed(corpus_records()["account"])
_PERSON = model_of(CLASS_MODELS["person"])

type _Answer = tuple[str, object]


def _register_exactly(
    self: WriteOwnership,
    evidence: ReadEvidence,
    *,
    read_at: int,
    current: Callable[[ObjectKey | ObjectStateKey, int], bool],
) -> None:
    observation = evidence.observation
    if observation is not None and not isinstance(observation.key, VersionedObjectStateKey):
        return
    state = evidence.object_key if observation is None else observation.key
    self._read_registrations[id(evidence)] = _ReadRegistration(  # pyright: ignore[reportPrivateUsage] - the index exact registering fills
        evidence,
        self._release,  # pyright: ignore[reportPrivateUsage] - the callback every registration shares
        read_at if current(state, read_at) else None,
    )


def _publish_exactly(self: UnitOfWork, evidence: ReadEvidence, /, *, read_at: int) -> None:
    self._admission.register_read_evidence(  # pyright: ignore[reportPrivateUsage] - registering before any change completed too
        evidence,
        read_at=read_at,
        current=self._current,  # pyright: ignore[reportPrivateUsage] - the judgment production registration makes
    )


class _Run:
    """One attempt a script drives, answering what every source it published
    reaches after each step."""

    def __init__(self, meta: Metamodel) -> None:
        self.meta = meta
        simulated = SimulatedWriteSteps(build_write_planner(meta).payloads, meta, POSTGRES)
        self.uow = UnitOfWork(
            settings=TransactionSettings(),
            lifetime=TxnAttemptLifetime(),
            clock=FixedClock(dt.datetime(2024, 6, 1, tzinfo=dt.UTC)),
            meta=meta,
            execute_write_steps=simulated,
            execute_counted_step=simulated.counted,
            acquire_rows=HeldRows(meta),
            planner=build_write_planner(meta),
            actor_identity=TEST_ACTOR_IDENTITY,
            evidence_policy_for=opt_lock.view(meta).required_key,
        )
        self.start = self.uow.freshness
        self.sources: dict[str, ReadEvidence] = {}
        self.answers: list[list[_Answer]] = []

    def publish(
        self, label: str, key: ObjectKey, *, version: int | None = None, read_at: int | None = None
    ) -> None:
        stamp = self.uow.freshness if read_at is None else read_at
        observation = None
        if version is not None:
            observation = self.uow.retain(
                RetainedObservation(
                    VersionedObjectStateKey(key, version),
                    VersionObservation(observed_version=version),
                    self.uow.participation,
                ),
                read_at=stamp,
            )
        evidence = ReadEvidence(key.entity, key, self.uow.participation, observation)
        self.uow.register_read_evidence(evidence, read_at=stamp)
        self.sources[label] = evidence
        self._answer()

    def write(self, label: str, mutation: KeyedMutation, **members: object) -> None:
        source = self.sources[label]
        entity = entity_by_name(self.meta, f"parallax.compatibility.{source.entity.name}")
        assert entity is not None
        key = source.object_key
        instruction = prepare_typed_write(
            KeyedWriteInstruction(
                mutation, entity.identity.name, ({**dict(key.primary_key), **members},)
            ),
            self.meta,
        )
        assert isinstance(instruction, PreparedKeyedWrite)
        settled = self.uow.resolve_read_evidence(entity, source, mutation=mutation, object_key=key)
        self.uow.buffer(buffered_write(instruction, settled, source=source))

    def insert(self, entity: str, **members: object) -> None:
        instruction = prepare_typed_write(
            KeyedWriteInstruction("insert", entity, (members,)), self.meta
        )
        assert isinstance(instruction, PreparedKeyedWrite)
        self.uow.buffer(instruction)

    def flush(self) -> None:
        self.uow.read(lambda: None)
        self._answer()

    def registrations(self) -> int:
        gc.collect()
        return sum(isinstance(held, _ReadRegistration) for held in reachable_objects(self.uow))

    def _answer(self) -> None:
        resolve = self.uow._admission.resolve_source  # pyright: ignore[reportPrivateUsage] - resolution without a write's refusal
        self.answers.append([(label, resolve(source)) for label, source in self.sources.items()])

    def kinds(self) -> set[str]:
        kinds: set[str] = set()
        for answers in self.answers:
            for label, answer in answers:
                if isinstance(answer, SourceRefusal):
                    kinds.add(answer.value)
                    continue
                observation = self.sources[label].observation
                if observation is None:
                    kinds.add("object")
                else:
                    kinds.add("observed" if answer == observation.key else "advanced")
        return kinds


def _person(key: int) -> ObjectKey:
    return corpus_object_key("Person", ("id", key))


def _account(key: int) -> ObjectKey:
    return corpus_object_key("Account", ("id", key))


def _unversioned(run: _Run) -> None:
    run.publish("early", _person(1))
    run.publish("doomed", _person(2))
    run.publish("bystander", _person(3))
    run.write("early", "amend", name="Ada")
    run.flush()
    run.publish("fresh", _person(1))
    run.publish("page before the amendment", _person(1), read_at=run.start)
    run.write("doomed", "delete")
    run.flush()
    run.publish("page before the deletion", _person(2), read_at=run.start)
    run.insert("Person", id=2, name="Again")
    run.flush()
    run.publish("reinserted", _person(2))
    run.write("reinserted", "amend", name="Bo")
    run.flush()
    between = run.uow.freshness
    run.write("fresh", "delete")
    run.flush()
    run.publish("page between the amendment and the deletion", _person(1), read_at=between)
    run.insert("Person", id=1, name="Back")
    run.flush()
    run.publish("back", _person(1))
    run.write("back", "amend", name="Cy")
    run.flush()


def _versioned(run: _Run) -> None:
    run.publish("first", _account(1), version=1)
    run.publish("doomed", _account(2), version=4)
    run.publish("bystander", _account(3), version=7)
    run.write("first", "amend", owner="Ada")
    run.flush()
    run.publish("fresh", _account(1), version=2)
    run.publish("page before the amendment", _account(1), version=1, read_at=run.start)
    run.write("first", "amend", owner="Bo")
    run.flush()
    run.publish("below the produced range", _account(1), version=0)
    run.write("fresh", "amend", balance=Decimal("9.00"))
    run.flush()
    run.write("doomed", "delete")
    run.flush()
    run.publish("page before the deletion", _account(2), version=4, read_at=run.start)
    run.insert("Account", id=2, owner="Cy", balance=Decimal("1.00"))
    run.flush()
    run.publish("reinserted", _account(2), version=1)
    run.write("reinserted", "amend", owner="Di")
    run.flush()


@pytest.mark.parametrize(
    ("meta", "script", "kinds"),
    [
        pytest.param(_PERSON, _unversioned, {"object", "stale", "ended"}, id="unversioned"),
        pytest.param(
            _ACCOUNT,
            _versioned,
            {"observed", "advanced", "stale", "ended"},
            id="versioned",
        ),
    ],
)
def test_an_unregistered_source_resolves_as_its_exact_registration_would(
    meta: Metamodel, script: Callable[[_Run], None], kinds: set[str]
) -> None:
    elided = _Run(meta)
    script(elided)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(WriteOwnership, "register_read_evidence", _register_exactly)
        patch.setattr(UnitOfWork, "register_read_evidence", _publish_exactly)
        exact = _Run(meta)
        script(exact)
    assert elided.answers == exact.answers
    assert elided.kinds() == kinds
    assert 0 < elided.registrations() < exact.registrations() == len(exact.sources)
