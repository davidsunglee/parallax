"""The order a streamed delivery advances by, and the seek each page must spell.

:mod:`.stream` is this module's only caller. It drives pages and proves the
delivery exhausted; what happens here is the derivation those pages are graded
against — the Continuation Order composed from the query and the model, the seek
expression and bind list one cursor composes, and the refusal of a page whose own
text spells something else.

Nothing here reads the authored SQL to decide what a page SHOULD say. The order
comes from the query's Sort Keys, the model's primary key, and a milestone-set
read's own As-Of Axis edges; the seek comes from the order and the cursor. The
authored text is only ever the thing being graded, which is what makes a page
that reached the right rows the wrong way a failure rather than a pass.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal, NamedTuple

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError
from sqlglot.expressions.core import Expr

from .. import portable_literal
from ..case import Case, Entity
from ..case_assertions import CaseFailure
from ..inheritance import Family, query_position
from ..sql_canonical import sqlglot_dialect
from ..storage_layout import DocumentMember, MemberAddress, member_address
from . import execute, materialize

# --- the order ---------------------------------------------------------------


def _primary_key_column(case: Case, entity: Entity) -> str:
    """The physical column of *entity*'s primary key.

    Every Continuation Order carries the primary key (`m-snapshot-read`), and a
    Metamodel primary key is one Attribute, so this is the coordinate a streamed
    page seeks from once the query's own Sort Keys are spent — and, for a
    single-instant read, the one that makes the order total.
    """
    for attribute in entity.attributes:
        if attribute.get("primaryKey"):
            return attribute["column"]
    raise CaseFailure(
        f"{case.path.name}: {entity.canonical_name} declares no primary key to continue a "
        f"stream from; a Continuation Order ends in the key that makes it total."
    )


@dataclass(frozen=True, slots=True)
class ContinuationTerm:
    """One term of the order a streamed delivery advances by, as its SEEK sees it.

    Direction reaches only the comparators: it decides which way each branch
    compares and never how many coordinates that branch binds, so it is graded
    against the statement's own text while the coordinates are graded against its
    binds. Null Placement reaches both — under `last` a null coordinate has
    nothing after it, so its depth contributes neither branch nor bind.

    ``column`` is the result key the term's coordinate is read under, which a
    document-resident member has as much as a Column-mapped one. The two
    spellings beside it are how the statement names the member, and they differ
    for a resident term: a comparison goes through the declared type's cast where
    the type has one, while a null test asks the bare extraction, presence being
    a question the cast does not change. ``path_binds`` is what every one of
    those occurrences binds ahead of its own coordinate — empty for a Column,
    which names itself.

    ``document_resident`` is the placement itself rather than a shorthand read
    off the binds, because it decides something the spellings do not: whether the
    seek hoists its leading range at all.
    """

    column: str
    compared: str
    tested: str
    path_binds: tuple[Any, ...]
    direction: Literal["asc", "desc"]
    nulls: Literal["first", "last"]
    nullable: bool
    placement: Literal["first", "last"]
    neutral_type: str
    document_resident: bool


_NULL_IS_LARGEST = {"postgres": True, "mariadb": False}
"""Whether a dialect's own `order by` ranks `NULL` above every value (m-dialect)."""


def _native_placement(dialect: str, direction: Literal["asc", "desc"]) -> Literal["first", "last"]:
    """Where *dialect* puts a `NULL` in *direction* when nothing asks (m-dialect)."""
    return "last" if _NULL_IS_LARGEST[dialect] == (direction == "asc") else "first"


def _emitted_placement(
    dialect: str,
    *,
    direction: Literal["asc", "desc"],
    nulls: Literal["first", "last"],
    nullable: bool,
) -> Literal["first", "last"]:
    """Where the ORDER BY a page emits actually puts this term's `NULL`s.

    A nullable key lowers through the compensating Null Placement form, so its
    authored placement is the effective one; every other key lowers plain, which
    leaves the dialect's own convention in force whatever the key requested and
    whatever the declaration says the column can hold.
    """
    return nulls if nullable else _native_placement(dialect, direction)


def _direct_term(
    column: str,
    neutral_type: str,
    dialect: str,
    *,
    direction: Literal["asc", "desc"],
    nulls: Literal["first", "last"],
    nullable: bool,
) -> ContinuationTerm:
    return ContinuationTerm(
        column=column,
        compared=column,
        tested=column,
        path_binds=(),
        document_resident=False,
        direction=direction,
        nulls=nulls,
        nullable=nullable,
        placement=_emitted_placement(dialect, direction=direction, nulls=nulls, nullable=nullable),
        neutral_type=neutral_type,
    )


