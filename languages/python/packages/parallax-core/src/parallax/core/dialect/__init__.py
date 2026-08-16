"""``parallax.core.dialect`` enforcement scope (m-dialect).

The pure, driver-free dialect strategy — the single home of every
dialect-specific decision (`m-dialect`): identifier quoting, NULL ordering,
row-limit rendering, optimizer fences, shared-read-lock application, the neutral-type → column-type
mapping, the structured-document extraction / typed-cast forms, the bytes
projection shape, the canonical `?` → driver placeholder translation, the
infinity representation, and the SQLSTATE → neutral-category table (`m-db-error`).
It performs no I/O and imports no driver. ``m-dialect`` depends only on ``m-core``.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, Literal, cast

from parallax.core.base import (
    SQL_NULL,
    Boolean,
    Bytes,
    Date,
    Decimal,
    DocumentRead,
    Float32,
    Float64,
    Int32,
    Int64,
    Json,
    NeutralType,
    PresentDocument,
    String,
    Time,
    Timestamp,
    Uuid,
    detach_json_container,
    is_document_value,
)

__all__ = [
    "INFINITY",
    "POSTGRES",
    "Dialect",
    "DocumentAssignment",
    "DocumentLeafAssignment",
    "DocumentValueAssignment",
    "LockMode",
    "dialect_for",
    "projection_result_key",
]

LockMode = Literal["locking", "optimistic"]


def projection_result_key(column: str, neutral_type: NeutralType) -> str:
    """The driver-row key produced by the canonical projection of one Column."""
    return f"{column}_hex" if isinstance(neutral_type, Bytes) else column


@dataclass(frozen=True, slots=True)
class DocumentLeafAssignment:
    """One encoded leaf value assigned relative to a document expression."""

    path: tuple[str, ...]
    value: object


@dataclass(frozen=True, slots=True)
class DocumentValueAssignment:
    """One complete encoded occurrence document assigned relative to a document
    expression — the object a ``one`` holds, the ordered array a ``many`` holds, or
    ``None`` for JSON null."""

    path: tuple[str, ...]
    value: object


type DocumentAssignment = DocumentLeafAssignment | DocumentValueAssignment
"""One assigned path and the complete encoded value that lands there.

