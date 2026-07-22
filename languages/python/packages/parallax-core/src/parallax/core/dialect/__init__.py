"""``parallax.core.dialect`` enforcement scope (m-dialect).

The pure, driver-free dialect strategy — the single home of every
dialect-specific decision (`m-dialect`): identifier quoting, NULL ordering,
row-limit rendering, shared-read-lock application, the neutral-type → column-type
mapping, the structured-document extraction / typed-cast forms, the bytes
projection shape, the canonical `?` → driver placeholder translation, the
infinity representation, and the SQLSTATE → neutral-category table (`m-db-error`).
It performs no I/O and imports no driver. ``m-dialect`` depends only on ``m-core``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final, Literal

__all__ = [
    "INFINITY",
    "POSTGRES",
    "Dialect",
    "LockMode",
    "dialect_for",
]

LockMode = Literal["locking", "optimistic"]

# A "simple" identifier needs no quoting: lowercase, starts with a letter.
_SIMPLE = re.compile(r"^[a-z][a-z0-9_]*$")

# The neutral infinity sentinel (the open upper bound of a temporal interval,
# m-core); Postgres binds it as native `'infinity'::timestamptz` at the adapter.
INFINITY: Final[str] = "infinity"


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
    def project(self, alias: str, column: str, neutral_type: str) -> tuple[str, list[object]]:
        """The select-list expression (and any projection-introduced binds) for a column.

        A `bytes` column projects the hex-encoded text so the wire value is stable
        (`encode(t0.col, ?) col_hex`, bind `hex`); every other column projects the
        plain alias-qualified reference with no bind.
        """
        if neutral_type == "bytes":
            return f"encode({self.qualified(alias, column)}, ?) {column}_hex", ["hex"]
        return self.qualified(alias, column), []

    # -- result shaping ---------------------------------------------------- #
    def limit_clause(self) -> str:
        """The row-limit clause (the count rides as a `?` bind)."""
        return "limit ?"

    def null_order(self, column_sql: str, direction: Literal["asc", "desc"]) -> str:
        """A relationship-ordering term with this dialect's NULLs-last placement.

        Used by the descriptor-`orderBy` relationship ordering (`m-deep-fetch`),
        where the canonical rule sorts NULLs last on every key. A user-authored
        `orderBy` directive renders plain (`m-sql`); it does not go through here.
        """
        if direction == "asc":
            return f"{column_sql} asc"
        return f"{column_sql} desc nulls last"

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

    def nested_cast(self, extraction: str, neutral_type: str) -> str:
        """Cast a text extraction to a non-text declared type before comparing."""
        base = _base_type(neutral_type)
        if base == "decimal":
            inner = neutral_type[len("decimal") :].strip("() ")
            p, s = (part.strip() for part in inner.split(","))
            return f"cast({extraction} as decimal({p}, {s}))"
        target = _CAST_TARGETS.get(base)
        if target is None:
            return extraction  # string / text — compare directly
        return f"cast({extraction} as {target})"

    def array_guard(self, document: str, segments: tuple[str, ...]) -> tuple[str, list[object]]:
        """The array-type guard fragment for a `multiplicity: many` value-object
        member (m-sql "To-many — exists / notExists and any-element predicates",
        abbreviated `<arr>`): the strict `jsonb_array_elements` ERRORS on a
        non-array argument, so the array is reached through a `case` that yields
        the extracted value only when `jsonb_typeof` confirms it IS a JSON array,
        an empty `[]` jsonb literal otherwise — collapsing a NULL column, a
        missing key, a JSON `null`, a JSON scalar, and a JSON object alike to
        zero elements (m-op-algebra absence collapse). ``segments`` is bound
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

    # -- placeholders ------------------------------------------------------ #
    def to_driver_sql(self, canonical_sql: str) -> str:
        """Translate the canonical `?` placeholders to this driver's form (`%s`)."""
        return canonical_sql.replace("?", "%s")

    def from_driver_sql(self, driver_sql: str) -> str:
        """The reverse of :meth:`to_driver_sql` — recover canonical `?`-placeholder
        SQL text from this driver's own form.

        Used only where a caller must REPORT a statement it did not itself lower
        (the conformance engine's materializing-predicate-write capture, COR-3
        Phase 8 increment 5: its per-row writes are query-result-dependent, so
        there is no independent pure re-lowering to draw canonical emission text
        from — the executed driver SQL is the only source, and every OTHER
        emission this engine reports is canonical text, so a captured statement
        must round-trip back before joining them). Production code never calls
        this — it always starts from canonical text and translates outward, never
        back.
        """
        return driver_sql.replace("%s", "?")

    # -- inheritance (m-inheritance / m-sql) -------------------------------- #
    def null_cast(self, neutral_type: str, max_length: int | None) -> str:
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
        if _base_type(neutral_type) == "decimal":
            inner = neutral_type[len("decimal") :].strip("() ")
            p, s = (part.strip() for part in inner.split(","))
            return f"decimal({p}, {s})"
        return self.column_type(neutral_type, max_length)

    # -- DDL type mapping -------------------------------------------------- #
    def column_type(self, neutral_type: str, max_length: int | None) -> str:
        """The concrete column type for a neutral type (used by DDL derivation)."""
        base = _base_type(neutral_type)
        if base == "string":
            return f"varchar({max_length})" if max_length is not None else "text"
        if base == "decimal":
            inner = neutral_type[len("decimal") :].strip("() ")
            p, s = (part.strip() for part in inner.split(","))
            return f"numeric({p}, {s})"
        mapped = _DDL_TYPES.get(base)
        if mapped is None:
            raise ValueError(f"no {self.name} column type for neutral type {neutral_type!r}")
        return mapped

    # -- errors ------------------------------------------------------------ #
    def classify(self, code: str) -> str | None:
        """The neutral m-db-error category for a native code, or ``None``."""
        return self.error_codes.get(code)


def _base_type(neutral_type: str) -> str:
    return neutral_type.split("(", 1)[0]


_CAST_TARGETS: Final[dict[str, str]] = {
    "int32": "bigint",
    "int64": "bigint",
    "float32": "double precision",
    "float64": "double precision",
}

_DDL_TYPES: Final[dict[str, str]] = {
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
    "json": "jsonb",
}

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
