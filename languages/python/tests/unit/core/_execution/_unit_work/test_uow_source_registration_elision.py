"""Leaving a Non-Temporal source unregistered answers as registering every
publication would.

A declarative scenario captures rows as a read acquires them, publishes each
capture's Read Evidence later, writes through published sources, and
flushes, declaring what each flush's completed writes change, advance, and
delete. Production runs it through the real lazy publication seam into the
attempt's source authority, which registers only some publications. A
test-only reference records every publication and judges it from the
scenario's declarations alone. After every step each live source must resolve
alike in both, and each scenario's last step states its outcomes outright.
"""

from __future__ import annotations

import datetime as dt
import gc
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal

import pytest

from parallax.conformance._simulated_write_steps import SimulatedWriteSteps
from parallax.conformance.class_models import MODELS as CLASS_MODELS
from parallax.conformance.scripted_clock import FixedClock
from parallax.core import opt_lock
from parallax.core._execution._planning import build_write_planner
from parallax.core._execution._retention import ReadEvidenceByProjection
from parallax.core._execution._transaction._lifetime import TxnAttemptLifetime
from parallax.core._execution._unit_work.instructions import (
    KeyedMutation,
    PreparedKeyedInstruction,
    prepare_typed_write,
)
from parallax.core.dialect import POSTGRES
from parallax.core.entity._model import model_of
from parallax.core.metamodel import EntityMetadata, Metamodel, entity_by_name
from parallax.core.unit_work import (
    KeyedWriteInstruction,
    ReadEvidence,
    TransactionSettings,
    UnitOfWork,
    WriteEvidenceError,
    admitted_write,
    object_key,
)
from parallax.core.write_plan import ObjectKey
from parallax.core.write_plan.keys import VersionedObjectStateKey
from tests._support.planner_probes import TEST_ACTOR_IDENTITY
from tests.unit._corpus_identity_support import corpus_object_key
from tests.unit._corpus_model_support import corpus_records, formed
from tests.unit._judged_evidence_support import judged_evidence
from tests.unit.core._execution._unit_work._acquired_rows_support import HeldRows

_ACCOUNT = formed(corpus_records()["account"])
_PERSON = model_of(CLASS_MODELS["person"])

type _Outcome = ObjectKey | VersionedObjectStateKey | str
"""What resolving a source answers: the object or exact version it settles
against, or ``stale`` or ``ended`` for the two consumed refusals."""


@dataclass(frozen=True, slots=True)
class _Capture:
    """A read acquires the row of ``key`` at ``version``, publishing nothing yet."""

    label: str
    key: ObjectKey
    version: int | None = None


@dataclass(frozen=True, slots=True)
class _Publish:
    """The capture ``label`` publishes its Read Evidence."""

    label: str


@dataclass(frozen=True, slots=True)
class _Write:
    """A keyed write through the published source ``label``."""

    label: str
    mutation: KeyedMutation
    members: Mapping[str, object] = field(default_factory=dict[str, object])


@dataclass(frozen=True, slots=True)
class _Insert:
    entity: str
    members: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class _Completed:
    """What one settled write a flush completes does, declared by the scenario:
    the states or objects it ``changes``, each ``(object, from, to)`` version
    it ``advances``, and the objects it ``deletes``."""

    changes: tuple[ObjectKey | VersionedObjectStateKey, ...] = ()
    advances: tuple[tuple[ObjectKey, int, int], ...] = ()
    deletes: tuple[ObjectKey, ...] = ()


@dataclass(frozen=True, slots=True)
class _Flush:
    completes: tuple[_Completed, ...] = ()


@dataclass(frozen=True, slots=True)
class _Release:
    """Nothing holds the published source ``label`` any longer."""

    label: str


@dataclass(frozen=True, slots=True)
class _Expect:
    """Every live source resolves exactly as ``outcomes`` states."""

    outcomes: Mapping[str, _Outcome]


