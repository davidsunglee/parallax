"""Derive schema DDL from a model descriptor (dialect-aware).

The neutral-type -> column-type mapping is the m-core table; it lives behind the
dialect (m-dialect). Postgres and MariaDB are the supported dialects
behind the same seam. The harness derives DDL from the descriptor so the database
schema is never authored by hand — it is a function of the metamodel, exactly as
an implementation's would be.

Every authored Index becomes a separately named ``create index`` statement under
its derived Physical Index Name (m-schema-delta), which is what lets a catalog
read after an authored Schema Delta be compared against a catalog read after this
builder ran. The naming rule is re-derived here from the normative statement
rather than shared with any implementation: it is the second oracle a delta cell
is graded against, so a shared derivation would grade the implementation twice.
The interval checks a PostgreSQL temporal table carries inline are named by
m-storage-layout's rule, re-derived here on the same terms.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence

from ._declared_contributor import DeclaredContributor
from .case import Model
from .storage_layout import (
    AttributeContributor,
    ColumnContributor,
    ColumnSlot,
    InheritanceDiscriminator,
    PhysicalIndex,
    RelationalDocument,
    TableLayout,
    ValueObjectContributor,
    is_scalar_collection,
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
    # The embedded-value `json` type maps to Postgres JSONB: a
    # whole valueObject is stored in one structured column rather than
    # column-flattened.
    "json": "jsonb",
}

# m-core neutral type -> MariaDB column type. The
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
        ``char``). An unbounded one casts to Postgres ``text`` and MariaDB ``char``,
        which is that grammar's only unbounded character target.
      * ``json`` diverges for the same reason: Postgres casts to its own ``jsonb``
        document type, while MariaDB's ``JSON`` is an alias for ``LONGTEXT`` and is
        no more a legal CAST target than ``LONGTEXT`` itself, so the document
        placeholder casts to ``char`` there too.
      * Every other neutral type reuses the DDL column-type mapping (``int64`` ->
        ``bigint``, ...), which is a legal CAST target on both dialects.

    This is the read-side counterpart of :func:`_column_type`; it exists separately
    because CAST targets and column types are not the same grammar (the divergences
    above).
    """
    decimal = _DECIMAL_RE.match(neutral_type)
    if decimal:
        return f"decimal({decimal.group(1)},{decimal.group(2)})"
    if dialect == "mariadb" and neutral_type in ("string", _DOCUMENT_TYPE):
        return f"char({max_length})" if neutral_type == "string" and max_length else "char"
    if neutral_type == "string":
        return f"varchar({max_length})" if max_length else "text"
    return _column_type(neutral_type, max_length, dialect)


# A framework-owned discriminator is not a declared attribute (m-inheritance), so
# the harness fixes its own physical type; DDL is never asserted byte-exact.
_TAG_COLUMN_TYPE = "string"
_TAG_COLUMN_MAX_LENGTH = 32

# A top-level valueObject occupies ONE dialect-mapped `json` column
# (m-value-object/m-core): the whole embedded composite, not column-flattened.
_DOCUMENT_TYPE = "json"


# The longest identifier each database stores without truncating it (m-dialect).
# Only a DERIVED name has to fit; an authored table or column name is spelled as
# the model declares it.
_MAX_IDENTIFIER_BYTES = {"postgres": 63, "mariadb": 64}

# The Physical Index Name grammar (m-schema-delta): `pxi_<readable>_<fingerprint>`.
_NAME_NAMESPACE = "pxi"
_FINGERPRINT_VERSION = "pxi-1"
_FINGERPRINT_HEX = 32
_EMPTY_PREFIX = "index"
_UNIQUE_MARKER = {True: "unique", False: "non-unique"}


def _readable_prefix(fields: Sequence[str], empty: str = _EMPTY_PREFIX) -> str:
    """The readable half of a derived name, from the facts it is derived over.

    ASCII letters lowercase, digits stay, every maximal run of anything else —
    including the boundary between two fields — becomes one underscore, and the
    result is trimmed. An input keeping nothing at all becomes ``empty``.
    """
    kept: list[str] = []
    separated = False
    for character in " ".join(fields):
        if character.isascii() and character.isalnum():
            if separated and kept:
                kept.append("_")
            separated = False
            kept.append(character.lower())
        else:
            separated = True
    return "".join(kept) or empty


