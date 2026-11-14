from __future__ import annotations

import enum
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from importlib.resources import files
from typing import Final, Literal, Protocol, cast

from parallax.core.internal.base import (
    SQL_NULL,
    Boolean,
    Bytes,
    Date,
    DocumentRead,
    DocumentValue,
    Float32,
    Float64,
    Int32,
    Int64,
    Json,
    NeutralType,
    Numeric,
    String,
    StructuredDocument,
    Time,
    Timestamp,
    Uuid,
    is_document_value,
)

__all__ = [
    "JSON_NULL",
    "POSTGRES",
    "ArrayBind",
    "ColumnDdl",
    "Dialect",
    "DocumentRootCheckDdl",
    "EncodedJsonKind",
    "ExclusionDdl",
    "IndexColumnDdl",
    "IntervalCheckDdl",
    "JsonNull",
    "PhysicalIndexName",
    "RenderedScalarCell",
    "ScalarResult",
    "TableReference",
    "Unsupported",
    "decode_bytes_cell",
    "scalar_result",
]

_HEX_DIGITS: Final = re.compile(r"[0-9a-fA-F]*")

EncodedJsonKind = Literal["boolean", "number", "string"]
"""The JSON primitive kind a scalar's canonical document encoding takes."""


class JsonNull(enum.Enum):
    """The literal JSON ``null`` document as one element of a ``json``
    :class:`ArrayBind`, distinct from ``None``, which is SQL NULL there."""

    JSON_NULL = "null"


JSON_NULL: Final = JsonNull.JSON_NULL


@dataclass(frozen=True, slots=True)
class ArrayBind:
    """A neutral carrier for one array bind whose elements share ``element_type``.

    ``values`` holds the managed elements in order, with no per-element
    wrapper. A ``None`` element is SQL NULL under every element type, and a
    ``timestamp`` element may be the open upper bound ``INFINITY``. Under
    ``json`` every other element is one encoded document: ``JSON_NULL`` is the
    literal JSON null document, and a list is one document rather than a
    dimension. The carrier is the only owner of its element type, so a concrete
    adapter binds the array from that type alone rather than by inspecting its
    elements. ``values`` is the caller's own list, handed over unchanged: it
    must not be mutated after binding.
    """

    element_type: NeutralType
    values: list[object]


@dataclass(frozen=True, slots=True)
class ScalarResult:
    """How one Column's scalar arrives in a result row and is published.

    ``encoded`` cells arrive as text the read decodes above the port rather than
    as the driver's native scalar, under ``publication_key`` rather than the
    Column's own spelling.
    """

    publication_key: str
    encoded: bool


def scalar_result(column: str, neutral_type: NeutralType) -> ScalarResult:
    """The result spelling and encoding of ``column``'s scalar of ``neutral_type``.

    A pure function of the value's type, shared by every dialect: `bytes`
    arrives as hexadecimal text under ``<column>_hex``.
    """
    if isinstance(neutral_type, Bytes):
        return ScalarResult(f"{column}_hex", True)
    return ScalarResult(column, False)


def decode_bytes_cell(cell: object) -> object:
    """The octets a `bytes` cell spells, or ``cell`` itself where it spells none.

    The cell is a dialect's hexadecimal spelling rather than a Wire value, so
    either case decodes, and admission judges whatever comes back undecoded.
    """
    if isinstance(cell, str) and len(cell) % 2 == 0 and _HEX_DIGITS.fullmatch(cell) is not None:
        return bytes.fromhex(cell)
    return cell


@dataclass(frozen=True, slots=True)
class RenderedScalarCell:
    """One rendered scalar select-list cell.

    ``select_sql`` is the cell as the select list spells it, naming
    ``output_alias`` where that differs from the expression's own name;
    ``expression_sql`` is the same value without an alias, for a comparison
    that reads the Column directly. ``binds`` belong to either spelling.
    """

    select_sql: str
    expression_sql: str
    binds: tuple[object, ...]
    output_alias: str
    scalar_result: ScalarResult


# A "simple" identifier needs no quoting: lowercase, starts with a letter.
_SIMPLE = re.compile(r"^[a-z][a-z0-9_]*$")


class TableReference(Protocol):
    """One physical table as structured components: its qualifier, then its name.

    Each component is raw. A dot inside one is part of it, never qualification.
    """

    @property
    def qualifier(self) -> tuple[str, ...]: ...
    @property
    def name(self) -> str: ...