type _Step = _Capture | _Publish | _Write | _Insert | _Flush | _Release | _Expect


class _Production:
    """One attempt running a scenario through the lazy publication seam and
    its source authority."""

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
        self.captured: dict[str, ReadEvidenceByProjection] = {}
        self.published: dict[str, ReadEvidence] = {}

    def run(self, step: _Step) -> None:
        match step:
            case _Capture(label, key, version):
                self.captured[label] = judged_evidence(
                    self.meta,
                    key.entity,
                    _row(key, version),
                    evidence_context=self.uow.source_authority,
                )
            case _Publish(label):
                self.published[label] = self.captured.pop(label)[0]
            case _Write(label, mutation, members):
                self._write(self.published[label], mutation, members)
            case _Insert(entity, members):
                instruction = prepare_typed_write(
                    KeyedWriteInstruction("insert", entity, (members,)), self.meta
                )
                assert isinstance(instruction, PreparedKeyedInstruction)
                self.uow.buffer_insert(
                    admitted_write(instruction, None, object_key(instruction, self.meta)),
                    insertion_advice=None,
                )
            case _Flush():
                self.uow.read(lambda: None)
            case _Release(label):
                del self.published[label]
                gc.collect()
            case _Expect():
                pass

    def answers(self) -> dict[str, _Outcome]:
        return {label: self._resolved(source) for label, source in self.published.items()}

    def _entity(self, source: ReadEvidence) -> EntityMetadata:
        entity = entity_by_name(self.meta, f"parallax.compatibility.{source.entity.name}")
        assert entity is not None
        return entity

    def _resolved(self, source: ReadEvidence) -> _Outcome:
        try:
            settled = self.uow.source_authority.resolve_read_evidence(
                self._entity(source), source, mutation="amend", object_key=source.object_key
            )
        except WriteEvidenceError as refused:
            assert refused.code == "write-evidence-consumed"
            return "stale" if "has since changed the state" in refused.message else "ended"
        assert isinstance(settled, ObjectKey | VersionedObjectStateKey)
        return settled

    def _write(
        self, source: ReadEvidence, mutation: KeyedMutation, members: Mapping[str, object]
    ) -> None:
        entity = self._entity(source)
        key = source.object_key
        instruction = prepare_typed_write(
            KeyedWriteInstruction(
                mutation, entity.identity.name, ({**dict(key.primary_key), **members},)
            ),
            self.meta,
        )
        assert isinstance(instruction, PreparedKeyedInstruction)
        settled = self.uow.source_authority.resolve_read_evidence(
            entity, source, mutation=mutation, object_key=key
        )
        assert settled is not None  # a write of existing state settles against something
        self.uow.buffer(admitted_write(instruction, settled, key, source=source))


class _ExactReference:
    """Every publication recorded with the change count its capture saw, and
    judged from the scenario's declared completions alone.

    A publication is stale where a declared change of what it observed
    completed after its capture; a source ends where a declared deletion of
    its object completed after its capture; a versioned source otherwise
    settles against the latest version a run of declared advances produced
    from the one it observed."""

    def __init__(self) -> None:
        self.changes = 0
        self.changed_at: dict[ObjectKey | VersionedObjectStateKey, int] = {}
        self.deleted_at: dict[ObjectKey, int] = {}
        self.versions: dict[ObjectKey, tuple[int, int]] = {}
        self.captured: dict[str, tuple[ObjectKey, int | None, int]] = {}
        self.published: dict[str, tuple[ObjectKey, int | None, int, bool]] = {}

    def run(self, step: _Step) -> None:
        match step:
            case _Capture(label, key, version):
                self.captured[label] = (key, version, self.changes)
            case _Publish(label):
                key, version, read_at = self.captured.pop(label)
                changed = self.changed_at.get(_observed(key, version))
                self.published[label] = (
                    key,
                    version,
                    read_at,
                    changed is None or changed <= read_at,
                )
            case _Flush(completes):
                for completed in completes:
                    self._complete(completed)
            case _Release(label):
                del self.published[label]
            case _Write() | _Insert() | _Expect():
                pass

    def answers(self) -> dict[str, _Outcome]:
        return {label: self._resolved(*held) for label, held in self.published.items()}

    def _complete(self, completed: _Completed) -> None:
        if completed.changes:
            self.changes += 1
        for state in completed.changes:
            self.changed_at[state] = self.changes
        for key, advanced_from, produced in completed.advances:
            held = self.versions.get(key)
            first = held[0] if held is not None and held[1] == advanced_from else advanced_from
            self.versions[key] = (first, produced)
        for key in completed.deletes:
            self.deleted_at[key] = self.changes
            self.versions.pop(key, None)

    def _resolved(self, key: ObjectKey, version: int | None, read_at: int, fresh: bool) -> _Outcome:
        if not fresh:
            return "stale"
        deleted = self.deleted_at.get(key)
        if deleted is not None and deleted > read_at:
            return "ended"
        if version is None:
            return key
        held = self.versions.get(key)
        if held is not None and held[0] <= version < held[1]:
            return VersionedObjectStateKey(key, held[1])
        return VersionedObjectStateKey(key, version)