_DOCUMENT_EXTRACTION = {"postgres": "jsonb_extract_path_text", "mariadb": "json_value"}

_DOCUMENT_CAST_TARGETS = {
    "postgres": {
        "int32": "bigint",
        "int64": "bigint",
        "float32": "real",
        "float64": "double precision",
        "boolean": "boolean",
    },
    "mariadb": {
        "int32": "signed",
        "int64": "signed",
        "float32": "float",
        "float64": "double",
        "boolean": "signed",
    },
}


def _document_cast_target(type_spelling: str | None, dialect: str) -> str | None:
    """The CAST target a document-resident member of this declared type compares
    under on *dialect*, or ``None`` where it compares as the extracted text.

    The numeric family casts because a JSON number's integer part has no fixed
    width, so its stored spelling does not compare in value order as text; a
    `boolean` casts because the two dialects' extractions do not spell it alike.
    Every other declarable type compares as the extracted text, the canonical
    document spelling already ordering correctly. Which target each casts TO is a
    dialect decision, and a `decimal(p, s)` casts to its own declared precision on
    both (m-dialect). Spelled here rather than taken from any implementation: the
    ①↔② cross-check is an independent derivation, so it must know the table
    itself.
    """
    if type_spelling is None:
        return None
    if type_spelling.startswith("decimal("):
        precision, _, scale = (
            type_spelling.removeprefix("decimal(").removesuffix(")").partition(",")
        )
        return f"decimal({precision.strip()}, {scale.strip()})"
    return _DOCUMENT_CAST_TARGETS.get(dialect, {}).get(type_spelling)


def _cast_target_spelling(target: exp.DataType | str, dialect: str) -> str:
    """*target* as one canonical spelling, so the two sides compare as types.

    Each side reaches this differently — the expected one from the table above,
    the observed one off the parsed statement — so both are put through the
    dialect's own type parser rather than compared as text: a golden is free to
    spell `DECIMAL(18,2)` where the table says `decimal(18, 2)`. What survives
    the normalization is the target's identity, which is what m-dialect fixes and
    what a page's own result depends on; MariaDB's `signed` and `bigint` alone
    normalize alike, so those two are indistinguishable here and the live sweep
    is what refuses the one MariaDB's CAST grammar rejects.
    """
    node = (
        target
        if isinstance(target, exp.DataType)
        else exp.DataType.build(target, dialect=sqlglot_dialect(dialect))
    )
    return node.sql(dialect=sqlglot_dialect(dialect)).lower()


def _extraction_path_binds(path: tuple[str, ...], dialect: str) -> tuple[Any, ...]:
    """The binds one document extraction over *path* carries, per dialect.

    Postgres `jsonb_extract_path_text` takes one hole per segment; MariaDB
    `json_value` takes one hole holding the whole ``$.a.b`` JSON path
    (m-dialect). A read's extraction therefore binds a different NUMBER of values
    on the two dialects for the same member, which is why a seek's bind list is
    derived per dialect rather than translated between them.
    """
    if dialect == "mariadb":
        return ("$." + ".".join(path),)
    return tuple(path)


def _resident_term(
    member: DocumentMember,
    document_column: str,
    dialect: str,
    *,
    direction: Literal["asc", "desc"],
    nulls: Literal["first", "last"],
    nullable: bool,
) -> ContinuationTerm:
    extraction = f"{document_column} extraction"
    target = _document_cast_target(member.type_spelling, dialect)
    return ContinuationTerm(
        column=member.column,
        compared=extraction
        if target is None
        else f"cast({extraction} as {_cast_target_spelling(target, dialect)})",
        tested=extraction,
        path_binds=_extraction_path_binds(member.path, dialect),
        document_resident=True,
        direction=direction,
        nulls=nulls,
        nullable=nullable,
        placement=_emitted_placement(dialect, direction=direction, nulls=nulls, nullable=nullable),
        neutral_type=member.type_spelling or "string",
    )


