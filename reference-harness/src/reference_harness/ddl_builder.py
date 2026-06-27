"""Derive ``CREATE TABLE`` DDL from a model descriptor (dialect-aware).

The neutral-type -> column-type mapping is the M0 table; it lives behind the
dialect (M11). Postgres is round-1; Phase 10 adds MariaDB as the second dialect
behind the same seam. The harness derives DDL from the descriptor so the database
schema is never authored by hand — it is a function of the metamodel, exactly as
an implementation's would be.
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
    # The embedded-value `json` type maps to JSONB (M0/M1, Phase 9): a whole
    # valueObject is stored in one JSONB column rather than column-flattened.
    "json": "jsonb",
}

# M0 neutral type -> MariaDB column type (Phase 10, the second dialect). The
# divergences from Postgres that matter here:
#   * `boolean`   -> MariaDB has no native boolean; `tinyint(1)` is the idiom
#                    (and `TRUE`/`FALSE` are aliases for `1`/`0`).
#   * `timestamp` -> `datetime(6)`: MariaDB's `TIMESTAMP` is range-limited
#                    (2038) and auto-updates, so milestones use `DATETIME` with
#                    microsecond precision. Crucially `DATETIME` has NO native
#                    `'infinity'`, so the open temporal upper bound maps to a
#                    documented MAX-SENTINEL at the provider seam (M11), not here.
#   * `float64`   -> `double`; `bytes` -> `longblob`; `json` -> `json`
#                    (MariaDB's `JSON` is an alias for `LONGTEXT`).
#   * `uuid`      -> no native UUID type; stored as `char(36)`.
_MARIADB_BASE_TYPES = {
    "boolean": "tinyint(1)",
    "int32": "int",
    "int64": "bigint",
    "float32": "float",
    "float64": "double",
    "bytes": "longblob",
    "date": "date",
    "time": "time",
    "timestamp": "datetime(6)",
    "uuid": "char(36)",
    "json": "json",
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


def _mariadb_column_type(neutral_type: str, max_length: int | None) -> str:
    decimal = _DECIMAL_RE.match(neutral_type)
    if decimal:
        precision, scale = decimal.group(1), decimal.group(2)
        return f"decimal({precision},{scale})"
    if neutral_type == "string":
        # MariaDB has no unbounded `text`-as-key column; an unbounded string maps
        # to `text`, a bounded one to `varchar(n)` (indexable, like Postgres).
        return f"varchar({max_length})" if max_length else "text"
    base = _MARIADB_BASE_TYPES.get(neutral_type)
    if base is None:
        raise ValueError(f"no MariaDB mapping for neutral type {neutral_type!r}")
    return base


def _column_type(neutral_type: str, max_length: int | None, dialect: str) -> str:
    if dialect == "postgres":
        return _postgres_column_type(neutral_type, max_length)
    if dialect == "mariadb":
        return _mariadb_column_type(neutral_type, max_length)
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

    # A valueObject is stored in ONE JSONB column (M1/M0, Phase 9): the whole
    # embedded composite, not column-flattened. Append its backing column after
    # the scalar attributes (so the Phase 1-8 cases are unaffected).
    for value_object in entity.value_objects:
        column_type = _column_type("json", None, dialect)
        parts = [value_object["column"], column_type]
        if not value_object.get("nullable", False):
            parts.append("not null")
        columns.append(" ".join(parts))

    # A temporal entity stores many milestone rows per business key, so the
    # declared primaryKey attribute(s) are NOT unique on their own — the unique
    # physical key is the business key PLUS each as-of dimension's `fromColumn`
    # (the milestone start). Extend the physical primary key accordingly so the
    # DDL admits the milestone chain (M7).
    for as_of in entity.as_of_attributes:
        from_column = as_of["fromColumn"]
        if from_column not in pk_columns:
            pk_columns.append(from_column)

    if pk_columns:
        columns.append(f"primary key ({', '.join(pk_columns)})")

    column_clause = ",\n  ".join(columns)
    return f"create table {entity.table} (\n  {column_clause}\n)"


def ddl_for(model: Model, dialect: str) -> list[str]:
    """Return the ordered DDL statements that create every entity's table.

    One ``CREATE TABLE`` per **distinct table** (a multi-entity descriptor yields
    several). A `table-per-hierarchy` inheritance model maps several entities to
    ONE shared table (each declaring the same columns), so tables are emitted
    once, keyed by name — the first entity declaring a table owns its DDL.
    Foreign keys are intentionally omitted: relationships are a query concern
    (navigation/join derivation), and leaving FK constraints out keeps
    fixture-load order unconstrained.
    """
    statements: list[str] = []
    seen: set[str] = set()
    for entity in model.entities:
        if entity.table in seen:
            continue
        seen.add(entity.table)
        statements.append(_create_table(entity, dialect))
    return statements


def column_order(entity: Entity) -> Sequence[str]:
    """The descriptor's column order for *entity* (matches DDL + load order).

    Scalar attributes first, then each valueObject's single JSONB column — the
    same order :func:`_create_table` emits, so fixture loading and table-state
    reads stay column-aligned.
    """
    columns = [attribute["column"] for attribute in entity.attributes]
    columns.extend(value_object["column"] for value_object in entity.value_objects)
    return columns
