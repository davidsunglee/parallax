"""Shared inputs for suites that drive the unit-of-work shell, the
write-lowering seam, or the Write Planner directly, without a full
``Database``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Final

from parallax.core._execution._transaction._lifetime import TxnAttemptLifetime
from parallax.core._execution._unit_work._write_ownership import NoInsertionAuthority
from parallax.core._execution._unit_work.acquisition_spans import AcquisitionSpan
from parallax.core._execution._unit_work.admission import BufferOutcome, WriteAdmission
from parallax.core._execution._unit_work.evidence import (
    InsertionIdentity,
    ParticipationToken,
    ReadEvidence,
    RetainedObservation,
)
from parallax.core._execution._unit_work.instructions import (
    INSERT_MUTATIONS,
    PreparedKeyedInstruction,
    prepare_typed_write,
)
from parallax.core._execution._unit_work.ranges import DeferredRange
from parallax.core._execution._unit_work.row_acquisition import AcquireRows, RowConsumer, RowRequest
from parallax.core._execution._unit_work.source_registry import SourceRegistry
from parallax.core._execution._unit_work.strategy import ActorIdentity
from parallax.core._execution._unit_work.write_items import (
    ComposedBitemporalOpening,
    ComposedTemporalWrite,
    ComposedWrite,
    KeyedInsert,
    LicensedWrite,
    PostRemovalInsert,
    TxStartConditioned,
    VersionConditioned,
    WriteAuthority,
)
from parallax.core._execution._unit_work.write_plan import SettledWrite, WriteGroup, WritePlan
from parallax.core._execution._unit_work.write_runner import ExecuteCountedStep
from parallax.core.internal import concurrency, temporal_read
from parallax.core.internal.concurrency import ConcurrencyPreference
from parallax.core.internal.metamodel import Metamodel
from parallax.core.internal.planned_step import ObjectKey, StateObservation
from parallax.core.internal.planned_step.keys import object_state_key_from_observation
from parallax.core.internal.planned_step.steps import PlannedDelete, PlannedStep, PlannedUpdate
from parallax.core.internal.unit_work import (
    AdmittedWrite,
    KeyedWriteInstruction,
    SubjectActor,
    admitted_write,
    object_key,
    settled_evidence,
)
from tests._support.write_preparation import write_preparation_of

__all__ = [
    "NO_COUNTED_STEPS",
    "NO_ROW_READS",
    "TEST_ACTOR_IDENTITY",
    "admit",
    "admit_licensed",
    "admitted_writes",
    "deferred_ranges",
    "object_source",
    "observed_buffer",
    "observed_write",
    "plan_steps",
    "retained_observation",
    "settled_writes",
    "source_registry",
    "unobserved_write",
    "write_admission",
]

# An arbitrary Actor Identity: `m-unit-work` requires one on every Planning
# Request and guarantees it is never inspected, so either closed variant serves
# every suite here identically.
TEST_ACTOR_IDENTITY: Final[ActorIdentity] = SubjectActor("test-subject")


class _NoRowReads:
    """A row acquisition for a unit of work whose writes read no row: any read
    asked of it fails the suite."""

    def __call__[Request: RowRequest, Result](
        self, request: Request, consumer: RowConsumer[Request, Result], /
    ) -> Result:
        del consumer
        raise AssertionError(f"no row read expected, but {request!r} was asked for")


NO_ROW_READS: Final[AcquireRows] = _NoRowReads()


class _NoCountedSteps:
    """A counted step execution for a unit of work running no
    predicate-selected write: any asked of it fails the suite."""

    def __call__(self, step: PlannedUpdate | PlannedDelete, /) -> int:
        raise AssertionError(f"no predicate-selected write expected, but {step!r} executed")


NO_COUNTED_STEPS: Final[ExecuteCountedStep] = _NoCountedSteps()


def object_source(
    target: ObjectKey, participation: ParticipationToken | None = None
) -> ReadEvidence:
    """Observation-free Read Evidence of ``target``, stamped with
    ``participation``, by default one no unit of work issued: what a write of
    an unversioned object keeps where a suite admits it directly rather than
    through a verb."""
    return ReadEvidence(
        target.entity,
        target,
        ParticipationToken() if participation is None else participation,
        None,
    )


def observed_buffer(
    buffer: Sequence[AdmittedWrite | KeyedWriteInstruction],
    model: Metamodel,
    observations: Mapping[ObjectKey, StateObservation] | None,
) -> list[AdmittedWrite | ComposedTemporalWrite | ComposedBitemporalOpening]:
    """``buffer`` with every authored instruction prepared and admitted as the
    write a verb would build for it, admitted in authored order as a unit of
    work admits it.

    A planner-level suite states which objects the transaction observed, which
    is the readable way to author the scenario; the verb that would do the
    resolving is not in play. This turns that statement into what a verb
    buffers — the instruction travelling with the one retained observation its
    attempt holds for that object — through the same
    :func:`~parallax.core.internal.unit_work.admitted_write` a verb uses, so a suite
    that names an object an insert also writes is refused here exactly as a verb
    would refuse it. An instruction of an object ``observations`` does not
    name is licensed by the buffer's standing insertion of that object, as a
    write through the inserted value is, and is otherwise admitted as
    :func:`unobserved_write` admits it.
    """
    registry = source_registry(model)
    admission = WriteAdmission(model, registry=registry)
    retained: dict[ObjectKey, RetainedObservation] = {}
    handles: dict[ObjectKey, InsertionIdentity] = {}
    for item in buffer:
        if isinstance(item, KeyedWriteInstruction):
            prepared = prepare_typed_write(item, write_preparation_of(model))
            key = object_key(prepared, model)
            observation = None if key is None or not observations else observations.get(key)
            if key is not None and observation is not None:
                held = retained.get(key)
                if held is None:
                    held = retained[key] = retained_observation(prepared, model, observation)
                item = admitted_write(prepared, held, key)
            else:
                item = _authorized(registry, handles, prepared, key, model)
        identity = admit(admission, item)
        if identity is not None:
            handles[identity.object_key] = identity
    return [_settled(item) for item in admission.composed_writes()]


def _authorized(
    registry: SourceRegistry,
    handles: Mapping[ObjectKey, InsertionIdentity],
    instruction: PreparedKeyedInstruction,
    key: ObjectKey | None,
    model: Metamodel,
) -> AdmittedWrite:
    """``instruction`` licensed by the latest insertion of its object buffering
    issued while that insertion still stands, else as :func:`unobserved_write`
    admits it."""
    handle = None if key is None or instruction.mutation in INSERT_MUTATIONS else handles.get(key)
    if handle is None or isinstance(registry.insertion_anchor(handle), NoInsertionAuthority):
        return unobserved_write(instruction, model)
    return admitted_write(instruction, None, key, insertion=handle)


def observed_write(
    instruction: PreparedKeyedInstruction, model: Metamodel, observation: StateObservation | None
) -> AdmittedWrite | ComposedTemporalWrite | ComposedBitemporalOpening:
    """``instruction`` buffered against ``observation``, as the one write a
    buffer holds."""
    item: AdmittedWrite
    if observation is None:
        item = unobserved_write(instruction, model)
    else:
        item = admitted_write(
            instruction,
            retained_observation(instruction, model, observation),
            object_key(instruction, model),
        )
    (only,) = admitted_writes(model, [item])
    return _settled(only)


def unobserved_write(instruction: PreparedKeyedInstruction, model: Metamodel) -> AdmittedWrite:
    """``instruction`` as the admitted write a verb builds where its source
    observed nothing: an insert, or a write of an unversioned row admitted
    through :func:`object_source` evidence. Any other write needs
    an observation, so a suite admitting one without it is refused."""
    key = object_key(instruction, model)
    evidence = settled_evidence(
        concurrency.concurrency_facet_of(model),
        instruction.target.identity,
        instruction.mutation,
        object_key=key,
        observation=None,
    )
    if evidence is None:
        return admitted_write(instruction, None, key)
    write = f"`{instruction.mutation}` on {instruction.target.identity.canonical!r}"
    assert isinstance(evidence, ObjectKey), f"{write} needs an observation"
    return admitted_write(instruction, evidence, key, source=object_source(evidence))


def admitted_writes(model: Metamodel, writes: Sequence[AdmittedWrite]) -> tuple[ComposedWrite, ...]:
    """``writes`` admitted in authored order into one buffer (:func:`admit`),
    and that buffer's composed writes."""
    admission = write_admission(model)
    for item in writes:
        admit(admission, item)
    return admission.composed_writes()