def _read_resolved_entities(case: Case, query: dict[str, Any], root: Entity) -> list[Entity]:
    """Every Entity whose own Table *query* resolves over, the position included.

    A concrete-target read resolves over its target alone. An abstract position
    resolves over each concrete subtype its effective set admits as well: under
    table-per-hierarchy every one of them shares the position's own Table, and
    under table-per-concrete-subtype each carries a Table of its own while the
    root carries none at all. Both questions residence raises — where a member
    sits, and whether the read reaches one placement of it or several — are asked
    of this same list.
    """
    position = query_position(query, case.model.entity_defs)
    if position is None:
        return [root]
    return [
        root,
        *(
            case.model.entity(concrete)
            for concrete in materialize.read_effective_set(case, position.family, position.target)
        ),
    ]


def _resolved_document_member(
    case: Case, query: dict[str, Any], root: Entity, address: MemberAddress
) -> tuple[str, DocumentMember] | None:
    """The ONE Structured Column and member a resident Sort Key extracts from.

    A seek spells its extraction against a single Table's document column, so the
    read has to resolve the member to one — which is a question about the Tables
    the read reaches, not about the position's abstractness. A table-per-hierarchy
    family shares ONE Table, so a member resident in its document is resolved
    there however many branches the read partitions into. A tableless root has no
    Table to extract from, and a table-per-concrete-subtype family places the same
    member in a Structured Column per branch, so neither resolves to one and both
    are refused by name rather than derived from.
    """
    slots: set[tuple[str, str]] = set()
    resolved: tuple[str, DocumentMember] | None = None
    for entity in _read_resolved_entities(case, query, root):
        document = case.model.storage_layout.document(entity.canonical_name)
        document_column, members = document.column, document.members
        member = next((member for member in members if member.address == address), None)
        if not document_column or member is None:
            continue
        slots.add((entity.table, document_column))
        resolved = document_column, member
    return resolved if len(slots) == 1 else None


def _document_resident_members(case: Case, entity: Entity) -> set[MemberAddress]:
    return {
        member.address
        for member in case.model.storage_layout.document(entity.canonical_name).members
    }


def _read_document_resident_members(case: Case, query: dict[str, Any]) -> set[MemberAddress]:
    """Every member a Table *query* reads carries inside a document instead.

    Addressed rather than spelled: residence is a property of the member a Sort Key
    names, and a member inside a document claims no Column, so a direct member is
    free to hold the very Column a resident one would have been spelled with. Two
    disjoint siblings may reuse a member name over one Table, so the name alone is
    not that member either — only the declaring owner tells one sibling's resident
    member from the other's Column.

    Residence belongs to a Table's own layout, so an abstract position may hold
    none of its own: a table-per-concrete-subtype root is TABLELESS, and a member
    every branch's document carries is resident in nothing that root can be asked
    about. The question is therefore asked of every Table the read resolves over.
    """
    return set[MemberAddress]().union(
        *(
            _document_resident_members(case, entity)
            for entity in _read_resolved_entities(case, query, case.model.entity(query["target"]))
        )
    )


def continuation_order(
    case: Case, query: dict[str, Any], root: Entity, dialect: str
) -> list[ContinuationTerm]:
    """The Continuation Order *query* is delivered in (`m-snapshot-read`).

    The authored Sort Keys in the precedence the query declares, then the primary
    key ascending, and then — for a milestone-set read — every declared As-Of
    Axis start ascending in canonical rank, each appended term omitted where a
    Sort Key already named it. Direction and Null Placement default to `asc` and
    `last` (`m-object-query`) and are carried whether or not they are
    observable.

    Residence is not part of that order and changes none of it: what it changes
    is how each term is spelled and bound, so it is resolved here — per dialect,
    the two extractions differing in both — and carried on the term. A resident
    member the read resolves to no single Structured Column is refused by name,
    since no one extraction spells it.
    """
    terms: list[ContinuationTerm] = []
    names_the_key = False
    family = Family(case.model.entity_defs)
    resident = _read_document_resident_members(case, query)
    for key in query.get("orderBy", []):
        class_name, _, name = key["attr"].rpartition(".")
        entity = case.model.entity(class_name)
        attribute = entity.attribute_by_name(name)
        address = member_address(family, entity.canonical_name, name)
        direction: Literal["asc", "desc"] = key.get("direction", "asc")
        nulls: Literal["first", "last"] = key.get("nulls", "last")
        nullable = bool(attribute.get("nullable"))
        names_the_key = names_the_key or bool(attribute.get("primaryKey"))
        if address not in resident | _document_resident_members(case, entity):
            terms.append(
                _direct_term(
                    attribute["column"],
                    attribute["type"],
                    dialect,
                    direction=direction,
                    nulls=nulls,
                    nullable=nullable,
                )
            )
            continue
        resolved = _resolved_document_member(case, query, root, address)
        if resolved is None:
            raise CaseFailure(
                f"{case.path.name}: the Continuation Order names the document-resident member "
                f"{key['attr']}, which this read resolves to no single Structured Column — an "
                f"extraction is spelled against ONE Table's document, and this read reaches no "
                f"Table holding it, or more than one"
            )
        document_column, member = resolved
        terms.append(
            _resident_term(
                member,
                document_column,
                dialect,
                direction=direction,
                nulls=nulls,
                nullable=nullable,
            )
        )
    if not names_the_key:
        terms.append(
            _direct_term(
                _primary_key_column(case, root),
                root.attribute_by_name(
                    next(
                        attribute["name"]
                        for attribute in root.attributes
                        if attribute.get("primaryKey")
                    )
                )["type"],
                dialect,
                direction="asc",
                nulls="last",
                nullable=False,
            )
        )
    named = {term.column for term in terms}
    for column in _milestone_edge_columns(query, root):
        if column not in named:
            terms.append(
                _direct_term(
                    column, "timestamp", dialect, direction="asc", nulls="last", nullable=False
                )
            )
    return terms


