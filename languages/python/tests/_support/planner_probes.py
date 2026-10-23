"""Shared inputs for suites that drive the unit-of-work shell, the
write-lowering seam, or the Write Planner directly, without a full
``Database``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Final

from parallax.core import opt_lock, temporal_read
from parallax.core._execution._unit_work.acquisition import AcquireRows, RowConsumer, RowRequest
from parallax.core._execution._unit_work.admission import WriteAdmission
from parallax.core._execution._unit_work.instructions import (
    INSERT_MUTATIONS,
    PreparedKeyedInstruction,
    prepare_typed_write,
)
from parallax.core._execution._unit_work.retain import (
    ParticipationToken,
    ReadEvidence,
    RetainedObservation,
)
from parallax.core._execution._unit_work.strategy import ActorIdentity
from parallax.core._execution._unit_work.write_items import (
    ComposedWrite,
    OrderedWrite,
    PostRemovalInsert,
    TargetWrite,
)
from parallax.core._execution._unit_work.write_runner import ExecuteCountedStep
from parallax.core.metamodel import EntityIdentity, Metamodel
from parallax.core.unit_work import (
    AdmittedWrite,
    KeyedWriteInstruction,
    SubjectActor,
    admitted_write,
    object_key,
)
from parallax.core.write_plan import ObjectKey, StateObservation, WritePlan
from parallax.core.write_plan.keys import object_state_key_from_observation
from parallax.core.write_plan.plan import SettledWrite, WriteGroup
from parallax.core.write_plan.steps import PlannedDelete, PlannedStep, PlannedUpdate

__all__ = [
    "NO_COUNTED_STEPS",
    "NO_ROW_READS",
    "TEST_ACTOR_IDENTITY",
    "admitted_writes",
    "object_source",
    "observed_buffer",
    "observed_write",
    "plan_steps",
    "retained_observation",
    "settled_writes",
    "unobserved_write",
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
    ``participation``, by default one no unit of work issued: what an
    object-locked write keeps where a suite admits it directly rather than
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
) -> list[OrderedWrite]:
    """``buffer`` with every authored instruction prepared and admitted as the
    write a verb would build for it, admitted in authored order as a unit of
    work admits it.

    A planner-level suite states which objects the transaction observed, which
    is the readable way to author the scenario; the verb that would do the
    resolving is not in play. This turns that statement into what a verb
    buffers — the instruction travelling with the one retained observation its
    attempt holds for that object — through the same
    :func:`~parallax.core.unit_work.admitted_write` a verb uses, so a suite
    that names an object an insert also writes is refused here exactly as a verb
    would refuse it. An instruction of an object ``observations`` does not
    name is licensed by the buffer's standing insertion of that object, as a
    write through the inserted value is, and is otherwise admitted as
    :func:`unobserved_write` admits it.
    """
    admission = _admission(model)
    retained: dict[ObjectKey, RetainedObservation] = {}
    for item in buffer:
        if isinstance(item, KeyedWriteInstruction):
            prepared = prepare_typed_write(item, model)
            key = object_key(prepared, model)
            observation = None if key is None or not observations else observations.get(key)
            if key is not None and observation is not None:
                held = retained.get(key)
                if held is None:
                    held = retained[key] = retained_observation(prepared, model, observation)
                item = admitted_write(prepared, held)
            else:
                item = _authorized(admission, prepared, key, model)
        admission.admit(item, confirm_target=_optimistic)
    return [_settled(item) for item in admission.composed_writes()]


def _authorized(
    admission: WriteAdmission,
    instruction: PreparedKeyedInstruction,
    key: ObjectKey | None,
    model: Metamodel,
) -> AdmittedWrite:
    identity = (
        None
        if key is None or instruction.mutation in INSERT_MUTATIONS
        else admission.insertion_identity(key)
    )
    if identity is None:
        return unobserved_write(instruction, model)
    return admitted_write(instruction, None, authority=identity)


def observed_write(
    instruction: PreparedKeyedInstruction, model: Metamodel, observation: StateObservation | None
) -> OrderedWrite:
    """``instruction`` buffered against ``observation``, as the one write a
    buffer holds."""
    item: AdmittedWrite
    if observation is None:
        item = unobserved_write(instruction, model)
    else:
        item = admitted_write(instruction, retained_observation(instruction, model, observation))
    (only,) = admitted_writes(model, [item])
    return _settled(only)


def unobserved_write(instruction: PreparedKeyedInstruction, model: Metamodel) -> AdmittedWrite:
    """``instruction`` as the admitted write a verb builds where its source
    observed nothing: an insert, or an object-locked write of an unversioned
    row admitted through :func:`object_source` evidence. Any other write needs
    an observation, so a suite admitting one without it is refused."""
    evidence = opt_lock.settled_evidence(
        opt_lock.optimistic_key(model, instruction.target.identity),
        instruction.mutation,
        object_key=object_key(instruction, model),
        observation=None,
    )
    if evidence is None:
        return admitted_write(instruction, None)
    write = f"`{instruction.mutation}` on {instruction.target.identity.canonical!r}"
    assert isinstance(evidence, ObjectKey), f"{write} needs an observation"
    return admitted_write(instruction, evidence, source=object_source(evidence))


def admitted_writes(model: Metamodel, writes: Sequence[AdmittedWrite]) -> tuple[ComposedWrite, ...]:
    """``writes`` admitted in authored order into one buffer, and that
    buffer's composed writes, under the Optimistic strategy, whose confirmation
    of a caller's revision reads nothing."""
    admission = _admission(model)
    for item in writes:
        admission.admit(item, confirm_target=_optimistic)
    return admission.composed_writes()


def _admission(model: Metamodel) -> WriteAdmission:
    return WriteAdmission(model, inserted_version=_no_insertion_authorizes, observations={})


def _optimistic(item: TargetWrite) -> TargetWrite:
    return item


def _no_insertion_authorizes(entity: EntityIdentity, advanced_from: int | None) -> int | None:
    raise AssertionError(f"no write an insertion of {entity.canonical!r} authorized is admitted")


def retained_observation(
    instruction: PreparedKeyedInstruction, model: Metamodel, observation: StateObservation
) -> RetainedObservation:
    """``observation`` retained under the exact state of ``instruction``'s
    object it is evidence about, with no participating read."""
    key = object_key(instruction, model)
    assert key is not None  # an observation is evidence about one object
    shape = temporal_read.view(model).shape(instruction.target.identity)
    assert shape is not None  # the facet covers every accepted Entity
    return RetainedObservation(
        object_state_key_from_observation(key, observation, shape), observation, None
    )


def _settled(item: ComposedWrite) -> OrderedWrite:
    """``item`` as settlement reads it: these suites buffer no insert that
    waits on an earlier removal."""
    assert not isinstance(item, PostRemovalInsert)
    return item


def plan_steps(plan: WritePlan) -> tuple[PlannedStep, ...]:
    """Every Planned Step of ``plan``'s Write Groups, in execution order; a
    deferred write plans none."""
    return tuple(
        step for entry in plan.entries if isinstance(entry, WriteGroup) for step in entry.steps
    )


def settled_writes(plan: WritePlan) -> tuple[SettledWrite, ...]:
    """Every settled write of ``plan``, grouped or deferred, in completion
    order."""
    writes: list[SettledWrite] = []
    for entry in plan.entries:
        if isinstance(entry, SettledWrite):
            writes.append(entry)
            continue
        for write in entry.writes:
            assert isinstance(write, SettledWrite)  # planning groups settled writes
            writes.append(write)
    return tuple(writes)
