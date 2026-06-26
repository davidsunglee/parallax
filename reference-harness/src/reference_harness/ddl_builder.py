"""Derive ``CREATE TABLE`` DDL from a model descriptor (dialect-aware).

The neutral-type -> column-type mapping is the M0 table; it lives behind the
dialect (M11). For round 1 only Postgres is wired. The harness derives DDL from
the descriptor so the database schema is never authored by hand — it is a
function of the metamodel, exactly as an implementation's would be.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from .case import Entity, Model

# M0 neutral type -> Postgres column type.
_POSTGRES_BASE_TYPES = {
    "boolean": "boolean",
    "int32": "integer",
    "int64": "bigint",
    "float32": "real",
    "float64": "double precision",
    "bytes": "bytea",
    "date": "date",
    "time": "time",
    "timestamp": "timestamptz",
    "uuid": "uuid",
}

_DECIMAL_RE = re.compile(r"^decimal\((\d+),(\d+)\)$")


def _postgres_column_type(neutral_type: str, max_length: int | None) -> str:
    decimal = _DECIMAL_RE.match(neutral_type)
    if decimal:
        precision, scale = decimal.group(1), decimal.group(2)
        return f"numeric({precision},{scale})"
    if neutral_type == "string":
        return f"varchar({max_length})" if max_length else "text"
    base = _POSTGRES_BASE_TYPES.get(neutral_type)
    if base is None:
        raise ValueError(f"no Postgres mapping for neutral type {neutral_type!r}")
    return base


def _column_type(neutral_type: str, max_length: int | None, dialect: str) -> str:
    if dialect == "postgres":
        return _postgres_column_type(neutral_type, max_length)
    raise ValueError(f"no DDL type mapping for dialect {dialect!r}")


def _create_table(entity: Entity, dialect: str) -> str:
    columns: list[str] = []
    pk_columns: list[str] = []
    for attribute in entity.attributes:
        column_type = _column_type(
            attribute["type"], attribute.get("maxLength"), dialect
        )
        parts = [attribute["column"], column_type]
        if not attribute.get("nullable", False):
            parts.append("not null")
        columns.append(" ".join(parts))
        if attribute.get("primaryKey", False):
            pk_columns.append(attribute["column"])

    if pk_columns:
        columns.append(f"primary key ({', '.join(pk_columns)})")

    column_clause = ",\n  ".join(columns)
    return f"create table {entity.table} (\n  {column_clause}\n)"


def ddl_for(model: Model, dialect: str) -> list[str]:
    """Return the ordered DDL statements that create every entity's table.

    One ``CREATE TABLE`` per declared entity (a multi-entity descriptor yields
    several). Foreign keys are intentionally omitted: relationships are a query
    concern (navigation/join derivation), and leaving FK constraints out keeps
    fixture-load order unconstrained.
    """
    return [_create_table(entity, dialect) for entity in model.entities]


def column_order(entity: Entity) -> Sequence[str]:
    """The descriptor's column order for *entity* (matches DDL + load order)."""
    return [attribute["column"] for attribute in entity.attributes]
