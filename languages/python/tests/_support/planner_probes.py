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
    PredicateWrite,
    SubjectActor,
    buffered_write,
    object_key,
)
from parallax.core.unit_work.acquisition import AcquireRows, RowConsumer, RowRequest
from parallax.core.unit_work.instructions import (
    PreparedKeyedWrite,
    PreparedPredicateWrite,
    PreparedWrite,
    prepare_typed_write,
)
from parallax.core.unit_work.materialized import (
    AfterRemoval,
    readless_write,
)
from parallax.core.unit_work.strategy import ActorIdentity
from parallax.core.unit_work.write_planner import BufferedWrite, compose_writes
from parallax.core.unit_work.write_settlement import OrderedWrite
from parallax.core.write_plan import ObjectKey, WriteObservation

__all__ = ["NO_ROW_READS", "TEST_ACTOR_IDENTITY", "observed_buffer", "observed_write"]

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


def observed_buffer(
    buffer: Sequence[BufferItem | KeyedWrite | PredicateWrite | PreparedPredicateWrite],
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
    buffer holds; a predicate write, which carries none, routed readless."""
    if isinstance(instruction, PreparedPredicateWrite):
        assert observation is None  # a predicate write is evidenced by its own read
        item: BufferItem = readless_write(instruction)
    else:
        item = buffered_write(instruction, observation)
    (only,) = compose_writes(model, [item])
    return _settled(only)


def _settled(item: BufferedWrite) -> OrderedWrite:
    """``item`` as settlement reads it: these suites buffer no insert that
    waits on an earlier removal."""
    assert not isinstance(item, AfterRemoval)
    return item


def _prepared_item(
    item: BufferItem | KeyedWrite | PredicateWrite | PreparedPredicateWrite, model: Metamodel
) -> BufferItem:
    """``item`` as a unit of work buffers it: an authored keyed write prepared,
    and a predicate write over a target these suites state is unversioned and
    Non-Temporal routed readless."""
    if isinstance(item, KeyedWrite):
        return prepare_typed_write(item, model)
    if isinstance(item, PredicateWrite):
        return readless_write(prepare_typed_write(item, model))
    if isinstance(item, PreparedPredicateWrite):
        return readless_write(item)
    return item