def admit(admission: WriteAdmission, item: AdmittedWrite) -> InsertionIdentity | None:
    """``item`` admitted through the operation admission takes it by — an
    insert, with no opener advice, through its own, answering the identity it
    issued — under the Optimistic strategy, whose confirmation of a caller's
    revision reads nothing."""
    if isinstance(item, KeyedInsert):
        return admission.admit_insert(item, insertion_advice=None)
    admit_licensed(admission, item)
    return None


def admit_licensed(admission: WriteAdmission, item: LicensedWrite[WriteAuthority]) -> BufferOutcome:
    """``item`` admitted under the Optimistic strategy, whose confirmation of
    a caller's revision reads nothing."""
    return admission.admit(
        item, confirm_version=_optimistic_version, confirm_tx_start=_optimistic_tx_start
    )


def source_registry(
    model: Metamodel, *, concurrency: ConcurrencyPreference = "optimistic"
) -> SourceRegistry:
    """A source registry over ``model`` for an attempt that stays open."""
    return SourceRegistry(
        model,
        lifetime=TxnAttemptLifetime(),
        preference=concurrency,
    )


def write_admission(model: Metamodel) -> WriteAdmission:
    """An empty buffer over its own :func:`source_registry`."""
    return WriteAdmission(model, registry=source_registry(model))