def _fingerprint(fields: Sequence[str]) -> str:
    """The first 128 bits of SHA-256 over a versioned, length-prefixed field
    sequence, as lowercase hexadecimal.

    Length-prefixing is what makes the digest a function of the field STRUCTURE:
    no two distinct sequences concatenate to the same bytes.
    """
    digest = hashlib.sha256()
    for field_value in fields:
        encoded = field_value.encode("utf-8")
        digest.update(len(encoded).to_bytes(4, "big"))
        digest.update(encoded)
    return digest.hexdigest()[:_FINGERPRINT_HEX]


def physical_index_name(index: PhysicalIndex, table: str, dialect: str) -> str:
    """``index``'s derived Physical Index Name on ``table`` for ``dialect``.

    The fingerprint hashes the Attribute behind each physical column — the
    authored components, then a temporal table's axis ends — so a non-temporal
    Index's name is a function of its authored components alone. Only the
    readable prefix is shortened, to whatever the dialect's identifier budget
    leaves once the namespace, the two joining underscores, and the
    never-truncated fingerprint are spent; the trim and the empty-input fallback
    are re-applied afterwards, so a cut landing inside a separator run cannot
    leave a doubled underscore behind. Generated names are ASCII, so a character
    budget and a byte budget are one budget.
    """
    declaration = index.declaration
    attributes = [f"{attribute.owner}.{attribute.name}" for attribute in index.column_attributes]
    marker = _UNIQUE_MARKER[declaration.unique]
    fingerprint = _fingerprint(
        [
            _FINGERPRINT_VERSION,
            table,
            declaration.namespace,
            declaration.entity,
            declaration.name,
            str(len(attributes)),
            *attributes,
            marker,
        ]
    )
    prefix = _readable_prefix([table, declaration.owner, declaration.name, marker])
    budget = max(_MAX_IDENTIFIER_BYTES[dialect] - len(_NAME_NAMESPACE) - len(fingerprint) - 2, 0)
    kept = prefix[:budget].strip("_") or _EMPTY_PREFIX
    return f"{_NAME_NAMESPACE}_{kept}_{fingerprint}"


# The temporal constraint name grammar (m-storage-layout):
# `pxc_<kind>_<readable-table>_<fingerprint>`, 63 bytes on every dialect.
_CONSTRAINT_NAMESPACE = "pxc"
_CONSTRAINT_VERSION = "pxc-1"
_CONSTRAINT_NAME_BYTES = 63
_CONSTRAINT_EMPTY_PREFIX = "table"
_INTERVAL_CHECK_KIND = {"transaction-time": "tx", "valid-time": "valid"}
_EXCLUSION_PREREQUISITE = "create extension if not exists btree_gist"
"""PostgreSQL's GiST equality operators for an exclusion's scalar key columns."""


def temporal_constraint_name(
    table: str, kind: str, groups: Sequence[tuple[str, Sequence[str]]]
) -> str:
    """A temporal constraint's derived name on ``table``.

    The fingerprint hashes the table, the kind, and each operand group — its
    semantics and its ordered columns, each group behind its count.
    """
    fields = [_CONSTRAINT_VERSION, table, kind, str(len(groups))]
    for semantics, columns in groups:
        fields.extend((semantics, str(len(columns)), *columns))
    fingerprint = _fingerprint(fields)
    budget = _CONSTRAINT_NAME_BYTES - len(_CONSTRAINT_NAMESPACE) - len(kind) - len(fingerprint) - 3
    prefix = _readable_prefix([table], _CONSTRAINT_EMPTY_PREFIX)
    kept = prefix[:budget].strip("_") or _CONSTRAINT_EMPTY_PREFIX
    return f"{_CONSTRAINT_NAMESPACE}_{kind}_{kept}_{fingerprint}"


