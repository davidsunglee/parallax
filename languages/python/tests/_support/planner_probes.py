"""Shared inputs for suites that drive the unit-of-work shell, the
write-lowering seam, or the Write Planner directly, without a full
``Database``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Final

from parallax.core.metamodel import Metamodel
from parallax.core.unit_work import (
    BufferItem,
    KeyedWrite,
    MaterializedWriteGroup,
    ObjectClaimedWrite,
    ObjectKey,
    PreparedKeyedWrite,
    PreparedPredicateWrite,
    PredicateWrite,
    ObservedKeyedWrite,
    SubjectIdentity,
    WriteObservation,
    buffered_write,
    object_key,
    prepare_typed_write,
)

__all__ = ["TEST_SUBJECT_IDENTITY", "observed_buffer"]

# An arbitrary nonempty Subject Identity: `m-unit-work` requires one on every
# Planning Request and guarantees it is never inspected, so any value serves
# every suite here identically.
TEST_SUBJECT_IDENTITY: Final[SubjectIdentity] = SubjectIdentity("test-subject")


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
        resolved.append(buffered_write(item, None if key is None else observations.get(key)))
    return resolved


def _prepared_item(
    item: BufferItem | KeyedWrite | PredicateWrite, model: Metamodel
) -> BufferItem:
    if isinstance(item, ObservedKeyedWrite):
        instruction = prepare_typed_write(item.instruction, model)
        assert isinstance(instruction, PreparedKeyedWrite)
        return ObservedKeyedWrite(
            instruction,
            item.observation,
            claim=item.claim,
            restorations=item.restorations,
        )
    if isinstance(item, ObjectClaimedWrite):
        instruction = prepare_typed_write(item.instruction, model)
        assert isinstance(instruction, PreparedKeyedWrite)
        return ObjectClaimedWrite(instruction, restorations=item.restorations)
    if isinstance(item, MaterializedWriteGroup):
        prepared = prepare_typed_write(item.mutation, model)
        assert not isinstance(prepared, PreparedKeyedWrite)
        return MaterializedWriteGroup(
            mutation=prepared,
            key_attributes=item.key_attributes,
            key_columns=item.key_columns,
            observations=item.observations,
        )
    if isinstance(item, KeyedWrite | PredicateWrite) and not isinstance(
        item, PreparedKeyedWrite | PreparedPredicateWrite
    ):
        return prepare_typed_write(item, model)
    return item