@dataclass(frozen=True, slots=True)
class _QualifiedName:
    qualifier: tuple[str, ...]
    name: str


@dataclass(frozen=True, slots=True)
class PhysicalIndexName:
    """One physical Index name as a database holds it.

    Validated as a nonempty identifier and nothing more: a name read back off a
    driver diagnostic (`widget_pkey`) is as legitimate as a generated one, and
    the Dialect's identifier byte limit is the generating rule's concern rather
    than this value's.
    """

    value: str

    def __post_init__(self) -> None:
        if not self.value:
            raise ValueError("a Physical Index Name is a nonempty identifier")


@dataclass(frozen=True, slots=True)
class ColumnDdl:
    """One physical Column as a DDL primitive receives it.

    ``column`` is already quoted for the dialect and ``type_sql`` is already its
    concrete column type, so a primitive spells the STATEMENT around facts a
    caller resolved rather than resolving a layout of its own.
    """

    column: str
    type_sql: str
    nullable: bool


@dataclass(frozen=True, slots=True)
class IndexColumnDdl:
    """One Index component: its quoted Column and the domain an index over it has.

    A dialect's index admissibility depends on the component's value domain — an
    unbounded String has no key length InnoDB can index — so the neutral type and
    its bound travel with the Column rather than being re-derived from the
    spelled type.
    """

    column: str
    neutral_type: NeutralType
    max_length: int | None


@dataclass(frozen=True, slots=True)
class IntervalCheckDdl:
    """One named check that a row's ``start`` Column precedes its ``end`` Column.

    Every identifier is already quoted for the dialect.
    """

    name: str
    start: str
    end: str


@dataclass(frozen=True, slots=True)
class DocumentRootCheckDdl:
    """One named check that a row's ``column`` holds a JSON object.

    Every identifier is already quoted for the dialect.
    """

    name: str
    column: str


@dataclass(frozen=True, slots=True)
class ExclusionDdl:
    """One named constraint that no two rows equal on every ``equal`` Column
    overlap on every ``overlapping`` half-open interval at once.

    Every identifier is already quoted for the dialect, and each interval is its
    start Column then its end Column.
    """

    name: str
    equal: tuple[str, ...]
    overlapping: tuple[tuple[str, str], ...]


def _check_condition(check: IntervalCheckDdl | DocumentRootCheckDdl) -> str:
    match check:
        case IntervalCheckDdl(start=start, end=end):
            return f"{start} < {end}"
        case DocumentRootCheckDdl(column=column):
            return f"jsonb_typeof({column}) = 'object'"


def _column_clause(column: ColumnDdl) -> str:
    """One Column's name, type, and nullability, as every DDL statement spells it."""
    return f"{column.column} {column.type_sql}" + ("" if column.nullable else " not null")


@dataclass(frozen=True, slots=True)
class Unsupported:
    """A DDL primitive's refusal: why this dialect cannot spell the statement.

    ``reason`` is dialect-neutral prose a caller carries verbatim into its own
    aggregated error. A primitive answering with the statement OR with why not is
    what keeps a capability predicate from drifting away from its renderer.
    """

    reason: str


