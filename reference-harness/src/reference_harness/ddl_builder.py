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
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .case import Entity, Model
from .storage_layout import (
    AttributeContributor,
    ColumnContributor,
    ColumnSlot,
    InheritanceDiscriminator,
    TableLayout,
    ValueObjectContributor,
)

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
# caught by the regex regardless. It is a non-normative harness fix bringing the
# harness into line with the already-normative per-dialect rule (m-dialect), and
# introduces no new normative surface.
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


def placeholder_cast_type(neutral_type: str, max_length: int | None, dialect: str) -> str:
    """The ``cast(null as <type>)`` target type for a table-per-concrete-subtype
    ``union all`` NULL placeholder (m-sql), per dialect (m-dialect).

    A column not applicable to a union branch is projected as ``cast(null as <type>)``
    in the column's declared type, so the union's result column types resolve
    deterministically rather than defaulting to an untyped ``NULL`` (m-sql). The
    target-type *spelling* is a dialect decision owned by m-dialect and DIVERGES from
    the DDL column type for strings:

      * ``decimal(p, s)`` is identical on both dialects.
      * A bounded ``string`` casts to Postgres ``varchar(n)`` but MariaDB ``char(n)`` —
        MariaDB's ``CAST`` target grammar does NOT accept ``varchar`` (it uses
        ``char``), whereas the *column* type is ``varchar(n)`` on both. An unbounded
        string casts to ``text`` (a legal CAST target on both).
      * Every other neutral type reuses the DDL column-type mapping (``int64`` ->
        ``bigint``, ...), which is a legal CAST target on both dialects.

    This is the read-side counterpart of :func:`_column_type`; it exists separately
    because CAST targets and column types are not the same grammar (the string
    divergence above).
    """
    decimal = _DECIMAL_RE.match(neutral_type)
    if decimal:
        return f"decimal({decimal.group(1)},{decimal.group(2)})"
    if neutral_type == "string":
        if dialect == "mariadb":
            return f"char({max_length})" if max_length else "text"
        return f"varchar({max_length})" if max_length else "text"
    return _column_type(neutral_type, max_length, dialect)


# A framework-owned discriminator is not a declared attribute (m-inheritance), so
# the harness fixes its own physical type; DDL is never asserted byte-exact.
_TAG_COLUMN_TYPE = "string"
_TAG_COLUMN_MAX_LENGTH = 32

# A top-level valueObject occupies ONE dialect-mapped `json` column
# (m-value-object/m-core): the whole embedded composite, not column-flattened.
_DOCUMENT_TYPE = "json"


@dataclass(frozen=True)
class _Declarations:
    """The authored facts DDL still resolves outside the physical layout.

    A layout slot names its contributor and physical answer; the neutral type and
    the ordered logical components of a unique Index remain declaration facts.
    """

    types: Mapping[ColumnContributor, tuple[str, int | None]]
    unique_indices: tuple[tuple[str, dict[str, Any]], ...]


def _declarations(model: Model) -> _Declarations:
    types: dict[ColumnContributor, tuple[str, int | None]] = {}
    unique_indices: list[tuple[str, dict[str, Any]]] = []
    for entity in model.entities:
        owner = entity.canonical_name
        definition = entity.definition
        for attribute in definition.get("attributes", []) or []:
            types[AttributeContributor(owner, attribute["name"])] = (
                attribute["type"],
                attribute.get("maxLength"),
            )
        for value_object in definition.get("valueObjects", []) or []:
            types[ValueObjectContributor(owner, value_object["name"])] = (_DOCUMENT_TYPE, None)
        unique_indices.extend(
            (owner, index)
            for index in definition.get("indices", []) or []
            if index.get("unique", False)
        )
    return _Declarations(types=types, unique_indices=tuple(unique_indices))


def contributor_types(model: Model) -> Mapping[ColumnContributor, tuple[str, int | None]]:
    """Each layout contributor's declared neutral type and length bound.

    A layout slot names its contributor and its physical answer but never a type,
    so every consumer that must spell one — a ``CREATE TABLE`` column, a read's
    typed ``NULL`` placeholder — resolves it here. A top-level value object binds
    into one structured document column whatever its inner members declare. The
    framework-owned discriminator has no declaration and so no entry.
    """
    return _declarations(model).types


def _slot_ddl(slot: ColumnSlot, declarations: _Declarations, dialect: str) -> str:
    if isinstance(slot.contributor, InheritanceDiscriminator):
        neutral_type, max_length = _TAG_COLUMN_TYPE, _TAG_COLUMN_MAX_LENGTH
    else:
        neutral_type, max_length = declarations.types[slot.contributor]
    parts = [
        quote_identifier(slot.column, dialect),
        _column_type(neutral_type, max_length, dialect),
    ]
    if not slot.effective_nullable:
        parts.append("not null")
    return " ".join(parts)


