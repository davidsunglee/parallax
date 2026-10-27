from __future__ import annotations

from parallax.core.dialect import (
    ColumnDdl,
    Dialect,
    ExclusionDdl,
    IndexColumnDdl,
    IntervalCheckDdl,
    Unsupported,
)
from parallax.evolution.schema_delta._physical import (
    AddColumn,
    CreateExtension,
    CreateIndex,
    CreateTable,
    DropIndex,
    Exclusion,
    IndexDefinition,
    PhysicalColumn,
    PhysicalOperation,
    RestateColumnDomain,
)

__all__ = ["render"]


def render(operation: PhysicalOperation, dialect: Dialect) -> str | Unsupported:
    """``operation`` as one statement, or why ``dialect`` cannot spell it."""
    match operation:
        case CreateExtension():
            return dialect.create_extension(dialect.quote(operation.name))
        case CreateTable():
            return dialect.create_table(
                dialect.quote(operation.table.name),
                [_column(column, dialect) for column in operation.columns],
                [dialect.quote(column.name) for column in operation.primary_key],
                [
                    IntervalCheckDdl(
                        name=dialect.quote(check.name),
                        start=dialect.quote(check.start.name),
                        end=dialect.quote(check.end.name),
                    )
                    for check in operation.interval_checks
                ],
                primary_key_name=(
                    None
                    if operation.primary_key_name is None
                    else dialect.quote(operation.primary_key_name)
                ),
                exclusion=(
                    None
                    if operation.exclusion is None
                    else _exclusion(operation.exclusion, dialect)
                ),
            )
        case AddColumn():
            return dialect.add_column(
                dialect.quote(operation.table.name), _column(operation.column, dialect)
            )
        case RestateColumnDomain():
            return dialect.restate_column(
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


def _exclusion(exclusion: Exclusion, dialect: Dialect) -> ExclusionDdl:
    return ExclusionDdl(
        name=dialect.quote(exclusion.name),
        equal=tuple(dialect.quote(column.name) for column in exclusion.equal),
        overlapping=tuple(
            (dialect.quote(start.name), dialect.quote(end.name))
            for start, end in exclusion.overlapping
        ),
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
