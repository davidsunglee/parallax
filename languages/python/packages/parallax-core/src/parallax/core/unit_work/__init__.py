"""``parallax.core.unit_work`` enforcement scope (m-unit-work).

The transaction scope: the unit of work that **buffers, orders, and flushes**
writes, the write-instruction IR it buffers, the Clock Strategy that supplies the
processing instant at flush, and the **pure planner** that turns a buffer into a
neutral, execution-ordered intermediate flush plan (coalesce -> FK-order -> elide).

The module DAG pins ``m-unit-work -> m-op-algebra`` and ``m-unit-work -> m-db-port``
**only** — there is deliberately **no** edge to ``m-sql`` or ``m-dialect``. So this
scope holds no SQL generation: the planner emits a neutral :class:`FlushPlan`, and
the write-DML -> SQL lowering (the deliberate ``m-sql`` edge) happens one layer up,
at the composition surface that legally sees both (M4). These are internal engine
seams, not part of the developer surface — nothing here is re-exported from
``parallax.core``.
"""

from __future__ import annotations

from parallax.core.unit_work.clock import Clock, FixedClock, SystemClock, instant_literal
from parallax.core.unit_work.instructions import (
    KeyedMutation,
    KeyedWrite,
    PredicateMutation,
    PredicateWrite,
    WriteAssignment,
    WriteInstruction,
    WriteInstructionError,
    WriteTarget,
    deserialize,
    serialize,
    validate_instruction,
)
from parallax.core.unit_work.planner import (
    AtomicUnit,
    BufferItem,
    CollapsePolicy,
    FlushPlan,
    ObjectKey,
    Observation,
    PlannedWrite,
    object_key,
    plan_flush,
)
from parallax.core.unit_work.uow import (
    Concurrency,
    EscapedTransactionError,
    FlushExecutor,
    RollbackOnlyError,
    TransactionSettings,
    UnitOfWork,
    UnitOfWorkError,
    active_unit_of_work,
    run_unit_of_work,
)
from parallax.core.unit_work.write_validate import WriteRejectedError, validate_write

__all__ = [
    "AtomicUnit",
    "BufferItem",
    "Clock",
    "CollapsePolicy",
    "Concurrency",
    "EscapedTransactionError",
    "FixedClock",
    "FlushExecutor",
    "FlushPlan",
    "KeyedMutation",
    "KeyedWrite",
    "ObjectKey",
    "Observation",
    "PlannedWrite",
    "PredicateMutation",
    "PredicateWrite",
    "RollbackOnlyError",
    "SystemClock",
    "TransactionSettings",
    "UnitOfWork",
    "UnitOfWorkError",
    "WriteAssignment",
    "WriteInstruction",
    "WriteInstructionError",
    "WriteRejectedError",
    "WriteTarget",
    "active_unit_of_work",
    "deserialize",
    "instant_literal",
    "object_key",
    "plan_flush",
    "run_unit_of_work",
    "serialize",
    "validate_instruction",
    "validate_write",
]