def _milestone_edge_columns(query: dict[str, Any], root: Entity) -> list[str]:
    """The from-columns a milestone-set read's Continuation Order ends in.

    Empty for every single-instant read, whose roots are one per primary key.
    A scan puts every milestone of a key in the result at once, so the key stops
    separating roots and each milestone's own edge — its As-Of Axis starts in
    canonical rank, whichever axis the query scanned — is what does
    (`m-snapshot-read`).
    """
    if not execute.scans_an_axis(query):
        return []
    return [axis["start_column"] for axis in root.temporal_runtime_axes]


# --- the seek expression a cursor composes -----------------------------------


type _SeekNode = str | _SeekJunction


@dataclass(frozen=True, slots=True)
class _SeekJunction:
    operator: Literal["and", "or", "not"]
    operands: tuple[_SeekNode, ...]


def _joined(operator: Literal["and", "or"], operands: Sequence[_SeekNode]) -> _SeekNode:
    """Flattened so that an association the composed and the spelled sides spell
    differently compares equal, while a page that conjoined what the order
    disjoins still does not."""
    flattened = [
        operand
        for node in operands
        for operand in (
            node.operands
            if isinstance(node, _SeekJunction) and node.operator == operator
            else (node,)
        )
    ]
    if len(flattened) == 1:
        return flattened[0]
    return _SeekJunction(operator, tuple(flattened))


@dataclass(frozen=True, slots=True)
class ComposedSeek:
    """The expression a page's seek is, and the binds carrying it, as ONE value.

    The two are one derivation rather than two agreeing ones: every leaf that
    spells a member spells its binds too — a Document Path ahead of a coordinate
    where the member is document-resident, the coordinate alone where it is a
    Column — so a shape and a bind list cannot drift apart here the way two
    parallel walks of the same order could.
    """

    node: _SeekNode
    binds: tuple[Any, ...]
    neutral_types: tuple[str | None, ...]

    def __post_init__(self) -> None:
        if len(self.binds) != len(self.neutral_types):
            raise ValueError("composed seek bind metadata must align with its binds")


def _composed(operator: Literal["and", "or"], parts: Sequence[ComposedSeek]) -> ComposedSeek:
    return ComposedSeek(
        _joined(operator, [part.node for part in parts]),
        tuple(bind for part in parts for bind in part.binds),
        tuple(neutral_type for part in parts for neutral_type in part.neutral_types),
    )


