from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Final

from parallax.evolution.schema_delta._physical import (
    AddColumn,
    CreateIndex,
    CreateTable,
    DropIndex,
    PhysicalOperation,
    RestateColumnDomain,
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


def order_key(operation: PhysicalOperation) -> tuple[str, int, str]:
    """The physical Table, then the operation kind, then the member addressed.

    Leading with the Table rather than with the kind keeps one Table's statements
    together and keeps the whole output stable under an edit to an unrelated
    Table.
    """
    return (table_of(operation).name, KIND_RANK[type(operation)], member_key(operation))


def order(plan: Sequence[PhysicalOperation]) -> tuple[PhysicalOperation, ...]:
    """``plan`` in executable order."""
    return tuple(sorted(plan, key=order_key))
