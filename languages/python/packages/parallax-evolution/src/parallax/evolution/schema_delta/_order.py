from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Final

from parallax.evolution.schema_delta._physical import (
    AddColumn,
    CreateExtension,
    CreateIndex,
    CreateTable,
    DropIndex,
    PhysicalOperation,
    RestateColumnDomain,
    TableOperation,
    member_key,
    table_of,
)

__all__ = ["order", "order_key"]

KIND_RANK: Final[Mapping[type, int]] = {
    CreateTable: 0,
    AddColumn: 1,
    RestateColumnDomain: 2,
    CreateIndex: 3,
    DropIndex: 4,
}


def order_key(operation: TableOperation) -> tuple[str, int, str]:
    """The physical Table, then the operation kind, then the member addressed.

    Leading with the Table rather than with the kind keeps one Table's statements
    together and keeps the whole output stable under an edit to an unrelated
    Table.
    """
    return (table_of(operation).name, KIND_RANK[type(operation)], member_key(operation))


def order(plan: Sequence[PhysicalOperation]) -> tuple[PhysicalOperation, ...]:
    """``plan`` in executable order.

    A prerequisite is depended on by every Table creation that requires it, so
    each one precedes every Table operation; the Table operations keep their own
    order among themselves.
    """
    prerequisites = sorted(
        (operation for operation in plan if isinstance(operation, CreateExtension)),
        key=lambda operation: operation.name,
    )
    local = sorted(
        (operation for operation in plan if not isinstance(operation, CreateExtension)),
        key=order_key,
    )
    return (*prerequisites, *local)