def composed_seek(terms: list[ContinuationTerm], coordinates: tuple[Any, ...]) -> ComposedSeek:
    """The seek a page continuing past *coordinates* carries.

    Derived from `m-snapshot-read`'s seek alone, never from the authored SQL: the
    lexicographic remainder — one branch per tie depth, disjoined, each branch
    tying with every coordinate above it before comparing its own in that term's
    direction and EMITTED placement — behind the range a leading direct Column
    declared non-nullable hoists. A single-term order composes neither part: one
    strict comparison already is the top-level conjunct the hoist supplies. A
    null coordinate carries no coordinate bind at any depth, both spellings that
    reach it being null checks, and where the emitted clause placed nulls last it
    contributes no branch at all: nothing sorts after a null there.

    Placement is the emitted one rather than the authored one, because that is
    what decides which rows the clause actually ranked after the coordinate: a
    key the model declares non-nullable lowers plain and takes the dialect's own
    convention. The hoist is the one part that still turns on the DECLARATION,
    and deliberately (`m-snapshot-read` *Streamed delivery*): over a direct
    Column it buys the leading index range at the price of skipping a stored NULL
    non-conforming storage left in a `NOT NULL` column. It stops at the Column,
    though — a document-resident leading term hoists nothing, because its
    extraction reads NULL for ordinary invalid stored data that same
    specification guarantees is delivered, and a range over an extraction is no
    index range to trade for it.

    Grading the SHAPE is what the binds cannot do — a page that seeks the wrong
    way, or disjoins what the order conjoins, binds exactly what a correct one
    binds — and grading the binds is what the shape cannot do, two resident terms
    over one document being one spelling told apart only by the paths they bind.
    """
    branches: list[ComposedSeek] = []
    for depth, term in enumerate(terms):
        after = _strictly_after(term, coordinates[depth])
        if after is None:
            continue
        ties = [_ties_with(terms[above], coordinates[above]) for above in range(depth)]
        branches.append(_composed("and", [*ties, after]) if ties else after)
    lead = terms[0]
    if len(terms) == 1:
        return branches[0]
    remainder = _composed("or", branches)
    if lead.nullable or lead.document_resident or coordinates[0] is None:
        return remainder
    return _composed("and", [_hoisted_range(lead, coordinates[0]), remainder])


def _strictly_after(term: ContinuationTerm, coordinate: Any) -> ComposedSeek | None:
    """``None`` where *term* admits nothing at all after *coordinate*.

    A null coordinate is *at* the nulls rather than at any value, so what follows
    it is the non-nulls under Nulls First and nothing at all under Nulls Last —
    a depth that admits nothing contributing no branch of its own.
    """
    if coordinate is None:
        return _null_leaf(term, negated=True) if term.placement == "first" else None
    strict = _comparison_leaf(term, ">" if term.direction == "asc" else "<", coordinate)
    if term.placement == "last":
        return ComposedSeek(
            _SeekJunction("or", (strict.node, _null_leaf(term).node)),
            (*strict.binds, *term.path_binds),
            (*strict.neutral_types, *(None for _ in term.path_binds)),
        )
    return strict


def _ties_with(term: ContinuationTerm, coordinate: Any) -> ComposedSeek:
    if coordinate is None:
        return _null_leaf(term)
    return _comparison_leaf(term, "=", coordinate)


def _hoisted_range(term: ContinuationTerm, coordinate: Any) -> ComposedSeek:
    return _comparison_leaf(term, ">=" if term.direction == "asc" else "<=", coordinate)


def _comparison_leaf(term: ContinuationTerm, comparator: str, coordinate: Any) -> ComposedSeek:
    canonical = portable_literal.canonicalize_observed(coordinate, term.neutral_type)
    return ComposedSeek(
        f"{term.compared} {comparator} ?",
        (*term.path_binds, canonical),
        (*(None for _ in term.path_binds), term.neutral_type),
    )


def _null_leaf(term: ContinuationTerm, *, negated: bool = False) -> ComposedSeek:
    return ComposedSeek(
        f"{term.tested} is {'not ' if negated else ''}null",
        tuple(term.path_binds),
        tuple(None for _ in term.path_binds),
    )


# --- the hidden cells a page captures its coordinates through -----------------


CAPTURE_ALIAS = "parallax_seek_"
"""The framework-owned result alias prefix a page captures each coordinate under."""


def capture_aliases(case: Case, terms: list[ContinuationTerm]) -> list[str]:
    """The result alias each term's coordinate cell is projected under, in order.

    Allocated hygienically over every result key the model can carry under an
    authored name (`m-sql`), the way a wrapped union's result aliases are: its
    Column spellings, and the member spellings a Relational Document Layout fans
    a resident member out under, which claim no Column and so may spell one. A
    model that authors either as `parallax_seek_0` keeps that key for itself, and
    the coordinate that would have collided with it takes the next free index —
    two cells under one result key would be one entry in the row a page returns,
    and a fan-out would overwrite the raw capture cell outright.
    """
    reserved = {slot.column for table in case.model.storage_layout.tables for slot in table.columns}
    reserved |= {
        member.column
        for entity in case.model.entities
        for member in case.model.storage_layout.document(entity.canonical_name).members
    }
    aliases: list[str] = []
    index = 0
    for _term in terms:
        while f"{CAPTURE_ALIAS}{index}" in reserved:
            index += 1
        aliases.append(f"{CAPTURE_ALIAS}{index}")
        index += 1
    return aliases


