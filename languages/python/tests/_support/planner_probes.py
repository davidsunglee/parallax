"""Shared inputs for suites that drive the unit-of-work shell, the
write-lowering seam, or the Write Planner directly, without a full
``Database``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Final

from parallax.core import inheritance
from parallax.core.document_codec import EffectiveChangeSet, classify_effective_change
from parallax.core.metamodel import Metamodel
from parallax.core.unit_work import (
    UPDATE_MUTATIONS,
    BufferItem,
    KeyedWrite,
    MaterializedWriteGroup,
    ObjectKey,
    PredicateWrite,
    SubjectActor,
    TemporalObservation,
    WriteObservation,
    buffered_write,
    object_key,
)
from parallax.core.unit_work.instructions import (
    PreparedKeyedWrite,
    PreparedPredicateWrite,
    PreparedWrite,
    prepare_typed_write,
)
from parallax.core.unit_work.materialized import ObjectClaimedWrite, ObservedKeyedWrite
from parallax.core.unit_work.strategy import ActorIdentity

__all__ = ["TEST_ACTOR_IDENTITY", "observed_buffer", "observed_write", "producer_change"]

# An arbitrary Actor Identity: `m-unit-work` requires one on every Planning
# Request and guarantees it is never inspected, so either closed variant serves
# every suite here identically.
TEST_ACTOR_IDENTITY: Final[ActorIdentity] = SubjectActor("test-subject")


def observed_buffer(
    buffer: Sequence[BufferItem | KeyedWrite | PredicateWrite],
    model: Metamodel,
    observations: Mapping[ObjectKey, WriteObservation] | None,
) -> list[BufferItem]:
    """``buffer`` with every item ``observations`` names wrapped in its carrier.

    A planner-level suite states which objects the transaction observed, which
    is the readable way to author the scenario; the verb that would do the
    resolving is not in play. This turns that statement into what a verb
    buffers — the instruction travelling with its own observation — through the
    same :func:`~parallax.core.unit_work.buffered_write` a verb uses, so a suite
    that names an object an insert also writes is refused here exactly as a verb
    would refuse it.
    """
    prepared = [_prepared_item(item, model) for item in buffer]
    if not observations:
        return prepared
    resolved: list[BufferItem] = []
    for item in prepared:
        if not isinstance(item, PreparedKeyedWrite):
            resolved.append(item)
            continue
        key = object_key(item, model)
        resolved.append(observed_write(item, model, None if key is None else observations.get(key)))
    return resolved


def observed_write(
    instruction: PreparedWrite, model: Metamodel, observation: WriteObservation | None
) -> BufferItem:
    """``instruction`` buffered against ``observation`` beside the change set a
    verb would classify for it (:func:`producer_change`)."""
    return buffered_write(
        instruction, observation, change=producer_change(instruction, model, observation)
    )


def producer_change(
    instruction: PreparedWrite, model: Metamodel, observation: WriteObservation | None
) -> EffectiveChangeSet | None:
    """The effective change set a keyed update settles against ``observation``
    with, classified by the rule the verb applies: the assigned members, less the
    identity, against the originals the evidence observed, over the target's
    applicable document shape.

    Only an observed single-row update has one; the carrier refuses an observed
    write of several rows itself. A Predecessor Row states the originals; a
    version observation states none, so every assigned member is effective.
    """
    if (
        observation is None
        or not isinstance(instruction, PreparedKeyedWrite)
        or instruction.mutation not in UPDATE_MUTATIONS
        or len(instruction.rows) != 1
    ):
        return None
    view = inheritance.view(model).entity(instruction.target.identity)
    assert view is not None  # the facet covers every accepted Entity
    key = view.primary_key.identity.name
    (row,) = instruction.rows
    assigned = {name: value for name, value in row.items() if name != key}
    if not isinstance(observation, TemporalObservation):
        return EffectiveChangeSet(effective=frozenset(assigned), restored=frozenset())
    return classify_effective_change(
        view.applicable_document_shape, assigned, observation.predecessor.members
    )


def _prepared_item(item: BufferItem | KeyedWrite | PredicateWrite, model: Metamodel) -> BufferItem:
    if isinstance(item, ObservedKeyedWrite | ObjectClaimedWrite | MaterializedWriteGroup):
        return item
    if isinstance(item, KeyedWrite | PredicateWrite) and not isinstance(
        item, PreparedKeyedWrite | PreparedPredicateWrite
    ):
        return prepare_typed_write(item, model)
    return item
