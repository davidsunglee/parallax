"""One physical operation to one statement, or to the Dialect's refusal.

The invariant half of rendering — which Columns, which types, which key — is
already settled by the planner; this module only quotes identifiers and asks the
Dialect for spellings. Nothing here names a dialect or branches on one, so the
same code renders every vendor and a synthetic Dialect drives the whole path.
"""

from __future__ import annotations

from parallax.core.dialect import ColumnDdl, Dialect, IndexColumnDdl, Unsupported
from parallax.evolution.schema_delta._physical import (
    AddColumn,
    CreateIndex,
    CreateTable,
    DropIndex,
    ExpandColumnDomain,
    IndexDefinition,
    PhysicalColumn,
    PhysicalOperation,
)

__all__ = ["render"]


def render(operation: PhysicalOperation, dialect: Dialect) -> str | Unsupported:
    """``operation`` as one statement, or why ``dialect`` cannot spell it."""
    match operation:
        case CreateTable():
            return dialect.create_table(
                dialect.quote(operation.table.name),
                [_column(column, dialect) for column in operation.columns],
                [dialect.quote(column.name) for column in operation.primary_key],
            )
        case AddColumn():
            return dialect.add_column(
                dialect.quote(operation.table.name), _column(operation.column, dialect)
            )
        case ExpandColumnDomain():
            return dialect.expand_column(
                dialect.quote(operation.table.name),
                _column(operation.earlier, dialect),
                _column(operation.later, dialect),
            )
        case CreateIndex():
            return dialect.create_index(
                dialect.quote(operation.definition.table.name),
                operation.name,
                _components(operation.definition, dialect),
                unique=operation.definition.unique,
            )
        case DropIndex():
            return dialect.drop_index(
                dialect.quote(operation.definition.table.name), operation.name
            )


def _column(column: PhysicalColumn, dialect: Dialect) -> ColumnDdl:
    return ColumnDdl(
        column=dialect.quote(column.column.name),
        type_sql=dialect.column_type(column.neutral_type, column.max_length),
        nullable=column.nullable,
    )


def _components(definition: IndexDefinition, dialect: Dialect) -> list[IndexColumnDdl]:
    return [
        IndexColumnDdl(
            column=dialect.quote(column.column.name),
            neutral_type=column.neutral_type,
            max_length=column.max_length,
        )
        for column in definition.columns
    ]
