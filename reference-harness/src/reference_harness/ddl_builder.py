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
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from ._declared_contributor import DeclaredContributor
from .case import Model
from .storage_layout import (
    AttributeContributor,
    ColumnContributor,
    ColumnSlot,
    InheritanceDiscriminator,
    RelationalDocument,
    TableLayout,
    ValueObjectContributor,
    derived_primary_key_index,
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


def _readable_prefix(fields: Sequence[str]) -> str:
    """The readable half of a Physical Index Name, from the facts it is derived over.

    ASCII letters lowercase, digits stay, every maximal run of anything else —
    including the boundary between two fields — becomes one underscore, and the
    result is trimmed. An input keeping nothing at all becomes ``index``.
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
    return "".join(kept) or _EMPTY_PREFIX


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


@dataclass(frozen=True)
class _AuthoredIndex:
    """One authored Index beside the declaring Entity Identity its name is derived
    from.

    The namespace and the local name are kept apart from the canonical spelling
    because the fingerprint hashes the structured identity while the readable
    prefix reads the canonical one.
    """

    namespace: str
    entity: str
    definition: dict[str, Any]

    @property
    def owner(self) -> str:
        """The declaring Entity's canonical name."""
        return self.entity if not self.namespace else f"{self.namespace}.{self.entity}"


def physical_index_name(index: _AuthoredIndex, table: str, dialect: str) -> str:
    """``index``'s derived Physical Index Name on ``table`` for ``dialect``.

    Only the readable prefix is shortened, to whatever the dialect's identifier
    budget leaves once the namespace, the two joining underscores, and the
    never-truncated fingerprint are spent; the trim and the empty-input fallback
    are re-applied afterwards, so a cut landing inside a separator run cannot
    leave a doubled underscore behind. Generated names are ASCII, so a character
    budget and a byte budget are one budget.
    """
    components = [f"{index.owner}.{name}" for name in index.definition["attributes"]]
    marker = _UNIQUE_MARKER[bool(index.definition.get("unique", False))]
    fingerprint = _fingerprint(
        [
            _FINGERPRINT_VERSION,
            table,
            index.namespace,
            index.entity,
            index.definition["name"],
            str(len(components)),
            *components,
            marker,
        ]
    )
    prefix = _readable_prefix([table, index.owner, index.definition["name"], marker])
    budget = max(_MAX_IDENTIFIER_BYTES[dialect] - len(_NAME_NAMESPACE) - len(fingerprint) - 2, 0)
    kept = prefix[:budget].strip("_") or _EMPTY_PREFIX
    return f"{_NAME_NAMESPACE}_{kept}_{fingerprint}"


@dataclass(frozen=True)
class _Declarations:
    """The authored facts DDL still resolves outside the physical layout.

    A layout slot names its contributor and physical answer; the neutral type and
    the ordered logical components of an Index remain declaration facts.
    """

    contributors: Mapping[ColumnContributor, DeclaredContributor]
    primary_key_indices: tuple[tuple[str, dict[str, Any]], ...]
    authored_indices: tuple[_AuthoredIndex, ...]


def _declarations(model: Model) -> _Declarations:
    contributors: dict[ColumnContributor, DeclaredContributor] = {}
    primary_key_indices: list[tuple[str, dict[str, Any]]] = []
    authored_indices: list[_AuthoredIndex] = []
    for entity in model.entities:
        owner = entity.canonical_name
        definition = entity.definition
        for attribute in definition.get("attributes", []) or []:
            contributors[AttributeContributor(owner, attribute["name"])] = DeclaredContributor(
                neutral_type=attribute["type"],
                max_length=attribute.get("maxLength"),
            )
        for value_object in definition.get("valueObjects", []) or []:
            contributors[ValueObjectContributor(owner, value_object["name"])] = DeclaredContributor(
                _DOCUMENT_TYPE
            )
        derived = derived_primary_key_index(definition)
        if derived is not None:
            primary_key_indices.append((owner, derived))
        authored_indices.extend(
            _AuthoredIndex(
                namespace=definition.get("namespace") or "",
                entity=definition["name"],
                definition=index,
            )
            for index in definition.get("indices", []) or []
        )
    return _Declarations(
        contributors=contributors,
        primary_key_indices=tuple(primary_key_indices),
        authored_indices=tuple(authored_indices),
    )


def declared_contributors(model: Model) -> Mapping[ColumnContributor, DeclaredContributor]:
    """Each layout contributor's declared scalar facts.

    A layout slot names its contributor and its physical answer but never a type,
    so every consumer that must spell one — a ``CREATE TABLE`` column, a read's
    typed ``NULL`` placeholder — resolves it here. A top-level value object binds
    into one structured document column whatever its inner members declare. The
    framework-owned discriminator has no declaration and so no entry.
    """
    return _declarations(model).contributors


def _slot_ddl(slot: ColumnSlot, declarations: _Declarations, dialect: str) -> str:
    if isinstance(slot.contributor, InheritanceDiscriminator):
        neutral_type, max_length = _TAG_COLUMN_TYPE, _TAG_COLUMN_MAX_LENGTH
    elif isinstance(slot.contributor, RelationalDocument):
        # A Relational Document Layout's shared Structured Column has no
        # declaration of its own, and carries the document-resident members of
        # every governed row in the same physical type a Value Object occupies.
        neutral_type, max_length = _DOCUMENT_TYPE, None
    else:
        declared = declarations.contributors[slot.contributor]
        neutral_type, max_length = declared.neutral_type, declared.max_length
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
    """One physical table's ``create table``, keyed inline.

    The derived primary-key Index becomes `primary key (...)` here; every
    authored Index is a separate statement instead, so a unique one is a named
    object a violation can report rather than an anonymous table constraint. The
    layout owns the complete slot sequence and effective physical nullability
    (m-storage-layout); this only renders selected values per dialect.
    """
    columns = [_slot_ddl(slot, declarations, dialect) for slot in layout.columns]

    for owner, index in declarations.primary_key_indices:
        index_columns = _index_columns(layout, owner, index)
        if index_columns is None:
            continue
        quoted = ", ".join(quote_identifier(column, dialect) for column in index_columns)
        columns.append(f"primary key ({quoted})")

    column_clause = ",\n  ".join(columns)
    return f"create table {quote_identifier(layout.table, dialect)} (\n  {column_clause}\n)"


def _create_indices(layout: TableLayout, declarations: _Declarations, dialect: str) -> list[str]:
    """Every authored Index this table holds, each under its derived name.

    An Index declared on an ancestor of several table-per-concrete-subtype
    concretes resolves into each of their tables, and the physical table is one
    of the facts the name is derived over, so the repetitions are distinct
    objects rather than a clash.
    """
    statements = []
    for index in declarations.authored_indices:
        index_columns = _index_columns(layout, index.owner, index.definition)
        if index_columns is None:
            continue
        keyword = "create unique index" if index.definition.get("unique", False) else "create index"
        name = quote_identifier(physical_index_name(index, layout.table, dialect), dialect)
        quoted = ", ".join(quote_identifier(column, dialect) for column in index_columns)
        table = quote_identifier(layout.table, dialect)
        statements.append(f"{keyword} {name} on {table} ({quoted})")
    return statements


def ddl_for(model: Model, dialect: str) -> list[str]:
    """Return the ordered DDL statements that create every physical table.

    One ``CREATE TABLE`` per compiled Table Layout, so a `table-per-hierarchy`
    family's shared table is created once with the whole family's slots and each
    `table-per-concrete-subtype` concrete gets its own ancestry-derived table.
    Every authored Index follows as its own named statement, after every table,
    which is the form a generated Schema Delta uses too — the catalogs the two
    leave behind are what a delta cell is graded by. Foreign keys are
    intentionally omitted: relationships are a query concern (navigation/join
    derivation), and leaving FK constraints out keeps fixture-load order
    unconstrained.
    """
    declarations = _declarations(model)
    tables = model.storage_layout.tables
    return [_create_table(layout, declarations, dialect) for layout in tables] + [
        statement
        for layout in tables
        for statement in _create_indices(layout, declarations, dialect)
    ]
