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
    ChunkedColumnBuilder,
    KeyedWrite,
    MaterializedWriteGroup,
    ObjectKey,
    PredecessorColumns,
    PredecessorShape,
    PredicateWrite,
    SubjectActor,
    TemporalColumns,
    WriteObservation,
    buffered_write,
    object_key,
    whole,
)
from parallax.core.unit_work.instructions import (
    PreparedKeyedWrite,
    PreparedPredicateWrite,
    prepare_typed_write,
)
from parallax.core.unit_work.materialized import ObjectClaimedWrite, ObservedKeyedWrite
from parallax.core.unit_work.strategy import ActorIdentity

__all__ = ["TEST_ACTOR_IDENTITY", "observed_buffer", "temporal_group"]

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
        resolved.append(buffered_write(item, None if key is None else observations.get(key)))
    return resolved


def _prepared_item(item: BufferItem | KeyedWrite | PredicateWrite, model: Metamodel) -> BufferItem:
    if isinstance(item, ObservedKeyedWrite | ObjectClaimedWrite | MaterializedWriteGroup):
        return item
    if isinstance(item, KeyedWrite | PredicateWrite) and not isinstance(
        item, PreparedKeyedWrite | PreparedPredicateWrite
    ):
        return prepare_typed_write(item, model)
    return item


def temporal_group(
    mutation: PredicateWrite,
    model: Metamodel,
    predecessors: Sequence[Mapping[str, object]],
    *,
    key_name: str = "id",
) -> MaterializedWriteGroup:
    """The Materialized Write Group ``mutation`` settles to once its resolving
    read matched ``predecessors``: each row keyed by its ``key_name`` member and
    retained whole as its Predecessor Row."""
    prepared = prepare_typed_write(mutation, model)
    assert isinstance(prepared, PreparedPredicateWrite)
    names = tuple(predecessors[0])
    keys: ChunkedColumnBuilder[object] = ChunkedColumnBuilder()
    members = {name: ChunkedColumnBuilder[object]() for name in names}
    for row in predecessors:
        keys.append(row[key_name])
        for name in names:
            members[name].append(row[name])
    return MaterializedWriteGroup(
        mutation=prepared,
        key_attributes=(key_name,),
        key_columns=(whole(keys.build()),),
        observations=TemporalColumns(
            predecessors=PredecessorColumns(
                shape=PredecessorShape(attributes=names),
                attribute_columns=tuple(whole(members[name].build()) for name in names),
            )
        ),
    )
