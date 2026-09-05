"""Executable statement order: one sort, because every dependency edge is local.

`m-schema-delta` states the order as dependency rules plus tie-breakers. Every
rule the current algebra can violate stays inside one Table — a Table exists
before anything on it, a Column exists before an Index over it, and an altered
Index's target is created before its earlier definition is dropped — so the key
below is a linear extension of the whole dependency relation and the sort emits
what a topological walk over the same key would.

Nothing is allocated that could outlive the call: there are no nodes, no edges,
and no in-degree table. :func:`dependency_violations` is the guard that keeps the
shortcut honest, and the first cross-Table operation kind — a foreign key being
the obvious one — is what would reintroduce an explicit graph.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Final

from parallax.evolution.schema_delta._physical import (
    AddColumn,
    CreateIndex,
    CreateTable,
    DropIndex,
    ExpandColumnDomain,
    PhysicalOperation,
    member_key,
    table_of,
)

__all__ = ["dependency_violations", "order", "order_key"]

KIND_RANK: Final[Mapping[type, int]] = {
    CreateTable: 0,
    AddColumn: 1,
    ExpandColumnDomain: 2,
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


def dependency_violations(ordered: Sequence[PhysicalOperation]) -> tuple[str, ...]:
    """Every dependency rule ``ordered`` breaks, empty when it is executable.

    The invariant :func:`order_key` rests on, stated over the three rules
    themselves so the key can never silently stop being a linear extension of
    them. A rule is silent about a prerequisite the plan does not contain: an
    operation on a Table this delta does not create acts on one the earlier
    edition already had.
    """
    tables = {
        table_of(operation).name: position
        for position, operation in enumerate(ordered)
        if isinstance(operation, CreateTable)
    }
    columns = {
        (table_of(operation).name, operation.column.column.name): position
        for position, operation in enumerate(ordered)
        if isinstance(operation, AddColumn)
    }
    indices = {
        operation.definition.index: position
        for position, operation in enumerate(ordered)
        if isinstance(operation, CreateIndex)
    }
    violations: list[str] = []
    for position, operation in enumerate(ordered):
        table = table_of(operation).name
        if tables.get(table, position) > position:
            violations.append(f"{position}: {table} is acted on before it is created")
        if isinstance(operation, CreateIndex):
            violations.extend(
                f"{position}: {operation.name.value} indexes {table}.{column.column.name} "
                "before that Column is added"
                for column in operation.definition.columns
                if columns.get((table, column.column.name), position) > position
            )
        if isinstance(operation, DropIndex) and (
            indices.get(operation.definition.index, position) > position
        ):
            violations.append(
                f"{position}: {operation.name.value} drops an altered Index before its "
                "target definition is created"
            )
    return tuple(violations)