def without_captured_coordinates(
    rows: list[dict[str, Any]], aliases: list[str]
) -> list[dict[str, Any]]:
    """``rows`` with the hidden coordinate cells lifted off, by their own names.

    A coordinate is framework-owned provenance rather than a member — the same
    standing the inheritance discriminator has — so it never reaches the graph a
    page publishes, and a delivered root carries exactly what the eager read of
    the same query gives it. Lifted by the aliases this delivery allocated
    rather than by the prefix, so an authored Column spelled like one survives.
    """
    lifted = set(aliases)
    return [{key: value for key, value in row.items() if key not in lifted} for row in rows]


def capture_binds(terms: list[ContinuationTerm]) -> list[Any]:
    """The Document Paths a page's coordinate cells bind, in term order.

    A cell is emitted from the same resolution as the term's own ordering
    clause, so a resident member's cell binds the same path that clause does and
    a Column-mapped one binds nothing.
    """
    return [bind for term in terms for bind in term.path_binds]


def refuse_an_uncaptured_page(
    case: Case,
    dialect: str,
    source: str,
    sql: str,
    terms: list[ContinuationTerm],
    aliases: list[str],
) -> None:
    """Refuse a page that does not project one coordinate cell per term.

    A streamed delivery advances on what the database evaluated for each ordering
    term, which reaches it as a hidden result cell under the alias that term was
    allocated — allocation runs in term order and skips a reserved spelling, so
    an alias is not necessarily at its term's own index — and emitted from that
    term's own compared expression, never as a reuse of a projected cell, whose
    expression and carrier coincide only by accident.

    Graded as the trailing cells of the select list, through the same member
    spelling the seek's own leaves are graded through, so a page capturing the
    wrong expression fails here rather than passing on the rows it happened to
    reach.
    """
    expected = [(alias, term.compared) for alias, term in zip(aliases, terms, strict=True)]
    projections = sqlglot.parse_one(sql, read=sqlglot_dialect(dialect)).expressions
    captured = [
        _captured_cell(cell, dialect) for cell in projections[len(projections) - len(terms) :]
    ]
    if captured != expected:
        raise CaseFailure(
            f"{case.path.name}: {source} ({dialect}) ends its projection with {captured!r}, "
            f"not the coordinate cells {expected!r}. A streamed page captures one hidden cell "
            f"per Continuation Order term, under the alias that term was allocated and emitted "
            f"from the expression the page is ordered by, after everything the read's own "
            f"projection selected."
        )


def _captured_cell(cell: Expr, dialect: str) -> tuple[str, str]:
    """One projected cell as its alias and the member it reads."""
    if not isinstance(cell, exp.Alias):
        return ("", _seek_member(cell, dialect))
    return (cell.alias, _seek_member(cell.this, dialect))


# --- grading one page's own text ---------------------------------------------


def seek_splice(first_page_sql: str, later_page_sql: str) -> tuple[int, int]:
    """The span of *later_page_sql* its seek was spliced into.

    A continuing page's statement is the first page's with the seek spliced in as
    ONE contiguous conjunct, so the two texts agree up to the splice and again
    after it, and every bind hole they share before it is one the query itself
    carries. Recovering the span this way is what lets the seek be graded against
    a read whose remaining clauses — a subtype narrowing's tag guard, say — bind
    AFTER the predicate the seek is conjoined to.

    Both shared ends stop at a token boundary rather than at the last matching
    character: a maximal character run can stop inside a bind hole or inside a
    column reference the query and the seek spell alike, which would leave half a
    token in the span and hide the comparator it belongs to.
    """
    head = 0
    for authored, continuing in zip(first_page_sql, later_page_sql, strict=False):
        if authored != continuing:
            break
        head += 1
    head = later_page_sql.rfind(" ", 0, head) + 1
    tail = 0
    shared = max(min(len(first_page_sql), len(later_page_sql)) - head, 0)
    while tail < shared and first_page_sql[-1 - tail] == later_page_sql[-1 - tail]:
        tail += 1
    while tail > 0 and later_page_sql[len(later_page_sql) - tail - 1] != " ":
        tail -= 1
    return head, len(later_page_sql) - tail