The two nodes name the two kinds of position a Parallax assignment reaches — a
leaf and a whole occurrence — and this seam renders them identically, because
both hand it one already-encoded value for one absolute path. The list is flat:
an occurrence carries no children here, since assigning one replaces its subtree
whole rather than reaching inside it.
"""

# A "simple" identifier needs no quoting: lowercase, starts with a letter.
_SIMPLE = re.compile(r"^[a-z][a-z0-9_]*$")

# The neutral infinity sentinel (the open upper bound of a temporal interval,
# m-core); Postgres binds it as native `'infinity'::timestamptz` at the adapter.
INFINITY: Final[str] = "infinity"


def _document_value_bind(value: object) -> object:
    """One assigned document value as the mutation expression's hole takes it.

    A composite crosses the seam as the portable document it is, so the adapter
    hands it to the driver's structured-document wrapper; a JSON scalar, which no
    structural authoring form distinguishes from an ordinary scalar bind, crosses
    as the JSON text both dialects' value expressions parse (`m-case-format`).
    Serializing it here is what keeps a key order and a separator convention out
    of every golden — a scalar has neither.
    """
    if isinstance(value, (dict, list)):
        return cast("object", value)
    return json.dumps(value)


@dataclass(frozen=True, slots=True)
class Dialect:
    """One database's pure SQL strings and parse rules (m-dialect)."""

    name: str
    # Names that are reserved words for this dialect and must be quoted even
    # though they are otherwise "simple". The concrete list is per-dialect
    # (m-dialect); a shared normative artifact is a deferred follow-on.
    reserved: frozenset[str]
    quote_char: str
    # SQLSTATE / native code -> neutral m-db-error category.
    error_codes: dict[str, str]

    # -- identifiers ------------------------------------------------------- #
    def quote(self, identifier: str) -> str:
        """Quote ``identifier`` iff it is reserved or non-simple for this dialect."""
        if _SIMPLE.match(identifier) and identifier not in self.reserved:
            return identifier
        q = self.quote_char
        return f"{q}{identifier}{q}"

    def qualified(self, alias: str, column: str) -> str:
        """An alias-qualified column reference (`t0.col` / `t0."order"`)."""
        return f"{alias}.{self.quote(column)}"

    # -- projections ------------------------------------------------------- #
    def project(
        self,
        alias: str,
        column: str,
        neutral_type: NeutralType,
        *,
        result_key: str | None = None,
    ) -> tuple[str, list[object]]:
        """The select-list expression (and any projection-introduced binds) for a column.

        A `bytes` column projects the hex-encoded text so the wire value is stable
        (`encode(t0.col, ?) col_hex`, bind `hex`); every other column projects the
        plain alias-qualified reference with no bind.
        """
        output = projection_result_key(column, neutral_type) if result_key is None else result_key
        if isinstance(neutral_type, Bytes):
            return f"encode({self.qualified(alias, column)}, ?) {output}", ["hex"]
        expression = self.qualified(alias, column)
        return (expression if output == column else f"{expression} {output}"), []

    def project_document_read(self, expression: str) -> tuple[str, str]:
        """The adjacent SQL presence/document cells for ``expression``."""
        return f"not {expression} is null", expression

    def parse_document_read(self, presence: object, document: object) -> DocumentRead:
        """Parse one adjacent SQL presence/document pair into its neutral tag.

        The discriminator is consulted first, so the same driver sentinel can
        denote SQL NULL in the false arm and JSON null in the true arm.
        """
        if type(presence) is not bool:
            raise ValueError(
                "a document-read presence projection must be a SQL boolean, "
                f"got {type(presence).__name__}"
            )
        if not presence:
            return SQL_NULL
        detached = detach_json_container(document)
        if not is_document_value(detached):
            raise ValueError(
                "a present structured-document result must be a portable JSON value, "
                f"got {type(document).__name__}"
            )
        return PresentDocument(detached)

    # -- result shaping ---------------------------------------------------- #
    def limit_clause(self) -> str:
        """The row-limit clause (the count rides as a `?` bind)."""
        return "limit ?"

    def optimizer_fence(self) -> tuple[str, list[object]]:
        """Prevent a discriminator-filtered derived table from being flattened."""
        return "offset 0", []

    def null_order(
        self,
        column_sql: str,
        direction: Literal["asc", "desc"],
        placement: Literal["first", "last"],
    ) -> str:
        """One WHOLE ordering-key term placing NULLs where *placement* asks.

        The m-dialect Null Placement seam, used for every ordering key over a
        NULLABLE attribute — a user-authored `orderBy` Sort Key and the
        descriptor-`orderBy` relationship ordering alike (a non-nullable key renders
        the plain term without consulting the dialect, `m-sql`).

        The return value is the complete term text, including any comma-joined
        LEADING rank term a dialect needs: Postgres compensates with a
        `nulls first`/`nulls last` suffix while MariaDB has no such syntax and
        compensates with a leading boolean rank term instead, and no caller composes
        or splits either form. Where the dialect's native placement already answers
        the request it returns the plain term — a deliberate lowering decision, not
        an omission.
        """
        if (direction, placement) in (("asc", "last"), ("desc", "first")):
            return f"{column_sql} {direction}"
        return f"{column_sql} {direction} nulls {placement}"

    # -- read lock --------------------------------------------------------- #
    def read_lock_suffix(self, root_alias: str) -> str:
        """The shared-row-lock suffix for an in-transaction object find."""
        return f"for share of {root_alias}"

    # -- structured documents (m-value-object) ----------------------------- #
    def nested_extract(self, document: str, segments: tuple[str, ...]) -> tuple[str, list[object]]:
        """The document text-extraction expression and its per-segment path binds.

        ``document`` is an ALREADY-RENDERED document-column reference, not an
        ``(alias, column)`` pair: how that reference is spelled is the caller's
        decision, because it differs by statement kind — a read qualifies it
        (`t0.address`) while a write's bare predicate does not (`address`,
        m-sql rule 1's unaliased DML shape) — and by what it addresses (an
        unnested element's `t1.value` is always alias-qualified, since the
        subquery declares that alias itself).
        """
        holes = ", ".join(["?"] * len(segments))
        return (f"jsonb_extract_path_text({document}, {holes})", list(segments))

    def nested_cast(self, extraction: str, neutral_type: NeutralType) -> str:
        """Cast a text extraction to its declared type before comparing, where the
        type's comparison casts at all.

        Two reasons a type casts, and the table below carries both: the **numeric
        family** casts because its document spelling does not compare in value order as
        text (`'10'` is less than `'9'`), and **`boolean`** casts because the two
        dialects' extractions do not yield the same characters for it —
        `jsonb_extract_path_text` returns `true`/`false` where MariaDB's `json_value`
        returns `1`/`0` — so no single bound text matches on both. Every other
        declarable type compares as the extracted text, because the canonical spelling
        `m-document-codec` writes already equates and orders correctly as text.
        """
        match neutral_type:
            case Decimal(precision, scale):
                return f"cast({extraction} as decimal({precision}, {scale}))"
            case Int32() | Int64():
                return f"cast({extraction} as bigint)"
            case Float32():
                return f"cast({extraction} as real)"
            case Float64():
                return f"cast({extraction} as double precision)"
            case Boolean():
                return f"cast({extraction} as boolean)"
            case _:
                return extraction  # a text-compared type — compare the extraction

    def array_guard(self, document: str, segments: tuple[str, ...]) -> tuple[str, list[object]]:
        """The array-type guard fragment for a `multiplicity: many` value-object
        member (m-sql "To-many — exists / notExists and any-element predicates",
        abbreviated `<arr>`): the strict `jsonb_array_elements` ERRORS on a
        non-array argument, so the array is reached through a `case` that yields
        the extracted value only when `jsonb_typeof` confirms it IS a JSON array,
        an empty `[]` jsonb literal otherwise — collapsing a NULL column, a
        missing key, a JSON `null`, a JSON scalar, and a JSON object alike to
        zero elements (m-predicate absence collapse). ``segments`` is bound
        TWICE — the guard's own `jsonb_typeof` probe, then the `then` branch's
        re-extraction — in the same order every other path bind rides (rule 4).
        An empty ``segments`` (the value object's own top-level `many` column IS
        the array, no further descent) needs no `jsonb_extract_path` call at all;
        the guard then probes the plain column reference directly.

        ``document`` is an ALREADY-RENDERED document-column reference, for the
        same reason :meth:`nested_extract` takes one.
        """
        if segments:
            holes = ", ".join(["?"] * len(segments))
            extract = f"jsonb_extract_path({document}, {holes})"
            path_binds: list[object] = list(segments)
        else:
            extract = document
            path_binds = []
        fragment = f"case when jsonb_typeof({extract}) = ? then {extract} else cast(? as jsonb) end"
        return fragment, [*path_binds, "array", *path_binds, "[]"]

    # -- structured documents (m-storage-layout) --------------------------- #
    def document_path(self, segments: Sequence[str]) -> str:
        """The bind value addressing ``segments`` inside a document, for a mutation.

        A dialect decision of its own, and it diverges from the extraction path
        binds above: Postgres `jsonb_set` takes ONE text-array path (`{a,b}`)
        where `jsonb_extract_path_text` takes one bind per segment, and MariaDB
        `json_set` takes the same `$.a.b` JSON-path string its `json_value`
        extraction does.
        """
        return "{" + ",".join(segments) + "}"

    def document_mutation(
        self, document: str, assignments: Sequence[DocumentAssignment]
    ) -> tuple[str, list[object]]:
        """The `SET` expression assigning each path of ``assignments`` inside
        ``document``, and its ordered binds (m-dialect *Document mutation-expression
        form*).

        ``document`` is an ALREADY-RENDERED Structured Column reference, for the
        same reason :meth:`nested_extract` takes one. Every node assigns one
        complete encoded value at one absolute path — a leaf's spelling, an
        occurrence's whole document, or JSON null — so the expression is one call
        per assigned path and its binds read path, value, path, value. The
        sequence is applied left to right in canonical logical placement order,
        which `m-sql` fixes and this seam MUST NOT reorder, deduplicate, or
        merge.

        The value hole is a per-dialect **expression**, not a bare `?`: Postgres
        resolves a bare parameter there to `jsonb_set`'s declared `jsonb` and
        rejects every scalar bind, while MariaDB accepts a scalar but silently
        escapes a composite into a string. `cast(? as jsonb)` and
        `json_extract(?, '$')` are the two expressions that accept one authored
        bind form on both engines. That form is the document itself for a
        composite — the adapter hands it to the driver's structured-document
        wrapper — and the value's JSON **text** for a scalar, which no structural
        authoring form could distinguish from an ordinary scalar bind
        (`m-case-format`).
        """
        expression = document
        binds: list[object] = []
        for assignment in assignments:
            expression = f"jsonb_set({expression}, ?, cast(? as jsonb))"
            binds.extend(
                [self.document_path(assignment.path), _document_value_bind(assignment.value)]
            )
        return expression, binds

    def document_equals(self, left: str, right: str) -> str:
        """The predicate deciding whether two documents are structurally equal.

        A dialect decision because the two engines do not agree by default:
        Postgres `jsonb` normalizes on storage — whitespace removed, duplicate
        keys reduced, numerics canonicalized — so `=` is already structural,
        while MariaDB `json` is a `longtext` alias whose `=` is a TEXT comparison
        sensitive to key order and whitespace, and needs `json_equals`. A
        consumer comparing documents MUST obtain the comparison here, or one
        assertion would mean different things on the two engines.
        """
        return f"{left} = {right}"

    # -- placeholders ------------------------------------------------------ #
    def to_driver_sql(self, canonical_sql: str) -> str:
        """Translate the canonical `?` placeholders to this driver's form (`%s`)."""
        return canonical_sql.replace("?", "%s")

    def from_driver_sql(self, driver_sql: str) -> str:
        """The reverse of :meth:`to_driver_sql` — recover canonical `?`-placeholder
        SQL text from this driver's own form.

        Used only where a caller must REPORT a statement it did not itself lower
        (the conformance engine's materializing-predicate-write capture: its
        per-row writes are query-result-dependent, so
        there is no independent pure re-lowering to draw canonical emission text
        from — the executed driver SQL is the only source, and every OTHER
        emission this engine reports is canonical text, so a captured statement
        must round-trip back before joining them). Production code never calls
        this — it always starts from canonical text and translates outward, never
        back.
        """
        return driver_sql.replace("%s", "?")

    # -- inheritance (m-inheritance / m-sql) -------------------------------- #
    def null_cast(self, neutral_type: NeutralType, max_length: int | None) -> str:
        """The ``CAST`` target-type spelling for a ``NULL`` placeholder column in a
        table-per-concrete-subtype union-all branch (m-sql "table-per-concrete-
        subtype lowering").

        A distinct `m-dialect` decision from :meth:`column_type` (the DDL column
        type), spelled independently rather than delegated: a bounded string casts
        to Postgres ``varchar(n)`` (MariaDB ``char(n)`` — MariaDB's ``CAST`` grammar
        rejects ``varchar``) and an unbounded string to ``text``, matching the DDL
        mapping; a ``decimal`` casts to ``decimal(p, s)`` on every dialect —
        identical to `~parallax.core.sql_gen._predicate`'s nested-extraction cast
        (which reaches it through :meth:`nested_cast`), but
        **not** :meth:`column_type`'s own ``numeric(p, s)`` DDL spelling.
        """
        if isinstance(neutral_type, Decimal):
            return f"decimal({neutral_type.precision}, {neutral_type.scale})"
        return self.column_type(neutral_type, max_length)

    # -- DDL type mapping -------------------------------------------------- #
    def column_type(self, neutral_type: NeutralType, max_length: int | None) -> str:
        """The concrete column type for a neutral type (used by DDL derivation)."""
        match neutral_type:
            case String():
                return f"varchar({max_length})" if max_length is not None else "text"
            case Decimal(precision, scale):
                return f"numeric({precision}, {scale})"
            case Boolean():
                return "boolean"
            case Int32():
                return "integer"
            case Int64():
                return "bigint"
            case Float32():
                return "real"
            case Float64():
                return "double precision"
            case Bytes():
                return "bytea"
            case Date():
                return "date"
            case Time():
                return "time"
            case Timestamp():
                return "timestamptz"
            case Uuid():
                return "uuid"
            case Json():
                return "jsonb"

    # -- errors ------------------------------------------------------------ #
    def classify(self, code: str) -> str | None:
        """The neutral m-db-error category for a native code, or ``None``."""
        return self.error_codes.get(code)


# Postgres reserved words that appear as declared columns in the corpus and so
# must be quoted (m-descriptor-001 witnesses the shared-reserved `order`).
_PG_RESERVED: Final[frozenset[str]] = frozenset(
    {"order", "user", "select", "from", "where", "table", "group", "default", "primary"}
)

POSTGRES: Final[Dialect] = Dialect(
    name="postgres",
    reserved=_PG_RESERVED,
    quote_char='"',
    error_codes={
        "23505": "uniqueViolation",
        "40P01": "deadlock",
        "40001": "deadlock",
        "55P03": "lockWaitTimeout",
    },
)


def dialect_for(name: str) -> Dialect:
    """The pure dialect strategy for ``name`` (postgres is the only concrete one)."""
    if name == "postgres":
        return POSTGRES
    raise ValueError(f"unsupported dialect {name!r}")