def interval_check_name(table: str, kind: str, start: str, end: str) -> str:
    """The interval check ``start < end``'s derived name on ``table``."""
    return temporal_constraint_name(table, kind, [("lt", [start, end])])


def declared_contributors(model: Model) -> Mapping[ColumnContributor, DeclaredContributor]:
    """Each layout contributor's declared scalar facts.

    A layout slot names its contributor and its physical answer but never a type,
    so every consumer that must spell one — a ``CREATE TABLE`` column, a read's
    typed ``NULL`` placeholder — resolves it here. A top-level value object binds
    into one structured document column whatever its inner members declare. The
    framework-owned discriminator has no declaration and so no entry, and a scalar
    collection binds into one structured document column of its elements.
    """
    contributors: dict[ColumnContributor, DeclaredContributor] = {}
    for entity in model.entities:
        owner = entity.canonical_name
        definition = entity.definition
        for attribute in definition.get("attributes", []) or []:
            contributors[AttributeContributor(owner, attribute["name"])] = (
                DeclaredContributor(_DOCUMENT_TYPE, element_type=attribute["type"])
                if is_scalar_collection(attribute)
                else DeclaredContributor(
                    neutral_type=attribute["type"],
                    max_length=attribute.get("maxLength"),
                )
            )
        for value_object in definition.get("valueObjects", []) or []:
            contributors[ValueObjectContributor(owner, value_object["name"])] = DeclaredContributor(
                _DOCUMENT_TYPE
            )
    return contributors


def slot_neutral_type(
    slot: ColumnSlot, declarations: Mapping[ColumnContributor, DeclaredContributor]
) -> str:
    """The neutral type *slot*'s column is declared with, including the
    framework-owned discriminator and shared Structured Column that no
    contributor declaration types."""
    return _slot_declaration(slot, declarations)[0]


def _slot_declaration(
    slot: ColumnSlot, declarations: Mapping[ColumnContributor, DeclaredContributor]
) -> tuple[str, int | None]:
    if isinstance(slot.contributor, InheritanceDiscriminator):
        return _TAG_COLUMN_TYPE, _TAG_COLUMN_MAX_LENGTH
    if isinstance(slot.contributor, RelationalDocument):
        # A Relational Document Layout's shared Structured Column has no
        # declaration of its own, and carries the document-resident members of
        # every governed row in the same physical type a Value Object occupies.
        return _DOCUMENT_TYPE, None
    declared = declarations[slot.contributor]
    return declared.neutral_type, declared.max_length


def _slot_ddl(
    slot: ColumnSlot, declarations: Mapping[ColumnContributor, DeclaredContributor], dialect: str
) -> str:
    neutral_type, max_length = _slot_declaration(slot, declarations)
    parts = [
        quote_identifier(slot.column, dialect),
        _column_type(neutral_type, max_length, dialect),
    ]
    if not slot.effective_nullable:
        parts.append("not null")
    return " ".join(parts)


def _columns(slots: Sequence[ColumnSlot], dialect: str) -> str:
    return ", ".join(quote_identifier(slot.column, dialect) for slot in slots)


def _interval_checks(layout: TableLayout, dialect: str) -> list[str]:
    """The PostgreSQL interval check of each of ``layout``'s As-Of Axes."""
    clauses = []
    for axis in layout.temporal_axes:
        start, end = axis.start.column, axis.end.column
        name = interval_check_name(layout.table, _INTERVAL_CHECK_KIND[axis.dimension], start, end)
        clauses.append(
            f"constraint {quote_identifier(name, dialect)} check "
            f"({quote_identifier(start, dialect)} < {quote_identifier(end, dialect)})"
        )
    return clauses


