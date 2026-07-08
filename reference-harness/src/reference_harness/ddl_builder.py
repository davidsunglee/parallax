"""Derive ``CREATE TABLE`` DDL from a model descriptor (dialect-aware).

The neutral-type -> column-type mapping is the m-core table; it lives behind the
dialect (m-dialect). Postgres is round-1; Phase 10 adds MariaDB as the second dialect
behind the same seam. The harness derives DDL from the descriptor so the database
schema is never authored by hand — it is a function of the metamodel, exactly as
an implementation's would be.
"""

from __future__ import annotations

import copy
import re
from collections.abc import Sequence

from .case import Entity, Model

# m-core neutral type -> Postgres column type.
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
    # The embedded-value `json` type maps to Postgres JSONB (m-core/m-value-object, Phase 9): a
    # whole valueObject is stored in one structured column rather than
    # column-flattened.
    "json": "jsonb",
}

# m-core neutral type -> MariaDB column type (Phase 10, the second dialect). The
# divergences from Postgres that matter here:
#   * `boolean`   -> MariaDB has no native boolean; `tinyint(1)` is the idiom
#                    (and `TRUE`/`FALSE` are aliases for `1`/`0`).
#   * `timestamp` -> `datetime(6)`: MariaDB's `TIMESTAMP` is range-limited
#                    (2038) and auto-updates, so milestones use `DATETIME` with
#                    microsecond precision. Crucially `DATETIME` has NO native
#                    `'infinity'`, so the open temporal upper bound maps to a
#                    documented MAX-SENTINEL owned by the dialect (m-dialect), not here.
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

# A "simple" identifier needs no quoting; anything else (a reserved word, or a
# name with uppercase / special characters / a leading digit) MUST be quoted.
_SIMPLE_IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]*$")

# Reserved words that, although lexically simple, MUST be quoted when used as a
# column/table identifier. The set is **per-dialect** (m-dialect: identifier
# quoting): a keyword list differs from database to database, so the quoting
# DECISION — not merely the quote character — diverges. The curated base below is
# the words shared by both dialects (enough to cover identifiers a model might
# realistically use, e.g. `order`); a non-simple name (uppercase / special) is
# caught by the regex regardless. This mirrors the per-dialect sets the TypeScript
# dialects already carry (`postgres.ts` / `mariadb.ts` `RESERVED_WORDS`); it is a
# non-normative harness fix bringing the harness into line with the already-
# normative per-dialect rule (m-dialect), and introduces no new normative surface.
_RESERVED_WORDS_BASE = frozenset(
    {
        "all",
        "and",
        "as",
        "asc",
        "between",
        "by",
        "case",
        "check",
        "column",
        "constraint",
        "create",
        "default",
        "delete",
        "desc",
        "distinct",
        "drop",
        "else",
        "end",
        "exists",
        "foreign",
        "from",
        "group",
        "having",
        "in",
        "index",
        "insert",
        "into",
        "is",
        "join",
        "key",
        "like",
        "limit",
        "not",
        "null",
        "on",
        "or",
        "order",
        "primary",
        "references",
        "select",
        "set",
        "table",
        "then",
        "to",
        "union",
        "unique",
        "update",
        "user",
        "using",
        "values",
        "when",
        "where",
    }
)

# `position` is a MariaDB-only addition: `POSITION()` is a reserved SQL function
# name on MariaDB (so an unquoted `Position` table emits an unparseable
# `insert into position(...)` there) but NOT on Postgres, where `position` stays
# unquoted — byte-identical to the existing bare-Postgres `position` goldens. This
# is exactly the divergence the single-set shape could not express.
_RESERVED_WORDS = {
    "postgres": _RESERVED_WORDS_BASE,
    "mariadb": _RESERVED_WORDS_BASE | {"position"},
}

_QUOTE_CHAR = {"postgres": '"', "mariadb": "`"}


def quote_identifier(name: str, dialect: str) -> str:
    """Quote *name* for *dialect* when it is a reserved word or otherwise non-simple.

    A simple lowercase identifier that is not reserved **for that dialect** is
    returned unquoted, so the generated DDL/DML for every existing model is
    byte-identical. A reserved word (e.g. ``order`` on both dialects, or
    ``position`` on MariaDB only) or a name with uppercase / special characters is
    wrapped in the dialect's quote character — ``"..."`` on Postgres, backticks on
    MariaDB — with any embedded quote doubled. The hand-authored golden SQL quotes
    the same identifiers; the m-sql normalizer preserves that quoting.
    """
    reserved = _RESERVED_WORDS.get(dialect, _RESERVED_WORDS_BASE)
    if _SIMPLE_IDENTIFIER.match(name) and name not in reserved:
        return name
    char = _QUOTE_CHAR.get(dialect, '"')
    return f"{char}{name.replace(char, char * 2)}{char}"