def _index_columns(layout: TableLayout, owner: str, index: Mapping[str, Any]) -> list[str] | None:
    """One declared Index's physical columns, or absent when it names another table.

    An Index stays an ordered declaration of logical Attribute names local to its
    declaring Entity (m-storage-layout), so each component resolves through the
    layout's contributor lookup rather than a second column derivation.
    """
    slots = [layout.contribution(AttributeContributor(owner, name)) for name in index["attributes"]]
    if all(slot is None for slot in slots):
        return None
    if any(slot is None for slot in slots):
        raise KeyError(f"index {index['name']!r} spans table {layout.table!r} only partially")
    return [slot.column for slot in slots if slot is not None]


def _create_table(layout: TableLayout, declarations: _Declarations, dialect: str) -> str:
    """One physical table's ``create table``, rendered from its canonical layout.

    The layout already owns the complete slot sequence, effective physical
    nullability, and the model-key-plus-temporal-start physical primary key
    (m-storage-layout); this only renders those selected values per dialect.
    """
    columns = [_slot_ddl(slot, declarations, dialect) for slot in layout.columns]
    pk_columns = [slot.column for slot in layout.physical_primary_key]

    # A UNIQUE constraint is emitted for each declared unique index whose columns
    # are NOT exactly the physical primary key (already enforced by `primary key
    # (...)`), so a model can witness a unique-INDEX violation distinct from a PK
    # collision (m-db-error error classification).
    for owner, index in declarations.unique_indices:
        index_columns = _index_columns(layout, owner, index)
        if index_columns is None or set(index_columns) == set(pk_columns):
            continue
        quoted = ", ".join(quote_identifier(column, dialect) for column in index_columns)
        columns.append(f"unique ({quoted})")

    if pk_columns:
        quoted_pk = ", ".join(quote_identifier(column, dialect) for column in pk_columns)
        columns.append(f"primary key ({quoted_pk})")

    column_clause = ",\n  ".join(columns)
    return f"create table {quote_identifier(layout.table, dialect)} (\n  {column_clause}\n)"


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


def _merge_by_name(items: Sequence[dict], key: str = "name") -> list[dict]:
    merged: list[dict] = []
    seen: set[str] = set()
    for item in items:
        name = item[key]
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

    definition = copy.deepcopy(entities[0].runtime_facts)
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

    as_of_axes = _merge_by_name(
        [as_of for entity in entities for as_of in entity.runtime_facts.get("asOfAxes", [])],
        key="dimension",
    )
    if as_of_axes:
        definition["asOfAxes"] = as_of_axes
    else:
        definition.pop("asOfAxes", None)

    return Entity(definition=definition)


def ddl_for(model: Model, dialect: str) -> list[str]:
    """Return the ordered DDL statements that create every physical table.

    One ``CREATE TABLE`` per compiled Table Layout, so a `table-per-hierarchy`
    family's shared table is created once with the whole family's slots and each
    `table-per-concrete-subtype` concrete gets its own ancestry-derived table.
    Foreign keys are intentionally omitted: relationships are a query concern
    (navigation/join derivation), and leaving FK constraints out keeps
    fixture-load order unconstrained.
    """
    declarations = _declarations(model)
    return [_create_table(layout, declarations, dialect) for layout in model.storage_layout.tables]


def _entities_by_table(model: Model) -> dict[str, list[Entity]]:
    """Group the model's ROW-OWNING entities by physical table.

    Abstract inheritance nodes (root / abstract-subtype) are tableless and rowless
    (m-inheritance), so they are excluded — a `table-per-hierarchy` family's shared
    table is the union of its concrete subtypes, and a `table-per-concrete-subtype`
    family maps each concrete subtype to its own table.
    """
    by_table: dict[str, list[Entity]] = {}
    for entity in model.entities:
        if entity.is_abstract:
            continue
        by_table.setdefault(entity.table, []).append(entity)
    return by_table


def physical_entities_by_table(model: Model) -> dict[str, Entity]:
    """Map each physical table to the synthesized entity carrying its full column set.

    For a `table-per-hierarchy` shared table this is the union of every concrete
    subtype mapped to it (so a table-state read projects the whole physical row,
    not just one subtype's columns); for an ordinary or `table-per-concrete-subtype`
    table it is the single entity that owns it.
    """
    return {
        table: _physical_table_entity(entities)
        for table, entities in _entities_by_table(model).items()
    }


def column_order(entity: Entity) -> Sequence[str]:
    """The descriptor's column order for *entity* (matches DDL + load order).

    Scalar attributes first, then each valueObject's single structured-document
    column — the same order :func:`_create_table` emits, so fixture loading and
    table-state reads stay column-aligned.
    """
    columns = [attribute["column"] for attribute in entity.attributes]
    columns.extend(value_object["column"] for value_object in entity.value_objects)
    return columns