@dataclass(frozen=True, slots=True)
class Dialect:
    """One database's pure SQL strings and parse rules (m-dialect)."""

    name: str
    reserved: frozenset[str]
    quote_char: str
    # SQLSTATE / native code -> neutral m-db-error category.
    error_codes: dict[str, str]
    # The longest identifier this database stores without truncating it. A
    # derived name is shortened to fit; a resolved table or sequence component
    # that does not fit is refused (`identifier_issue`).
    max_identifier_bytes: int
    # The most bind parameters one statement may carry (`m-dialect` "Bind
    # parameter limit"): a positive bound on each statement alone.
    max_bind_parameters: int
    # Whether an UPDATE's native affected count includes the rows it matched
    # but left unchanged, which is what lets a matched count prove that an
    # unchanged row still stands as observed (`m-dialect` "Unchanged-row count").
    counts_unchanged_rows: bool = False
    # Whether one bind may carry a whole array, cast through
    # :meth:`array_parameter` (`m-dialect` "Array parameter cast form").
    binds_arrays: bool = False
    # The native codes reporting an exclusion constraint's violation, one kind
    # of the `constraintViolation` category (`m-db-error`).
    exclusion_violation_codes: frozenset[str] = frozenset()
    seek_null_tail_lock_placement: Literal["outer", "branches"] = "outer"
    # The scope an index name is unique within (`m-dialect` "Object-name
    # scopes"): every relation of one qualifier, or the one table it indexes.
    index_name_scope: Literal["qualifier", "table"] = "qualifier"

    def __post_init__(self) -> None:
        limit = self.max_bind_parameters
        if type(limit) is not int or limit < 1:
            raise ValueError(
                f"a dialect's bind parameter limit is a positive integer, got {limit!r}"
            )

    # -- identifiers ------------------------------------------------------- #
    def quote(self, identifier: str) -> str:
        """Quote ``identifier`` iff it is reserved or non-simple for this dialect,
        doubling every quote character inside it."""
        if _SIMPLE.match(identifier) and identifier not in self.reserved:
            return identifier
        q = self.quote_char
        return f"{q}{identifier.replace(q, q + q)}{q}"

    def render_table(self, table: TableReference) -> str:
        """``table`` as SQL: each qualifier component, then its name, quoted alone."""
        return ".".join(self.quote(component) for component in (*table.qualifier, table.name))

    def identifier_issue(self, identifier: str) -> str | None:
        """Why this database cannot hold ``identifier`` exactly, or ``None``.

        An empty identifier names nothing, a NUL cannot be spelled, and a longer
        one is truncated or refused rather than stored as written.
        """
        if not identifier:
            return "an identifier is nonempty"
        if "\x00" in identifier:
            return "an identifier cannot contain NUL"
        if len(identifier.encode("utf-8")) > self.max_identifier_bytes:
            return f"an identifier is at most {self.max_identifier_bytes} bytes"
        return None

    def qualified(self, alias: str, column: str) -> str:
        """An alias-qualified column reference (`t0.col` / `t0."order"`)."""
        return f"{alias}.{self.quote(column)}"

    # -- select-list rendering ------------------------------------------- #
    def render_scalar(
        self,
        alias: str,
        column: str,
        neutral_type: NeutralType,
        *,
        output_alias: str | None = None,
    ) -> RenderedScalarCell:
        """One Column's scalar select-list cell against ``alias``.

        A `bytes` column renders its hex-encoded text
        (`encode(t0.col, ?) col_hex`, bind `hex`); every other column renders the
        plain alias-qualified reference with no bind. The cell is named by its
        publication key unless ``output_alias`` names it otherwise, which changes
        only the SQL name, never the encoding or the publication key.
        """
        result = scalar_result(column, neutral_type)
        output = result.publication_key if output_alias is None else output_alias
        reference = self.qualified(alias, column)
        if result.encoded:
            expression = f"encode({reference}, ?)"
            return RenderedScalarCell(
                f"{expression} {output}", expression, ("hex",), output, result
            )
        select = reference if output == column else f"{reference} {output}"
        return RenderedScalarCell(select, reference, (), output, result)

    def render_document_pair(self, expression: str) -> tuple[str, str]:
        """The adjacent SQL presence/document cells for ``expression``."""
        return f"not {expression} is null", expression

    def parse_owned_document_read(self, presence: object, document: object) -> DocumentRead:
        """Parse a document pair whose plain JSON containers transfer to the result."""
        if type(presence) is not bool:
            raise ValueError(
                "a document-read presence projection must be a SQL boolean, "
                f"got {type(presence).__name__}"
            )
        if not presence:
            return SQL_NULL
        if not is_document_value(document):
            raise ValueError(
                "a present structured-document result must be a portable JSON value, "
                f"got {type(document).__name__}"
            )
        return StructuredDocument(document)

    # -- result shaping ---------------------------------------------------- #
    def limit_clause(self) -> str:
        """The row-limit clause (the count rides as a `?` bind)."""
        return "limit ?"

    def optimizer_fence(self) -> tuple[str, list[object]]:
        """Prevent a discriminator-filtered derived table from being flattened."""
        return "offset 0", []

    def native_placement(self, direction: Literal["asc", "desc"]) -> Literal["first", "last"]:
        """Where this database puts a NULL in ``direction`` when nothing asks.

        Not portable, and not observationally irrelevant: an ordering key that
        lowers to the plain term — a non-nullable one, or one whose authored
        placement is already this answer — leaves the database's own convention
        deciding which side of the non-nulls a stored NULL falls on, and a
        continuation seek past that key admits or excludes it accordingly.
        Postgres treats NULL as the largest value and MariaDB as the smallest,
        so the two are mirror images.
        """
        return "last" if direction == "asc" else "first"

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
        or splits either form. Where :meth:`native_placement` already answers the
        request it returns the plain term — a deliberate lowering decision, not an
        omission, and one a seek reads back through that same method.
        """
        if placement == self.native_placement(direction):
            return f"{column_sql} {direction}"
        return f"{column_sql} {direction} nulls {placement}"

    # -- shared lock ------------------------------------------------------- #
    def shared_lock_on_outer_seek_read(self) -> bool:
        """Whether a two-branch seek read takes its shared lock on the outer read."""
        return self.seek_null_tail_lock_placement == "outer"

    def shared_lock_suffix(self, root_alias: str) -> str:
        """The shared-row-lock suffix for an object find required to take the lock."""
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
        if isinstance(neutral_type, Numeric):
            return f"cast({extraction} as decimal({neutral_type.precision}, {neutral_type.scale}))"
        cast_type = _EXTRACTION_CASTS.get(type(neutral_type))
        return extraction if cast_type is None else f"cast({extraction} as {cast_type})"

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

    def scalar_element(
        self, element: str, kind: EncodedJsonKind, neutral_type: NeutralType
    ) -> tuple[str, str, list[object]]:
        """The extraction and compared expressions of one array element read as
        a scalar of ``neutral_type``, and their binds.

        ``element`` is the element's own JSON value reference. The scalar is
        extracted, and cast where the type's comparison casts, only inside the
        `when` branch of a `case` whose guard confirms the element's JSON kind is
        ``kind``; any other element yields SQL null, so it stays a candidate
        whose every comparison is unknown. Placing the cast inside the matching
        branch, rather than beside a separate kind conjunct, is what keeps a
        wrong-kind element from reaching the cast at all.
        """
        extraction = f"case when jsonb_typeof({element}) = ? then {element} #>> ? end"
        compared_value = self.nested_cast(f"{element} #>> ?", neutral_type)
        compared = f"case when jsonb_typeof({element}) = ? then {compared_value} end"
        return extraction, compared, [kind, "{}"]

    def object_presence(self, document: str, segments: tuple[str, ...]) -> tuple[str, list[object]]:
        """Whether the single Value Object at ``segments`` inside ``document`` is
        present, two-valued: a JSON object there is present, and SQL null, a
        missing key, JSON null, or any non-object is absent.

        ``document`` is an ALREADY-RENDERED document reference, for the same
        reason :meth:`nested_extract` takes one; an empty ``segments`` probes it
        directly.
        """
        if segments:
            holes = ", ".join(["?"] * len(segments))
            extract = f"jsonb_extract_path({document}, {holes})"
        else:
            extract = document
        return f"coalesce(jsonb_typeof({extract}) = ?, false)", [*segments, "object"]

    def boolean_envelope(self, value: str) -> str:
        """A one-element Boolean array carrying ``value``, null included."""
        return f"array [ {value} ]"

    def absent_envelope(self) -> str:
        """The envelope an absent target defaults to: a false element."""
        return "array [ false ]"

    def envelope_value(self, envelope: str) -> str:
        """The Boolean ``envelope`` carries, extracted once its defaults apply."""
        return f"({envelope}) [ 1 ]"

    # -- structured documents (m-storage-layout) --------------------------- #
    def document_mutation(
        self, document: str, members: Mapping[str, object]
    ) -> tuple[str, list[object]]:
        """The `SET` expression assigning ``members`` inside ``document``, and its
        ordered binds (m-dialect *Document mutation-expression form*).

        ``document`` is an ALREADY-RENDERED Structured Column reference, for the
        same reason :meth:`nested_extract` takes one. ``members`` maps each
        assigned top-level member to its complete encoded value in canonical
        logical placement order. Postgres merges them as one object, so its
        supplied keys replace the stored ones whole and every other key stands;
        the object crosses as one structured document, which the adapter hands
        to the driver's structured-document wrapper.
        """
        return f"{document} || cast(? as jsonb)", [
            StructuredDocument(cast("DocumentValue", members))
        ]

    def sourced_document_mutation(self, document: str, source: str) -> str:
        """The `SET` expression merging the assigned-members object of the
        already-rendered ``source`` expression into ``document``: a grouped
        statement's per-row source column, which already carries the document
        type, so the term binds nothing of its own."""
        return f"{document} || {source}"

    # -- inheritance (m-inheritance / m-sql) -------------------------------- #
    def null_cast(self, neutral_type: NeutralType, max_length: int | None) -> str:
        """The ``CAST`` target-type spelling for a ``NULL`` placeholder column in a
        table-per-concrete-subtype union-all branch.

        `m-dialect`'s placeholder cast form owns each spelling. It is a separate
        decision from :meth:`column_type`, which only some spellings happen to match.
        """
        if isinstance(neutral_type, Numeric):
            return f"decimal({neutral_type.precision}, {neutral_type.scale})"
        if isinstance(neutral_type, Int32):
            return "int"
        return self.column_type(neutral_type, max_length)

    def array_parameter(self, neutral_type: NeutralType, *, extracted: bool = False) -> str:
        """One array bind cast to the array of the type an expression of
        ``neutral_type`` compares in or a Column of it stores: its column type,
        or, when ``extracted`` from a document, the type :meth:`nested_cast`
        casts the text to, else text.

        The driver types an untyped array by its elements, so small integers would
        arrive as a narrower integer array and make the comparison cross-type. The
        element type carries no length or precision modifier: an explicit cast to
        ``varchar(n)`` truncates and one to ``decimal(p, s)`` rounds, so either
        could make a value equal a key it does not equal, or store a value other
        than the one bound where assignment into the Column would refuse it.
        """
        if not extracted:
            element = _ARRAY_ELEMENT_TYPES[type(neutral_type)]
        elif isinstance(neutral_type, Numeric):
            element = "decimal"
        else:
            element = _EXTRACTION_CASTS.get(type(neutral_type), "text")
        return f"cast(? as {element}[])"

    # -- DDL type mapping -------------------------------------------------- #
    def column_type(self, neutral_type: NeutralType, max_length: int | None) -> str:
        """The concrete column type for a neutral type (used by DDL derivation)."""
        match neutral_type:
            case String():
                return f"varchar({max_length})" if max_length is not None else "text"
            case Numeric(precision, scale):
                return f"numeric({precision}, {scale})"
            case _:
                return _FIXED_COLUMN_TYPES[type(neutral_type)]

    # -- DDL statements ---------------------------------------------------- #
    def create_table(
        self,
        table: str,
        columns: Sequence[ColumnDdl],
        primary_key: Sequence[str],
        checks: Sequence[IntervalCheckDdl | DocumentRootCheckDdl] = (),
        *,
        primary_key_name: str | None = None,
        exclusion: ExclusionDdl | None = None,
    ) -> str:
        """``create table`` for one whole Table, keyed and constrained inline.

        The caller supplies the complete physical column sequence, the key
        columns, the checks, and the exclusion in their own order; all are
        already quoted. An empty ``primary_key`` emits no key clause, which
        is the keyless Table a model declaring no primary key produces, and a
        key without ``primary_key_name`` is left for the database to name. The
        exclusion is immediate and not deferrable: each statement is checked as
        it runs.
        """
        parts = [_column_clause(column) for column in columns]
        if primary_key:
            named = "" if primary_key_name is None else f"constraint {primary_key_name} "
            parts.append(f"{named}primary key ({', '.join(primary_key)})")
        parts.extend(
            f"constraint {check.name} check ({_check_condition(check)})" for check in checks
        )
        if exclusion is not None:
            operands = [f"{column} with =" for column in exclusion.equal]
            operands.extend(
                f"tstzrange({start}, {end}) with &&" for start, end in exclusion.overlapping
            )
            parts.append(f"constraint {exclusion.name} exclude using gist ({', '.join(operands)})")
        return f"create table {table} ({', '.join(parts)})"

    def create_extension(self, name: str) -> str | Unsupported:
        """Install the provider extension ``name`` unless the database has it.

        ``name`` is already quoted. The one statement a Schema Delta spells
        idempotently: the extension is a provider-managed prerequisite of the
        tables a delta creates, not a model-owned object it reconciles.
        """
        return f"create extension if not exists {name}"

    def add_column(self, table: str, column: ColumnDdl) -> str:
        """``alter table … add column`` for one new physical Column."""
        return f"alter table {table} add column {_column_clause(column)}"

    def restate_column(self, table: str, earlier: ColumnDdl, later: ColumnDdl) -> str | Unsupported:
        """Restate one Column's value domain as ``later``, or why this dialect cannot.

        The whole earlier-to-later change arrives at once because the two
        dialects factor it differently: Postgres spells a type change and a
        dropped ``not null`` as separate actions of one ``alter table``, while
        MariaDB restates the whole column with ``modify``. Nullability only ever
        relaxes across this seam — a Column rows are stored against is never
        asked to tighten, and one no shape stores is nullable at both endpoints —
        so a dropped ``not null`` is the only nullability action a caller can
        request.
        """
        actions: list[str] = []
        if earlier.type_sql != later.type_sql:
            actions.append(f"alter column {later.column} type {later.type_sql}")
        if earlier.nullable != later.nullable:
            actions.append(f"alter column {later.column} drop not null")
        return f"alter table {table} {', '.join(actions)}"

    def create_index(
        self,
        table: str,
        name: PhysicalIndexName,
        columns: Sequence[IndexColumnDdl],
        *,
        unique: bool,
    ) -> str | Unsupported:
        """``create index`` for one authored Index, or why this dialect cannot.

        Postgres indexes every column type this system spells, including an
        unbounded ``text``, so it never refuses. Creating a unique Index is the
        authoritative validation of the data already stored; no statement here
        preflights it.
        """
        keyword = "create unique index" if unique else "create index"
        components = ", ".join(column.column for column in columns)
        return f"{keyword} {self.quote(name.value)} on {table} ({components})"

    def drop_index(self, table: TableReference, name: PhysicalIndexName) -> str:
        """``drop index`` for one Index the later model no longer defines.

        ``table`` is the Table the Index sits on. Postgres names the Index within
        that Table's schema, never through the connection's search path.
        """
        return f"drop index {self.render_table(_QualifiedName(table.qualifier, name.value))}"

    # -- errors ------------------------------------------------------------ #
    def classify(self, code: str) -> str | None:
        """The neutral m-db-error category for a native code, or ``None``."""
        return self.error_codes.get(code)

    def reports_exclusion_violation(self, code: str | None) -> bool:
        """Whether native ``code`` reports an exclusion constraint's violation."""
        return code in self.exclusion_violation_codes