def _column_of_attr(entity: Entity, attr_name: str) -> str:
    """The physical column backing an attribute *name* on *entity*."""
    for attribute in entity.attributes:
        if attribute["name"] == attr_name:
            return attribute["column"]
    raise KeyError(f"{entity.name} has no attribute {attr_name!r} (index reference)")


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
        column_type = _column_type(attribute["type"], attribute.get("maxLength"), dialect)
        parts = [quote_identifier(attribute["column"], dialect), column_type]
        if not attribute.get("nullable", False):
            parts.append("not null")
        columns.append(" ".join(parts))
        if attribute.get("primaryKey", False):
            pk_columns.append(attribute["column"])

    # A valueObject is stored in ONE dialect-mapped `json` column (m-value-object/m-core, Phase
    # 9): the whole embedded composite, not column-flattened. Append its backing
    # column after the scalar attributes (so the Phase 1-8 cases are unaffected).
    for value_object in entity.value_objects:
        column_type = _column_type("json", None, dialect)
        parts = [quote_identifier(value_object["column"], dialect), column_type]
        if not value_object.get("nullable", False):
            parts.append("not null")
        columns.append(" ".join(parts))

    # A temporal entity stores many milestone rows per business key, so the
    # declared primaryKey attribute(s) are NOT unique on their own — the unique
    # physical key is the business key PLUS each as-of dimension's `fromColumn`
    # (the milestone start). Extend the physical primary key accordingly so the
    # DDL admits the milestone chain (m-temporal-read).
    for as_of in entity.as_of_attributes:
        from_column = as_of["fromColumn"]
        if from_column not in pk_columns:
            pk_columns.append(from_column)

    # Emit a UNIQUE constraint for each declared unique index whose columns are
    # NOT exactly the primary key (the PK is already unique via `primary key
    # (...)` below). This lets a model witness a unique-INDEX violation distinct
    # from a PK collision (m-db-error error classification). Existing models declare
    # only PK-backed unique indices, so this is a no-op for them. The guard
    # compares against the PHYSICAL primary key (declared PK + temporal fromColumns
    # appended above), so a temporal entity's full-milestone-key unique index is
    # recognized as PK-backed and not re-emitted.
    for index in entity.definition.get("indices", []):
        if not index.get("unique", False):
            continue
        index_columns = [_column_of_attr(entity, attr_name) for attr_name in index["attributes"]]
        if set(index_columns) == set(pk_columns):
            continue
        quoted = ", ".join(quote_identifier(column, dialect) for column in index_columns)
        columns.append(f"unique ({quoted})")

    if pk_columns:
        quoted_pk = ", ".join(quote_identifier(column, dialect) for column in pk_columns)
        columns.append(f"primary key ({quoted_pk})")

    column_clause = ",\n  ".join(columns)
    return f"create table {quote_identifier(entity.table, dialect)} (\n  {column_clause}\n)"


def _merge_by_column(items: Sequence[dict], key: str = "column") -> list[dict]:
    """Return physical column definitions once, preserving first-seen order."""
    merged: list[dict] = []
    seen: set[str] = set()
    for item in items:
        column = item[key]
        if column in seen:
            continue
        seen.add(column)
        merged.append(copy.deepcopy(item))
    return merged


def _merge_by_name(items: Sequence[dict]) -> list[dict]:
    merged: list[dict] = []
    seen: set[str] = set()
    for item in items:
        name = item["name"]
        if name in seen:
            continue
        seen.add(name)
        merged.append(copy.deepcopy(item))
    return merged


def _physical_table_entity(entities: Sequence[Entity]) -> Entity:
    """Synthesize the physical table shape for entities sharing one table.

    Table-per-hierarchy descriptors may put subtype-specific columns only on the
    subtype entity. DDL is physical, so the shared table must contain the union of
    all columns that any entity mapped to that table can load or query.
    """
    if len(entities) == 1:
        return entities[0]

    definition = copy.deepcopy(entities[0].definition)
    definition["attributes"] = _merge_by_column(
        [attribute for entity in entities for attribute in entity.attributes]
    )
    value_objects = _merge_by_column(
        [value_object for entity in entities for value_object in entity.value_objects]
    )
    if value_objects:
        definition["valueObjects"] = value_objects
    else:
        definition.pop("valueObjects", None)

    as_of_attributes = _merge_by_name(
        [as_of for entity in entities for as_of in entity.as_of_attributes]
    )
    if as_of_attributes:
        definition["asOfAttributes"] = as_of_attributes
    else:
        definition.pop("asOfAttributes", None)

    return Entity(definition=definition)


def ddl_for(model: Model, dialect: str) -> list[str]:
    """Return the ordered DDL statements that create every entity's table.

    One ``CREATE TABLE`` per **distinct table** (a multi-entity descriptor yields
    several). A `table-per-hierarchy` inheritance model maps several entities to
    ONE shared table, so the emitted DDL is the union of every entity mapped to
    that table rather than whichever entity appears first.
    Foreign keys are intentionally omitted: relationships are a query concern
    (navigation/join derivation), and leaving FK constraints out keeps
    fixture-load order unconstrained.
    """
    statements: list[str] = []
    by_table: dict[str, list[Entity]] = {}
    for entity in model.entities:
        by_table.setdefault(entity.table, []).append(entity)
    for entities in by_table.values():
        statements.append(_create_table(_physical_table_entity(entities), dialect))
    return statements


def column_order(entity: Entity) -> Sequence[str]:
    """The descriptor's column order for *entity* (matches DDL + load order).

    Scalar attributes first, then each valueObject's single structured-document
    column — the same order :func:`_create_table` emits, so fixture loading and
    table-state reads stay column-aligned.
    """
    columns = [attribute["column"] for attribute in entity.attributes]
    columns.extend(value_object["column"] for value_object in entity.value_objects)
    return columns