_SEEK_COMPARATORS: dict[type[Expr], str] = {
    exp.GT: ">",
    exp.GTE: ">=",
    exp.LT: "<",
    exp.LTE: "<=",
    exp.EQ: "=",
}

# The splice recovers the seek together with the keyword joining it to the rest
# of the predicate: the `where` or `and` that introduces the conjunct, or the
# `and` that joins it to the predicate it precedes.
_SEEK_BOUNDARY = re.compile(r"^(?:where|and)\s+|\s+and$", re.IGNORECASE)


def _spelled_seek(fragment: str, dialect: str) -> _SeekNode:
    """The Boolean expression the spliced *fragment* actually spells.

    Parsed rather than scanned for the comparisons it mentions: a seek is a
    composed expression, and a page that grouped its branches differently, joined
    them with the other operator, or negated one of them mentions exactly the
    comparisons a correct page mentions, in exactly their order. What the splice
    carries along either side of the conjunct is the boundary keyword that
    introduces or joins it, which is dropped here; a fragment that then parses as
    no expression at all is carried into the mismatch as its own text rather than
    refused for a second reason.
    """
    text = _SEEK_BOUNDARY.sub("", fragment.strip())
    try:
        parsed = sqlglot.parse_one(text, read=sqlglot_dialect(dialect))
    except SqlglotError:
        return text
    return _seek_node(parsed, dialect)


def _seek_node(expression: Expr, dialect: str) -> _SeekNode:
    if isinstance(expression, exp.Paren):
        return _seek_node(expression.this, dialect)
    if isinstance(expression, exp.And | exp.Or):
        operator: Literal["and", "or"] = "and" if isinstance(expression, exp.And) else "or"
        return _joined(
            operator,
            [_seek_node(expression.this, dialect), _seek_node(expression.expression, dialect)],
        )
    if isinstance(expression, exp.Not):
        negated = _null_test(expression.this, dialect, negate=True)
        if negated is not None:
            return negated
        return _SeekJunction("not", (_seek_node(expression.this, dialect),))
    plain = _null_test(expression, dialect, negate=False)
    if plain is not None:
        return plain
    comparator = _SEEK_COMPARATORS.get(type(expression))
    if comparator is not None and isinstance(expression.expression, exp.Placeholder):
        return f"{_seek_member(expression.this, dialect)} {comparator} ?"
    return expression.sql()


def _null_test(expression: Expr, dialect: str, *, negate: bool) -> str | None:
    """*expression* as the one null-test leaf a seek composes, or ``None`` where it
    is not a leaf the composed side could have built.

    A negated null test has two production spellings — `x is not null` and
    `not x is null` — and a dialect may parse either into the other's tree, so ONE
    negation is folded into the leaf rather than left as a junction the composed
    side never builds. A SECOND negation is not folded: a Continuation Order
    composes no negation at any depth, so `not x is not null` is drift, and
    cancelling the pair would admit it wherever a dialect happens to parse the
    inner `not` into the null test itself.
    """
    while isinstance(expression, exp.Paren):
        expression = expression.this
    if not (isinstance(expression, exp.Is) and isinstance(expression.expression, exp.Null)):
        return None
    if negate and expression.args.get("negate"):
        return None
    negated = negate or bool(expression.args.get("negate"))
    return f"{_seek_member(expression.this, dialect)} is {'not ' if negated else ''}null"


def _seek_member(expression: Expr, dialect: str) -> str:
    """The member a seek leaf compares, in the spelling the composed side uses.

    A Column answers its own bare name, dropping the alias the statement
    qualifies it with. A document-resident member has no name in the statement at
    all — its Document Path rides in a bind hole — so what the text can be held
    to is the Structured Column it extracts from and the CAST the declared type
    compares through, target included: another target can order the same page's
    rows the same way and carry the same cursor forward, so a wrong one survives
    the next page and only the target itself refuses it. WHICH member it is stays
    a bind question, and the seek's bind list is where it is asked.
    """
    if isinstance(expression, exp.Cast):
        source = _extraction_source(expression.this, dialect)
        if source is not None:
            return f"cast({source} extraction as {_cast_target_spelling(expression.to, dialect)})"
    source = _extraction_source(expression, dialect)
    if source is not None:
        return f"{source} extraction"
    return expression.name if isinstance(expression, exp.Column) else expression.sql()