def _observed(key: ObjectKey, version: int | None) -> ObjectKey | VersionedObjectStateKey:
    return key if version is None else VersionedObjectStateKey(key, version)


def _row(key: ObjectKey, version: int | None) -> dict[str, object]:
    ((_name, value),) = key.primary_key
    if version is None:
        return {"id": value, "name": "Ada"}
    return {"id": value, "owner": "Ada", "balance": Decimal("1.00"), "version": version}


def _person(key: int) -> ObjectKey:
    return corpus_object_key("Person", ("id", key))


def _account(key: int) -> ObjectKey:
    return corpus_object_key("Account", ("id", key))


def _version(key: int, version: int) -> VersionedObjectStateKey:
    return VersionedObjectStateKey(_account(key), version)


_UNVERSIONED: tuple[_Step, ...] = (
    _Capture("early", _person(1)),
    _Publish("early"),
    _Capture("doomed", _person(2)),
    _Publish("doomed"),
    _Capture("bystander", _person(3)),
    _Publish("bystander"),
    _Capture("page before the amendment", _person(1)),
    _Capture("page before the deletion", _person(2)),
    # Equal but distinct evidence of one object, each judged by its own
    # publication and living as long as its own holder.
    _Capture("twin published at once", _person(3)),
    _Publish("twin published at once"),
    _Capture("twin published later", _person(3)),
    _Write("early", "amend", {"name": "Ada"}),
    _Flush((_Completed(changes=(_person(1),)),)),
    _Capture("fresh", _person(1)),
    _Publish("fresh"),
    _Publish("page before the amendment"),
    _Write("bystander", "amend", {"name": "By"}),
    _Flush((_Completed(changes=(_person(3),)),)),
    _Publish("twin published later"),
    _Write("doomed", "delete"),
    _Flush((_Completed(changes=(_person(2),), deletes=(_person(2),)),)),
    _Publish("page before the deletion"),
    _Insert("Person", {"id": 2, "name": "Again"}),
    _Flush(),
    _Capture("reinserted", _person(2)),
    _Publish("reinserted"),
    _Write("reinserted", "amend", {"name": "Bo"}),
    _Flush((_Completed(changes=(_person(2),)),)),
    _Release("twin published at once"),
    _Capture("page between the amendment and the deletion", _person(1)),
    _Write("fresh", "delete"),
    _Flush((_Completed(changes=(_person(1),), deletes=(_person(1),)),)),
    _Publish("page between the amendment and the deletion"),
    _Insert("Person", {"id": 1, "name": "Back"}),
    _Flush(),
    _Capture("back", _person(1)),
    _Publish("back"),
    _Write("back", "amend", {"name": "Cy"}),
    _Flush((_Completed(changes=(_person(1),)),)),
    _Expect(
        {
            "early": "ended",
            "doomed": "ended",
            "bystander": _person(3),
            "fresh": "ended",
            "page before the amendment": "stale",
            "twin published later": "stale",
            "page before the deletion": "stale",
            "reinserted": _person(2),
            "page between the amendment and the deletion": "stale",
            "back": _person(1),
        }
    ),
)