def _optimistic_version(item: LicensedWrite[VersionConditioned]) -> None:
    del item


def _optimistic_tx_start(
    item: LicensedWrite[TxStartConditioned],
) -> LicensedWrite[TxStartConditioned]:
    return item


def retained_observation(
    instruction: PreparedKeyedInstruction, model: Metamodel, observation: StateObservation
) -> RetainedObservation:
    """``observation`` retained under the exact state of ``instruction``'s
    object it is evidence about, with no participating read."""
    key = object_key(instruction, model)
    assert key is not None  # an observation is evidence about one object
    shape = temporal_read.temporal_facet_of(model).shape(instruction.target.identity)
    assert shape is not None  # the facet covers every accepted Entity
    return RetainedObservation(
        object_state_key_from_observation(key, observation, shape), observation, None
    )


def _settled(
    item: ComposedWrite,
) -> AdmittedWrite | ComposedTemporalWrite | ComposedBitemporalOpening:
    """``item`` as settlement reads it: these suites buffer no insert that
    waits on an earlier removal."""
    assert not isinstance(item, PostRemovalInsert)
    return item


def plan_steps(plan: WritePlan) -> tuple[PlannedStep, ...]:
    """Every Planned Step of ``plan``'s Write Groups, in execution order; a
    deferred write plans none."""
    return tuple(step for turn in plan.turns if isinstance(turn, WriteGroup) for step in turn.steps)


def settled_writes(plan: WritePlan) -> tuple[SettledWrite, ...]:
    """Every settled write of ``plan``'s Write Groups, in completion order; a
    deferred write is none until it binds."""
    writes: list[SettledWrite] = []
    for turn in plan.turns:
        if isinstance(turn, WriteGroup):
            for write in turn.writes:
                assert isinstance(write, SettledWrite)  # planning groups settled writes
                writes.append(write)
    return tuple(writes)


def deferred_ranges(plan: WritePlan) -> tuple[DeferredRange, ...]:
    """Every deferred write of ``plan``'s acquisition spans, in order."""
    return tuple(
        deferred
        for turn in plan.turns
        if isinstance(turn, AcquisitionSpan)
        for deferred in turn.ranges
    )
