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
    PredicateWrite,
    SubjectActor,
    buffered_write,
    object_key,
)
from parallax.core.unit_work.instructions import (
    PreparedKeyedWrite,
    PreparedPredicateWrite,
    PreparedWrite,
    prepare_typed_write,
)
from parallax.core.unit_work.materialized import (
    AfterRemoval,
    ObjectClaimedWrite,
    ObservedKeyedWrite,
)
from parallax.core.unit_work.strategy import ActorIdentity
from parallax.core.unit_work.write_planner import BufferedWrite, compose_writes
from parallax.core.unit_work.write_settlement import OrderedWrite
from parallax.core.write_plan import ObjectKey, WriteObservation

__all__ = ["TEST_ACTOR_IDENTITY", "observed_buffer", "observed_write"]

# An arbitrary Actor Identity: `m-unit-work` requires one on every Planning
# Request and guarantees it is never inspected, so either closed variant serves
# every suite here identically.
TEST_ACTOR_IDENTITY: Final[ActorIdentity] = SubjectActor("test-subject")


def observed_buffer(
    buffer: Sequence[BufferItem | KeyedWrite | PredicateWrite],
    model: Metamodel,
    observations: Mapping[ObjectKey, WriteObservation] | None,
) -> list[OrderedWrite]:
    """``buffer`` with every item ``observations`` names wrapped in its carrier,
    composed in authored order as a unit of work composes what it admits.

    A planner-level suite states which objects the transaction observed, which
    is the readable way to author the scenario; the verb that would do the
    resolving is not in play. This turns that statement into what a verb
    buffers — the instruction travelling with its own observation — through the
    same :func:`~parallax.core.unit_work.buffered_write` a verb uses, so a suite
    that names an object an insert also writes is refused here exactly as a verb
    would refuse it.
    """
    prepared = [_prepared_item(item, model) for item in buffer]
    resolved: list[BufferItem] = []
    for item in prepared:
        if not observations or not isinstance(item, PreparedKeyedWrite):
            resolved.append(item)
            continue
        key = object_key(item, model)
        resolved.append(buffered_write(item, None if key is None else observations.get(key)))
    return [_settled(item) for item in compose_writes(model, resolved)]


def observed_write(
    instruction: PreparedWrite, model: Metamodel, observation: WriteObservation | None
) -> OrderedWrite:
    """``instruction`` buffered against ``observation``, as the one write a
    buffer holds."""
    (only,) = compose_writes(model, [buffered_write(instruction, observation)])
    return _settled(only)


def _settled(item: BufferedWrite) -> OrderedWrite:
    """``item`` as settlement reads it: these suites buffer no insert that
    waits on an earlier removal."""
    assert not isinstance(item, AfterRemoval)
    return item


def _prepared_item(item: BufferItem | KeyedWrite | PredicateWrite, model: Metamodel) -> BufferItem:
    if isinstance(item, ObservedKeyedWrite | ObjectClaimedWrite | MaterializedWriteGroup):
        return item
    if isinstance(item, KeyedWrite | PredicateWrite) and not isinstance(
        item, PreparedKeyedWrite | PreparedPredicateWrite
    ):
        return prepare_typed_write(item, model)
    return item