_VERSIONED: tuple[_Step, ...] = (
    _Capture("first", _account(1), 1),
    _Publish("first"),
    _Capture("doomed", _account(2), 4),
    _Publish("doomed"),
    _Capture("bystander", _account(3), 7),
    _Publish("bystander"),
    _Capture("page before the amendment", _account(1), 1),
    _Capture("page before the deletion", _account(2), 4),
    _Write("first", "amend", {"owner": "Ada"}),
    _Flush((_Completed(changes=(_version(1, 1),), advances=((_account(1), 1, 2),)),)),
    _Capture("fresh", _account(1), 2),
    _Publish("fresh"),
    _Publish("page before the amendment"),
    # Through the version the first amendment produced.
    _Write("first", "amend", {"owner": "Bo"}),
    _Flush((_Completed(changes=(_version(1, 2),), advances=((_account(1), 2, 3),)),)),
    _Capture("below the produced range", _account(1), 0),
    _Publish("below the produced range"),
    _Write("fresh", "amend", {"balance": Decimal("9.00")}),
    _Flush((_Completed(changes=(_version(1, 3),), advances=((_account(1), 3, 4),)),)),
    _Write("doomed", "delete"),
    _Flush((_Completed(changes=(_version(2, 4),), deletes=(_account(2),)),)),
    _Publish("page before the deletion"),
    _Insert("Account", {"id": 2, "owner": "Cy", "balance": Decimal("1.00")}),
    _Flush(),
    _Capture("reinserted", _account(2), 1),
    _Publish("reinserted"),
    _Write("reinserted", "amend", {"owner": "Di"}),
    _Flush((_Completed(changes=(_version(2, 1),), advances=((_account(2), 1, 2),)),)),
    _Expect(
        {
            "first": _version(1, 4),
            "doomed": "ended",
            "bystander": _version(3, 7),
            "fresh": _version(1, 4),
            "page before the amendment": "stale",
            "below the produced range": _version(1, 0),
            "page before the deletion": "stale",
            "reinserted": _version(2, 2),
        }
    ),
)


def _kinds(answers: list[dict[str, _Outcome]], published: Mapping[str, int | None]) -> set[str]:
    kinds: set[str] = set()
    for answered in answers:
        for label, outcome in answered.items():
            if isinstance(outcome, str):
                kinds.add(outcome)
            elif isinstance(outcome, ObjectKey):
                kinds.add("object")
            else:
                kinds.add("observed" if outcome.version == published[label] else "advanced")
    return kinds


@pytest.mark.parametrize(
    ("meta", "scenario", "kinds"),
    [
        pytest.param(_PERSON, _UNVERSIONED, {"object", "stale", "ended"}, id="unversioned"),
        pytest.param(
            _ACCOUNT, _VERSIONED, {"observed", "advanced", "stale", "ended"}, id="versioned"
        ),
    ],
)
def test_an_unregistered_source_resolves_as_its_exact_registration_would(
    meta: Metamodel, scenario: tuple[_Step, ...], kinds: set[str]
) -> None:
    production = _Production(meta)
    reference = _ExactReference()
    answers: list[dict[str, _Outcome]] = []
    versions: dict[str, int | None] = {}
    for step in scenario:
        if isinstance(step, _Capture):
            versions[step.label] = step.version
        production.run(step)
        reference.run(step)
        answered = production.answers()
        assert answered == reference.answers(), step
        if isinstance(step, _Expect):
            assert answered == step.outcomes
        answers.append(answered)
    assert isinstance(scenario[-1], _Expect)
    assert _kinds(answers, versions) == kinds