_FIXED_COLUMN_TYPES: Final[Mapping[type, str]] = {
    Boolean: "boolean",
    Int32: "integer",
    Int64: "bigint",
    Float32: "real",
    Float64: "double precision",
    Bytes: "bytea",
    Date: "date",
    Time: "time",
    Timestamp: "timestamptz",
    Uuid: "uuid",
    Json: "jsonb",
}

# The cast a document extraction of each non-decimal type compares through; a
# type absent here compares as the extracted text.
_EXTRACTION_CASTS: Final[Mapping[type, str]] = {
    Int32: "bigint",
    Int64: "bigint",
    Float32: "real",
    Float64: "double precision",
    Boolean: "boolean",
}

_ARRAY_ELEMENT_TYPES: Final[Mapping[type, str]] = {
    Boolean: "boolean",
    Int32: "int",
    Int64: "bigint",
    Float32: "real",
    Float64: "double precision",
    Numeric: "decimal",
    String: "text",
    Bytes: "bytea",
    Date: "date",
    Time: "time",
    Timestamp: "timestamptz",
    Uuid: "uuid",
    Json: "jsonb",
}

_RESERVED_WORDS: Final[dict[str, list[str]]] = json.loads(
    files(__package__).joinpath("dialect-reserved-words.json").read_text("utf-8")
)

POSTGRES: Final[Dialect] = Dialect(
    name="postgres",
    reserved=frozenset(_RESERVED_WORDS["postgres"]),
    quote_char='"',
    error_codes={
        "23505": "uniqueViolation",
        "23514": "constraintViolation",
        "23P01": "constraintViolation",
        "40P01": "deadlock",
        "40001": "deadlock",
        "55P03": "lockWaitTimeout",
    },
    max_identifier_bytes=63,
    max_bind_parameters=65_535,
    counts_unchanged_rows=True,
    binds_arrays=True,
    exclusion_violation_codes=frozenset({"23P01"}),
)
"""The PostgreSQL Dialect."""
