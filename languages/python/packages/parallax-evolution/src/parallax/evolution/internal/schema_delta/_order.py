from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Final

from parallax.evolution.internal.schema_delta._physical import (
    AddColumn,
    CreateExtension,
    CreateIndex,
    CreateSequence,
    CreateTable,
    DropIndex,
    PhysicalOperation,
    RestateColumnDomain,
    TableOperation,
    member_key,
    table_of,
)

__all__ = ["order", "order_key", "table_operations"]

KIND_RANK: Final[Mapping[type, int]] = {
    CreateTable: 0,
    AddColumn: 1,
    RestateColumnDomain: 2,
    CreateIndex: 3,
    DropIndex: 4,
}


def order_key(operation: TableOperation) -> tuple[str, tuple[str, ...], int, str]:
    """The physical Table — its local name, then its qualifier — then the
    operation kind, then the member addressed.

    Leading with the Table rather than with the kind keeps one Table's statements
    together and keeps the whole output stable under an edit to an unrelated
    Table; the qualifier tells equal local names in different locations apart.
    """
    physical = table_of(operation).physical
    return (physical.name, physical.qualifier, KIND_RANK[type(operation)], member_key(operation))


def order(plan: Sequence[PhysicalOperation]) -> tuple[PhysicalOperation, ...]:
    """``plan`` in executable order.

    A prerequisite is depended on by every Table creation that requires it, so
    each one precedes every Table operation. A sequence depends on nothing and
    nothing in the delta depends on it, so the sequences follow the
    prerequisites in physical-name order. The Table operations keep their own
    order among themselves.
    """
    prerequisites = sorted(
        (operation for operation in plan if isinstance(operation, CreateExtension)),
        key=lambda operation: operation.name,
    )
    sequences = sorted(
        (operation for operation in plan if isinstance(operation, CreateSequence)),
        key=lambda operation: (
            operation.sequence.physical.name,
            operation.sequence.physical.qualifier,
        ),
    )
    return (*prerequisites, *sequences, *table_operations(plan))


def table_operations(plan: Sequence[PhysicalOperation]) -> tuple[TableOperation, ...]:
    """``plan``'s Table operations alone, in executable order among themselves."""
    return tuple(
        sorted(
            (
                operation
                for operation in plan
                if isinstance(
                    operation,
                    CreateTable | AddColumn | RestateColumnDomain | CreateIndex | DropIndex,
                )
            ),
            key=order_key,
        )
    )