def _exclusion(layout: TableLayout, dialect: str) -> str:
    """The PostgreSQL non-overlap exclusion over ``layout``'s logical key.

    The logical key is the primary key without the axis ends it derives from
    them — the root's key Attributes, never the table-per-hierarchy tag — and
    each axis contributes one half-open range in canonical axis order.
    """
    ends = set(layout.axis_ends)
    logical = [slot.column for slot in layout.physical_primary_key if slot not in ends]
    ranges = [(axis.start.column, axis.end.column) for axis in layout.temporal_axes]
    name = temporal_constraint_name(
        layout.table,
        "excl",
        [("eq", logical), *(("overlap", [start, end]) for start, end in ranges)],
    )
    operands = [f"{quote_identifier(column, dialect)} with =" for column in logical]
    operands.extend(
        f"tstzrange({quote_identifier(start, dialect)}, {quote_identifier(end, dialect)}) with &&"
        for start, end in ranges
    )
    return (
        f"constraint {quote_identifier(name, dialect)} exclude using gist ({', '.join(operands)})"
    )


def _create_table(
    layout: TableLayout, declarations: Mapping[ColumnContributor, DeclaredContributor], dialect: str
) -> str:
    """One physical table's ``create table``, keyed inline.

    The physical primary key becomes `primary key (...)` here; every authored
    Index is a separate statement instead, so a unique one is a named object a
    violation can report rather than an anonymous table constraint. The layout
    owns the complete slot sequence, the key, the axes, and effective physical
    nullability (m-storage-layout); this only renders selected values per
    dialect. Only PostgreSQL names a temporal table's primary key and carries its
    interval checks and non-overlap exclusion: MariaDB's generated tables enforce
    no temporal constraint natively.
    """
    columns = [_slot_ddl(slot, declarations, dialect) for slot in layout.columns]
    constrained = dialect == "postgres" and bool(layout.temporal_axes)
    key = layout.physical_primary_key
    if key:
        named = ""
        if constrained:
            name = temporal_constraint_name(
                layout.table, "pk", [("unique", [slot.column for slot in key])]
            )
            named = f"constraint {quote_identifier(name, dialect)} "
        columns.append(f"{named}primary key ({_columns(key, dialect)})")
    if constrained:
        columns.extend(_interval_checks(layout, dialect))
        columns.append(_exclusion(layout, dialect))

    column_clause = ",\n  ".join(columns)
    return f"create table {quote_identifier(layout.table, dialect)} (\n  {column_clause}\n)"


def _create_indices(layout: TableLayout, dialect: str) -> list[str]:
    """Every authored Index this table holds, each under its derived name.

    An Index declared on an ancestor of several table-per-concrete-subtype
    concretes resolves into each of their tables, and the physical table is one
    of the facts the name is derived over, so the repetitions are distinct
    objects rather than a clash.
    """
    statements = []
    table = quote_identifier(layout.table, dialect)
    for index in layout.secondary_indices:
        keyword = "create unique index" if index.declaration.unique else "create index"
        name = quote_identifier(physical_index_name(index, layout.table, dialect), dialect)
        statements.append(f"{keyword} {name} on {table} ({_columns(index.columns, dialect)})")
    return statements


def ddl_for(model: Model, dialect: str) -> list[str]:
    """Return the ordered DDL statements that create every physical table.

    One ``CREATE TABLE`` per compiled Table Layout, so a `table-per-hierarchy`
    family's shared table is created once with the whole family's slots and each
    `table-per-concrete-subtype` concrete gets its own ancestry-derived table.
    On PostgreSQL the exclusion prerequisite precedes the tables whenever one is
    temporal. Every authored Index follows as its own named statement, after every table,
    which is the form a generated Schema Delta uses too — the catalogs the two
    leave behind are what a delta cell is graded by. Foreign keys are
    intentionally omitted: relationships are a query concern (navigation/join
    derivation), and leaving FK constraints out keeps fixture-load order
    unconstrained.
    """
    declarations = declared_contributors(model)
    tables = model.storage_layout.tables
    created = [_create_table(layout, declarations, dialect) for layout in tables]
    prerequisite = (
        [_EXCLUSION_PREREQUISITE]
        if dialect == "postgres" and any(layout.temporal_axes for layout in tables)
        else []
    )
    return (
        prerequisite
        + created
        + [statement for layout in tables for statement in _create_indices(layout, dialect)]
    )