def _extraction_source(node: Expr, dialect: str) -> str | None:
    """The Structured Column *dialect*'s document extraction reads, else ``None``.

    The extraction takes that column as its first argument and its Document Path
    as bind holes — one per segment on Postgres, one whole JSON path on MariaDB —
    so a call carrying a literal path, a second column, or a folded expression is
    not the extraction `m-sql` compares through. sqlglot parses MariaDB's
    ``json_value`` into a node of its own and leaves the Postgres spelling an
    anonymous call, so each dialect is matched by the shape it emits.
    """
    extraction = _DOCUMENT_EXTRACTION.get(dialect)
    if extraction is None:
        return None
    if isinstance(node, exp.JSONValue):
        if extraction != "json_value":
            return None
        column, path = node.this, [node.args.get("path")]
    elif isinstance(node, exp.Anonymous) and node.name.lower() == extraction:
        column, *path = node.expressions or [None]
    else:
        return None
    if not path or not all(isinstance(segment, exp.Placeholder) for segment in path):
        return None
    return column.name if isinstance(column, exp.Column) else None


def _render_seek(node: _SeekNode) -> str:
    if isinstance(node, str):
        return node
    if node.operator == "not":
        return f"not {_render_seek(node.operands[0])}"
    return f"({f' {node.operator} '.join(_render_seek(operand) for operand in node.operands)})"


class PageText(NamedTuple):
    """One continuing page's SQL, and where a failure should say it was read.

    ``source`` is the authored list the pages came off — ``then.statements`` for a
    read case, a Scenario step's own ``scenario[<index>].statements`` — so a drift
    diagnostic names the member the case actually carries.
    """

    case: Case
    dialect: str
    source: str
    page: int
    first_root_sql: str
    root_sql: str


def refuse_a_drifting_page(
    text: PageText,
    seek: ComposedSeek,
    cursor: tuple[Any, ...],
    seek_shapes: dict[tuple[bool, ...], str],
) -> None:
    """Grade one continuing page's root SQL against the seek its order composes.

    Three rules, in the order a drift is worth reporting in. A continuing page
    carries a conjunct the first page has no coordinate for, so the two texts
    cannot be equal. Two continuing pages differ in text only where their
    coordinates differ in NULLNESS, a null one being sought through a null test
    rather than through a comparison. And the page is otherwise the first page's
    statement with that one conjunct spliced in, spelling exactly the Boolean
    expression the Continuation Order composes for the coordinates it is seeking
    past — which is what grades the seek's DIRECTION and its BRANCHING, the parts
    of it no bind can carry.
    """
    case, dialect, source, page, first_root_sql, root_sql = text
    where = f"{case.path.name}: {source} ({dialect}) page {page + 1}"
    if root_sql == first_root_sql:
        raise CaseFailure(
            f"{where} repeats the FIRST page's root SQL. A continuing page carries a seek "
            f"conjunct the first page has no coordinate for, so the two texts cannot be equal."
        )
    seeking = seek_shapes.setdefault(tuple(coordinate is None for coordinate in cursor), root_sql)
    if root_sql != seeking:
        raise CaseFailure(
            f"{where} root SQL differs from an earlier page seeking the same shape of "
            f"coordinates. Two continuing pages differ in text only where their coordinates "
            f"differ in NULLNESS; otherwise they seek the same way and differ only in what "
            f"they bind."
        )
    spliced_at, spliced_to = seek_splice(first_root_sql, root_sql)
    if root_sql[:spliced_at] + root_sql[spliced_to:] != first_root_sql:
        raise CaseFailure(
            f"{where} root SQL is not the first page's with ONE conjunct spliced into it. A "
            f"continuing page reads the same rows the same way and differs only by the "
            f"seek:\n  first:      {first_root_sql}\n  continuing: {root_sql}"
        )
    spelled = _spelled_seek(root_sql[spliced_at:spliced_to], dialect)
    if spelled != seek.node:
        raise CaseFailure(
            f"{where} seeks {_render_seek(spelled)}, not {_render_seek(seek.node)}. A page "
            f"compares each Continuation Order term in that term's OWN direction and "
            f"placement, one branch per tie depth DISJOINED, behind the range a non-nullable "
            f"leading term hoists."
        )
