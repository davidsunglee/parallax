"""Write grading: what a golden write statement must be for the input it renders.

One neutral write input (①) and one golden statement (②) are cross-checked here,
for every lane that authors a write — write sequences, conflicts, bitemporal
milestone closes, pk generation, and Unit Work Scenario steps. A caller states a
case, an entity, and the statement it is grading, and gets back a classified row,
a derived bind row, an address, or a refusal.

What this module decides internally: how a flat attribute-named row resolves to
physical columns and a primary key, which (target, mutation) pair may observe a
version, what a milestone close's address binds and in which order, which column
carries the optimistic version or the inheritance tag, and how a rendered
statement is taken apart — its column lists, its assignments, where its predicate
begins, and which object it addresses. SQL text is scanned and parsed here and
nowhere else in the harness's write grading: a physical name may be reserved and
therefore quoted, a comma or a `where` may sit inside an identifier, and a
subquery's predicate belongs to the inner query, so every reader that takes a
golden apart goes through one grammar rather than a pattern of its own.

What stays outside: case-shape routing, provisioning, the ordered composition of
a lane's own steps, Object Query semantics, and the model facts
:mod:`.inheritance` and :mod:`.storage_layout` own — this module consumes those
rather than re-deriving them.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, NamedTuple

import sqlglot
from sqlglot import exp
from sqlglot.expressions.core import Expr

from .case import Case, Entity
from .case_assertions import CaseFailure, write_value_equal
from .document_codec import encode_document, encode_leaf
from .inheritance import tag_of
from .keyed_write_validate import states_framework_marker
from .sql_canonical import sqlglot_dialect
from .storage_layout import DocumentMember
from .temporality import TEMPORAL_DIMENSION_RANK

# --- the write verbs and control keys a neutral write input speaks ---------------


# The mutations that OPEN a row with no prior state to close: the unbounded
# `insert` and its Valid-Time-bounded `insertUntil` sibling. Such an entry
# resolves no source — there is no row for a read to return — and on a temporal
# target it opens a rectangle rather than splitting one.
OPENING_MUTATIONS = ("insert", "insertUntil")

# The keyed write mutations a public verb states. `cascadeDelete` is deliberately
# absent: it is not a Keyed Mutation, no verb states it, and an entry writing one
# therefore resolves no source.
_KEYED_MUTATIONS = (
    *OPENING_MUTATIONS,
    "update",
    "delete",
    "terminate",
    "updateUntil",
    "terminateUntil",
)

# The ONE reserved observation control key a case write row may spell
# (`compatibility-case.schema.json` `$defs/writeRow`). Which (target, mutation)
# pair is entitled to spell it is :func:`_observation_refusal`'s answer — one
# shared `writeRow` definition spans every authoring location, so the schema
# cannot express it.
_VERSION_OBSERVATION_KEY = "observedVersion"

# The two halves of an observed milestone's own EDGE coordinate. Neither is a
# write-row key in any authoring location: a temporal write observes a whole
# predecessor milestone, which no flat row cell can name, so both ride beside the
# write, at `when.observedTxStart` / `when.observedValidStart` — and, on a retry
# attempt, `observedTxStart` alone, since the edge form is single-attempt only
# (`m-case-format`). Named here so a row that spells one is refused by the rule
# rather than by the generic "not a member" diagnosis.
MILESTONE_COORDINATE_KEYS = ("observedTxStart", "observedValidStart")


# --- what one choreography unit's keyed writes owe -------------------------------


def _entry_entity(case: Case, entry: dict[str, Any]) -> Entity:
    """The Entity one write entry targets, resolved from the spelling it authored
    — canonical or an unambiguous bare local name, which name one Entity."""
    return case.model.entity(entry.get("entity", ""))


def _entry_object_keys(case: Case, entry: dict[str, Any]) -> list[tuple[str, tuple[Any, ...]]]:
    """Which object each of ``entry``'s rows names, by its declared primary key.

    The entity's flattened definition carries the family's key, so a concrete
    subtype resolves the same key its root declares, and each object is named by
    the CANONICAL Entity spelling, so two entries spelling one target differently
    name one object rather than two.
    """
    entity = _entry_entity(case, entry)
    names = [a["name"] for a in entity.attributes if a.get("primaryKey")]
    return [
        (entity.canonical_name, tuple(repr(row.get(name)) for name in names))
        for row in entry.get("rows", [])
    ]


def unit_resolving_reads(case: Case, entries: list[dict[str, Any]]) -> int:
    """The resolving reads ONE choreography unit owes: one per target Entity whose
    existing-row keyed writes address a row this unit did not itself open.

    A keyed write verb is addressed and licensed by a value a read published, so
    a unit writing against existing state reads it first — once per Entity,
    resolving every row of that Entity the unit addresses, because a read
    interleaved between two writes would force-flush the first and destroy the
    batch collapse the goldens pin. Three kinds of entry owe nothing: an insert
    OPENS its row, a row an earlier entry of the same unit opened is
    read-your-own-writes, and an entry carrying a DB-computed write marker states
    the framework's own bookkeeping, which no public verb accepts.

    Targets are counted by their canonical spelling, so two entries naming one
    Entity two ways owe one read between them.
    """
    opened: set[tuple[str, tuple[Any, ...]]] = set()
    needed: set[str] = set()
    for entry in entries:
        mutation = entry.get("mutation")
        if mutation in OPENING_MUTATIONS:
            opened.update(_entry_object_keys(case, entry))
            continue
        if mutation not in _KEYED_MUTATIONS:
            continue
        entity = _entry_entity(case, entry)
        if states_framework_marker(entity, entry):
            continue
        if any(key not in opened for key in _entry_object_keys(case, entry)):
            needed.add(entity.canonical_name)
    return len(needed)


# --- the framework-derived columns a write gates and routes on -------------------


def version_column(entity: Entity) -> str | None:
    """The physical column of an entity's explicit optimistic-lock version, or None.

    A VERSIONED entity carries an attribute-level ``optimisticLocking: true`` version
    (m-opt-lock); the value advance (``initial 1`` / ``observed + 1``) and gate are DERIVED,
    so the column never appears in the neutral write input (①). A temporal entity
    locks via its Transaction-Time ``in_z`` timestamp and declares no such attribute.
    """
    for attribute in entity.attributes:
        if attribute.get("optimisticLocking"):
            return attribute["column"]
    return None


def tag(entity: Entity) -> tuple[str, Any] | None:
    """The (column, value) a table-per-hierarchy INSERT writes, or None (m-inheritance).

    A TABLE-PER-HIERARCHY concrete subtype maps to a shared table discriminated by
    the root's ``tag`` column; the value THIS subtype's rows carry is its
    ``tagValue``. On a write that column is FRAMEWORK-DERIVED — set from the declared
    ``tagValue``, never carried in the neutral write input (①), exactly as the version
    column's advance is derived. A TABLE-PER-CONCRETE-SUBTYPE subtype has its own
    table and no tag (``tagValue`` is absent, m-inheritance), so this returns
    ``None`` and the write is an ordinary single-table write. The concrete subtype's
    flattened definition (:func:`inheritance.resolve_effective_definition`) carries
    both the resolved root ``tag`` column and the subtype's own ``tagValue``.
    """
    return tag_of(entity.runtime_facts)


# --- classifying one neutral write row against its entity ------------------------


def _observation_refusal(entity: Entity, mutation: str) -> str | None:
    """Why a write row against *entity* under *mutation* may not spell the reserved
    ``observedVersion`` control key — ``None`` when that pair is the ONE the case
    vocabulary entitles to spell it.

    This is the whole licensing rule `m-unit-work`'s "Absence is structural"
    states, restated by the case schema's own ``observedVersion`` prose ("absent
    on a versioned insert and on a non-versioned write"), and it is TOTAL over
    every (target, mutation) pair a case can author. A VERSIONED, NON-TEMPORAL
    update or delete may spell the key; nothing else may:

    - a TEMPORAL target's write observes a whole predecessor MILESTONE, which no
      flat row cell can name, and a close's Transaction-Time gate is authored
      beside the write (``when.observedTxStart`` or the attempt's own field,
      `m-case-format`) rather than inside the row;
    - an INSERT opens a row rather than writing against one, so an observed
      version names a milestone that does not yet exist;
    - an UNVERSIONED non-temporal target has no version to observe, so an
      observed version on it is evidence about nothing.

    Deciding it HERE, at the one seam every ① row is classified through, is what
    keeps the neutral grader's table the same table the conformance engine
    enforces: a consumer that merely ignores the value it was handed accepts a
    case the engine refuses, and the two implementations then disagree about
    which cases the corpus even admits.
    """
    if entity.is_temporal:
        return (
            f"a temporal row spells no {_VERSION_OBSERVATION_KEY!r} (m-unit-work: a temporal "
            f"write observes a whole predecessor milestone, which no flat row cell can name, "
            f"and a close's observed `in_z` gate rides beside the write)"
        )
    if mutation in OPENING_MUTATIONS:
        return (
            f"an insert row spells no {_VERSION_OBSERVATION_KEY!r} (m-unit-work: inserts have "
            f"no observation — an observed version names the milestone a write against an "
            f"EXISTING row observed)"
        )
    if version_column(entity) is None:
        return (
            f"an unversioned row spells no {_VERSION_OBSERVATION_KEY!r} (m-unit-work: "
            f"unversioned Non-Temporal writes have no observation — there is no observed "
            f"version for it to name)"
        )
    return None


def classify_write_row(
    case: Case, entity: Entity, row: dict[str, Any], *, mutation: str, opening: bool
) -> tuple[dict[str, Any], Any, dict[str, Any], Any]:
    """Classify a flat attribute-named ① row against *entity*'s metamodel.

    Mirrors the fixture loader's attribute→column resolution. Every key is either
    the reserved control key ``observedVersion`` — admitted only where
    :func:`_observation_refusal` entitles this (*entity*, *mutation*) pair to
    spell it, so an unobservable row is refused HERE rather than accepted and
    discarded by whichever consumer has no use for it — an ENTITY ATTRIBUTE name,
    or a
    top-level VALUE-OBJECT name (a bad key raises :class:`CaseFailure`, so the
    neutral input can't silently name a non-member); the primary-key attribute's
    value is split into the pk, every other attribute AND every value object into
    the domain ``set`` — all keyed by physical column. A value object resolves to
    its single structured-document column and its value is the WHOLE document
    (m-value-object): it binds atomically as one document value at its Document-tier
    slot, never decomposed into path-level binds. Because that role is resolved
    HERE (from the entity's declared members), a value-object column's value is ALWAYS
    literal document content downstream — never a DB-computed marker
    (``computed`` / ``increment``), even when the document is marker-SHAPED; marker
    interpretation applies only to a scalar-attribute column.

    A value object's ① value is the occurrence's neutral write input, so it is
    ENCODED here (``document_codec``) rather than taken as the document. That is what
    makes the golden bind graded rather than trusted: the harness derives the document
    a conforming writer must produce from the case's own member values, and
    :func:`assert_write_values` compares it to the authored bind — so a leaf spelled
    any other way fails the case instead of surviving it. An OPENING statement
    additionally binds every `many` occurrence's column whether ① names it or not:
    absence and the empty array are one logical zero state (m-value-object).

    Under Relational Document Layout the members the layout moved inside the shared
    Structured Column resolve to THAT one column rather than to columns of their own,
    and their derived value depends on what the statement does with them: an opening
    statement writes the whole document, so they are composed into it here, while a
    revising one patches only the paths its own row names and takes them from
    those assignments instead. ``opening`` is therefore the caller's
    answer, from the step's own mutation, and never inferred from the row.
    """
    pk_columns = {a["column"] for a in entity.attributes if a.get("primaryKey")}
    layout_document = case.model.storage_layout.document(entity.canonical_name)
    document_column, resident = layout_document.column, layout_document.members
    resident_columns = {member.column for member in resident}
    columns: dict[str, Any] = {}
    set_columns: dict[str, Any] = {}
    pk_value: Any = None
    observed_version: Any = None
    for key, value in row.items():
        if key in MILESTONE_COORDINATE_KEYS:
            raise CaseFailure(
                f"{case.path.name}: {entity.name} {mutation!r}: a write row spells no {key!r} "
                f"(m-case-format: an observed milestone's own edge coordinate rides beside the "
                f"write, at `when.observedTxStart` / `when.observedValidStart`, or an "
                f"attempt's own `observedTxStart`; a writeRow reserves "
                f"{_VERSION_OBSERVATION_KEY!r} alone and every other key names an entity member)"
            )
        if key == _VERSION_OBSERVATION_KEY:
            refusal = _observation_refusal(entity, mutation)
            if refusal is not None:
                raise CaseFailure(f"{case.path.name}: {entity.name} {mutation!r}: {refusal}")
            observed_version = value
            continue
        try:
            column = entity.attribute_by_name(key)["column"]
        except KeyError:
            # Not an attribute — a value object binds as ONE document at its
            # Document-tier slot (m-value-object); the neutral input names it
            # like a scalar attribute and its value is the whole document.
            try:
                value_object = entity.value_object_by_name(key)
            except KeyError as exc:
                raise CaseFailure(
                    f"{case.path.name}: writeSequence row key {key!r} is not an attribute "
                    f"or value object of {entity.name} — the neutral write input speaks "
                    f"ATTRIBUTE / value-object names, not columns."
                ) from exc
            column = value_object["column"]
            if column not in resident_columns:
                value = encode_document(value_object, value)
        if column in resident_columns:
            continue  # the Structured Column carries it; composed below
        columns[column] = value
        if column in pk_columns:
            pk_value = value
        else:
            set_columns[column] = value
    if opening:
        # A `many` occurrence with a Column of its own binds on every opening
        # statement whether or not the row names it: absence and the empty array are
        # one logical zero state, so an unnamed `many` stores `[]` (m-value-object) —
        # the same answer the codec composes for one inside a document.
        for value_object in entity.value_objects:
            column = value_object["column"]
            if value_object.get("multiplicity", "one") != "many" or column in resident_columns:
                continue
            if value_object["name"] not in row:
                columns[column] = encode_document(value_object, [])
                set_columns[column] = columns[column]
    if document_column and opening:
        # The Structured Column binds on EVERY opening statement, including one for
        # an Entity whose members are all direct: it is `NOT NULL` and every governed
        # row carries a document, the empty object included (m-storage-layout).
        document = _entity_document(entity, resident, row)
        columns[document_column] = document
        set_columns[document_column] = document
    return columns, pk_value, set_columns, observed_version


def _entity_document(
    entity: Entity, resident: tuple[DocumentMember, ...], row: dict[str, Any]
) -> dict[str, Any]:
    """The complete Structured Column document one opening ① row implies.

    Composed over EVERY document-resident member rather than only the named ones,
    because presence is the codec's classification: an omitted key stays absent, an
    authored null becomes JSON null, and a ``many`` occurrence always contributes its
    array. Members are emitted in canonical placement order — every attribute, then
    every occurrence — so one set of member values yields exactly one document.
    """
    document: dict[str, Any] = {}
    for member in resident:
        name = member.name
        if member.type_spelling is None:
            occurrence = entity.value_object_by_name(name)
            if name in row:
                document[name] = encode_document(occurrence, row[name])
            elif occurrence.get("multiplicity", "one") == "many":
                document[name] = []
            continue
        if name in row:
            document[name] = encode_leaf(member.type_spelling, row[name])
    return document


# --- the address a milestone close carries ---------------------------------------


def _as_of_axes(entity: Entity) -> list[dict[str, Any]]:
    """*entity*'s As-Of Axes in canonical dimension rank (Valid Time first)."""
    return sorted(
        entity.temporal_runtime_axes,
        key=lambda axis: TEMPORAL_DIMENSION_RANK[axis["dimension"]],
    )


def close_address_binds(case: Case, entity: Entity, pk: Any, valid_end: Any) -> list[Any]:
    """The binds a milestone close's ADDRESS carries, in rendered predicate order.

    A close addresses the ONE stored milestone it means to close, and that address is
    identical in both concurrency modes: the primary key, the table-per-hierarchy tag
    GUARD that rides the identity predicates right after it (m-inheritance), then one
    exclusive upper bound PER As-Of Axis in canonical dimension rank. The
    Transaction-Time end is invariantly the open bound, because only a
    Transaction-Time-current milestone is closable; the Valid-Time end is the observed
    rectangle's OWN end, which may be finite — a key plus the open Transaction-Time
    bound alone would select every disjoint current rectangle of that key
    (`m-bitemp-write`). An optimistic gate is appended AFTER the address, never woven
    into it.
    """
    discriminator = tag(entity)
    binds: list[Any] = [pk] if discriminator is None else [pk, discriminator[1]]
    for axis in _as_of_axes(entity):
        if axis["dimension"] != "valid-time":
            binds.append(axis.get("infinity", "infinity"))
            continue
        if valid_end is None:
            raise CaseFailure(
                f"{case.path.name}: a Bitemporal close of {entity.name} carries no observed "
                f"Valid-Time end — the address needs one exclusive upper bound per As-Of "
                f"Axis, and only the Transaction-Time one is invariant."
            )
        binds.append(valid_end)
    return binds


# --- reading a rendered golden statement apart -----------------------------------


def is_existing_row_statement(statement: str) -> bool:
    """True for an existing-row write (UPDATE / DELETE), False for an INSERT.

    A table-per-hierarchy existing-row statement carries the tag guard; an INSERT
    derives the tag COLUMN instead. This classifies by the leading verb so it covers
    the milestone TEMPORAL closes / inactivations (an ``update <table> set out_z = ?
    …``, m-txtime-write / m-bitemp-write) alongside the plain non-temporal
    ``update`` / ``delete`` — both are existing-row writes that MUST carry the guard,
    while the chained milestone INSERTs are not.
    """
    head = statement.lstrip().lower()
    return head.startswith("update ") or head.startswith("delete ")


def parse_insert_columns(case: Case, statement: str) -> list[str]:
    """The columns an INSERT names: the parenthesised list following its target table.

    Read through :func:`_sql_scan` for the same reason its `set`-clause sibling is: a
    quoted identifier may itself carry a bracket or a comma, and neither is syntax
    there.
    """
    columns = _insert_column_list(statement)
    if columns is None:
        raise CaseFailure(
            f"{case.path.name}: could not parse the INSERT column list from golden {statement!r}."
        )
    return [column.strip() for column in _top_level_commas(columns)]


def _insert_column_list(statement: str) -> str | None:
    """The text between the parentheses that follow an INSERT's target table, or
    ``None`` when the statement is not an INSERT or opens no such list."""
    if not _keyword_at(statement.lstrip().lower(), 0, "insert"):
        return None
    opened: int | None = None
    for index, char, depth in _sql_scan(statement):
        if char == "(" and depth == 1 and opened is None:
            opened = index + 1
        elif char == ")" and depth == 0 and opened is not None:
            return statement[opened:index]
    return None


def parse_set_columns(statement: str) -> list[str] | None:
    """The columns an UPDATE assigns, in the order its `set` clause renders them, or
    ``None`` when the statement carries no `set` clause at all.

    Assignment order IS bind order, so a caller reading the value bound to one
    column finds it at that column's own position. A DELETE and an INSERT assign
    nothing and answer ``None``; whether reaching one is a defect belongs to the
    caller that knows which verb its lane expected.
    """
    clause = _set_clause(statement)
    if clause is None:
        return None
    return [_assigned_column(piece) for piece in _top_level_commas(clause)]


def _predicate_bind_offset(statement: str) -> int | None:
    """How many binds precede the outer predicate's own first placeholder, or None
    when the statement carries no outer predicate.

    Scanned through :func:`_sql_scan` for the reason every reader that takes a
    golden apart by position is: a `?` inside a string literal binds nothing, and a
    `where` inside a quoted identifier or a subquery opens no predicate of this
    statement's own.
    """
    lowered = statement.lower()
    preceding = 0
    for position, char, depth in _sql_scan(statement):
        if depth == 0 and _keyword_at(lowered, position, "where"):
            return preceding
        if char == "?":
            preceding += 1
    return None


def _sql_scan(sql: str) -> Iterator[tuple[int, str, int]]:
    """Each character of *sql* OUTSIDE a quoted identifier or string literal, with
    its index and its bracket depth.

    Every reader that takes a golden statement apart by COLUMN goes through here —
    an INSERT's column list, an UPDATE's `set` clause, its assignments, and each
    assignment's own `=` — because a column name is any nonempty string and a
    dialect quotes one that is reserved or otherwise non-simple (`m-dialect`): a
    comma, a bracket, an `=`, and the word `where` can each sit inside an
    identifier, and none of them is syntax there.
    """
    quote = ""
    depth = 0
    for index, char in enumerate(sql):
        if quote:
            if char == quote:
                quote = ""
            continue
        if char in "\"`'":
            quote = char
            continue
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        yield index, char, depth


def _keyword_at(lowered: str, index: int, keyword: str) -> bool:
    """Whether *keyword* occupies a whole word at *index* of a lowercased statement."""
    if not lowered.startswith(keyword, index):
        return False
    before = lowered[index - 1] if index else " "
    after = lowered[index + len(keyword) :][:1] or " "
    return not _word_char(before) and not _word_char(after)


def _word_char(char: str) -> bool:
    return char.isalnum() or char == "_"


def _set_clause(statement: str) -> str | None:
    """An UPDATE's `set` clause: what sits between its own `set` and `where` keywords.

    Both delimiters are read at bracket depth zero and outside quotes, so neither a
    subquery's own keyword nor a column named `set` or `where` — legal, and quoted
    for exactly that reason — delimits the clause.
    """
    lowered = statement.lower()
    start: int | None = None
    for index, _char, depth in _sql_scan(statement):
        if depth:
            continue
        if start is None:
            if _keyword_at(lowered, index, "set"):
                start = index + len("set")
        elif _keyword_at(lowered, index, "where"):
            return statement[start:index].strip()
    return None


def _assigned_column(assignment: str) -> str:
    """The column one `set` term names: what sits left of its own top-level `=`."""
    for index, char, depth in _sql_scan(assignment):
        if char == "=" and depth == 0:
            return assignment[:index].strip()
    return assignment.strip()


def _top_level_commas(clause: str) -> list[str]:
    """*clause* split on the commas that separate its assignments.

    A `set` term's right-hand side may itself be a call taking commas — the
    document mutation expression is nested `jsonb_set` calls on Postgres and one
    N-pair `json_set` on MariaDB (m-dialect) — so only a comma at bracket depth
    zero ends an assignment. A comma inside a quoted identifier or a string literal
    ends nothing at all: `set "payload,archive" = ?` is one assignment, not two.
    """
    parts: list[str] = []
    start = 0
    for index, char, depth in _sql_scan(clause):
        if char == "," and depth == 0:
            parts.append(clause[start:index])
            start = index + 1
    parts.append(clause[start:])
    return parts


# --- the write grammar every predicate fact is projected out of ------------------


def _dml_target(statement: str, dialect: str) -> exp.Identifier | None:
    """The identifier *statement* names its target table with, or None when it is no
    table-targeting DML for *dialect*.

    The one reader of WHICH TABLE a write lands in, covering the ``INSERT`` that
    :func:`_existing_row_write` does not: table-per-concrete-subtype routing asks it of
    every statement a write emits, because there the table IS the concrete subtype
    (`m-inheritance`). Taken from the parse so the identifier keeps its own quoting,
    which is what decides whether the spelling is the model's table (:func:`_names`) —
    a reserved or otherwise non-simple physical name is rendered QUOTED (`m-dialect`).
    """
    with contextlib.suppress(sqlglot.ParseError):
        return _dml_target_of(sqlglot.parse_one(statement, read=sqlglot_dialect(dialect)))
    return None


def _dml_target_of(tree: Expr) -> exp.Identifier | None:
    """The target-table identifier of an already-parsed ``INSERT`` / ``UPDATE`` /
    ``DELETE``, or None for any other statement.

    An ``INSERT`` carries its table inside the column-list schema; the existing-row
    verbs name it directly.
    """
    if not isinstance(tree, (exp.Insert, exp.Update, exp.Delete)):
        return None
    target = tree.this
    if isinstance(target, exp.Schema):
        target = target.this
    if not isinstance(target, exp.Table) or not isinstance(target.this, exp.Identifier):
        return None
    return target.this


class _ExistingRowWrite(NamedTuple):
    """The outer keyed DML a golden statement is: the identifier its ``UPDATE`` /
    ``DELETE`` names the target table with, and its own top-level predicate
    conjuncts."""

    table: exp.Identifier
    conjuncts: tuple[Expr, ...]


def _existing_row_write(statement: str, dialect: str) -> _ExistingRowWrite | None:
    """*statement* read as the existing-row write it is, or None when it is not one.

    The ONE reader of that grammar, which each consumer projects its own fact out of
    — which object the statement addresses (:func:`statement_object`), whether it
    gates on the optimistic version (:func:`has_version_gate`) — so what counts as
    an existing-row write, and what an unparseable or non-DML statement answers,
    is decided in one place for all of them.

    Read through the grammar rather than by pattern, because a reserved physical
    table or column is rendered QUOTED (`m-dialect`), the last ` where ` in the text
    may belong to a subquery, and a subquery's own predicate is a conjunct of the
    inner ``SELECT`` rather than of this one (:func:`_conjuncts`). A statement that
    does not parse for *dialect*, that is not an ``UPDATE`` / ``DELETE`` of a table,
    or that carries no outer predicate is no existing-row write: it addresses no
    object and gates on nothing.
    """
    with contextlib.suppress(sqlglot.ParseError):
        tree = sqlglot.parse_one(statement, read=sqlglot_dialect(dialect))
        if not isinstance(tree, (exp.Update, exp.Delete)):
            return None
        table, where = _dml_target_of(tree), tree.args.get("where")
        if table is not None and isinstance(where, exp.Where):
            return _ExistingRowWrite(table, tuple(_conjuncts(where.this)))
    return None


def _conjuncts(predicate: Expr) -> Iterator[Expr]:
    """*predicate*'s own top-level ``AND`` operands, parentheses flattened.

    A subquery yields as ONE opaque operand: its own predicate is a conjunct of the
    inner ``SELECT``, never of this one, which is exactly the distinction a text scan
    cannot make.
    """
    if isinstance(predicate, exp.And):
        yield from _conjuncts(predicate.left)
        yield from _conjuncts(predicate.right)
    elif isinstance(predicate, exp.Paren):
        yield from _conjuncts(predicate.this)
    else:
        yield predicate


def _gates_on(operand: Expr, column: str) -> bool:
    """Whether *operand* is the ``<column> = ?`` equality a gate renders."""
    bound = _bound_equality_identifier(operand)
    return bound is not None and _names(bound, column)


def _bound_equality_identifier(operand: Expr) -> exp.Identifier | None:
    """The identifier a ``<column> = ?`` conjunct names its column with, or None for
    any other operand.

    The one predicate shape both a gate and an address are written in, either way
    round, taken from the parse so the identifier keeps its own quoting — which is
    what decides whether the spelling is the model's column (:func:`_names`).
    """
    if not isinstance(operand, exp.EQ):
        return None
    left, right = operand.left, operand.right
    if isinstance(right, exp.Column) and isinstance(left, exp.Placeholder):
        left, right = right, left
    if isinstance(left, exp.Column) and isinstance(right, exp.Placeholder):
        return left.this if isinstance(left.this, exp.Identifier) else None
    return None


def _names(identifier: exp.Identifier, declared: str) -> bool:
    """Whether *identifier*, as a golden spells it, is the physical *declared* name.

    A QUOTED identifier keeps exactly the name it spells — quoting is what a
    reserved or otherwise non-simple physical name is rendered with, and the
    normalizer preserves it (`m-dialect`) — while an UNQUOTED one is folded by the
    database, so it names *declared* whenever the two differ only in case.
    Lowercasing both sides instead would read a quoted ``"Order"`` and a bare
    ``order``, two names one model may declare separately, as one identifier.
    """
    return identifier.name == declared or (
        not identifier.quoted and identifier.name.lower() == declared.lower()
    )


# --- which object an existing-row statement addresses ----------------------------


@dataclass(frozen=True)
class ObjectAddress:
    """Which object an existing-row statement writes: the target table it names, the
    key column it gates on, and the primary-key value its identity predicate binds.

    Table and key together ARE an Object Key — Entity Identity plus primary-key
    values (`m-unit-work`). Every structural Table has exactly one mapping owner
    (`m-storage-layout`) and object identity normalizes to the inheritance family
    (`m-identity-map`), so a table names ONE Entity Identity: a table-per-hierarchy
    family's shared table names that family, a table-per-concrete-subtype table its
    own subtype, and no two objects share a table and a primary key. Which concrete
    subtype of a shared table a golden claims is the one thing the address cannot
    say, so the settled lane grades it separately
    (:func:`assert_inheritance_write_routing`).

    The table and the key column are ASKED rather than read, and are held in the
    golden's own spelling to make that the only way to ask: quoting is what a
    reserved or otherwise non-simple physical name is rendered with, so whether an
    address is the model's is a question about two renderings rather than about two
    strings, and only :meth:`names_table` / :meth:`names_key_column` answer it.
    """

    _table: exp.Identifier
    _key_column: exp.Identifier
    key: Any

    def names_table(self, declared: str) -> bool:
        """Whether this address's target table is the physical *declared* one."""
        return _names(self._table, declared)

    def names_key_column(self, declared: str) -> bool:
        """Whether this address's key column is the physical *declared* one."""
        return _names(self._key_column, declared)


def statement_object(statement: str, binds: list[Any], dialect: str) -> ObjectAddress | None:
    """The object *statement* addresses, read off the statement's own address, or
    ``None`` when it renders no bound key equality for *dialect*.

    Every existing-row write renders one address shape: the DML names the target
    table and the predicate LEADS with the primary-key equality, which the
    table-per-hierarchy tag guard, the temporal bounds, and the optimistic gate
    then follow in that order (`m-sql`, `m-inheritance`, `m-opt-lock`). The key's
    bind is therefore the predicate's first placeholder, and every placeholder
    before it belongs to the `set` clause.
    """
    write = _existing_row_write(statement, dialect)
    key_column = _bound_equality_identifier(write.conjuncts[0]) if write is not None else None
    offset = _predicate_bind_offset(statement)
    if write is None or key_column is None or offset is None or offset >= len(binds):
        return None
    return ObjectAddress(write.table, key_column, binds[offset])


# --- the optimistic gates a write appends to its address -------------------------


def has_version_gate(statement: str, version_col: str, dialect: str) -> bool:
    """True when a versioned write's OUTER predicate gates on the optimistic version.

    The optimistic golden write appends ``and <version> = ?`` to its keyed predicate
    (m-opt-lock). Two other places name the same column and are NOT that gate: an
    ``UPDATE``'s own ``SET`` clause, which carries the framework-derived advance in
    BOTH modes, and any nested ``SELECT``'s own ``WHERE`` — which is why the gate is
    projected out of the parsed statement (:func:`_existing_row_write`) rather than
    scanned for. A statement that is no existing-row write carries no gate.
    """
    write = _existing_row_write(statement, dialect)
    return write is not None and any(_gates_on(operand, version_col) for operand in write.conjuncts)


def has_temporal_gate(statement: str, in_z: str, dialect: str) -> bool:
    """True when a milestone close's SQL carries the OPTIMISTIC gate predicate.

    Address and gate are separate facts (`m-bitemp-write` "Address and gate are
    separate"): every close renders the same address in either mode, and an optimistic
    one APPENDS the observed Transaction-Time start (``and <in_z> = ?``) last. The gate
    signature is therefore that predicate as the predicate's LAST conjunct, so the
    address's own ``<out_z> = ?`` is never mistaken for it and a close that weaves the
    observed start into the address instead of appending it is reported UNGATED and
    fails on arity rather than passing as a well-formed gated close. A close is then
    never mis-read as gated on the strength of a longer bind row alone, nor on a gate
    predicate that binds anywhere but last.

    The temporal peer of :func:`has_version_gate`, and projected out of the same
    parsed statement (:func:`_existing_row_write`) for the same reasons: a reserved
    physical interval column is rendered QUOTED in the executing dialect's own quote
    character (`m-dialect`), and a nested ``SELECT``'s trailing predicate is a conjunct
    of that query rather than of this one.
    """
    write = _existing_row_write(statement, dialect)
    return write is not None and _gates_on(write.conjuncts[-1], in_z)


# --- cross-checking the neutral input against the golden binds -------------------


def assert_write_values(case: Case, expected: list[Any], actual: list[Any], statement: str) -> None:
    if len(expected) != len(actual):
        raise CaseFailure(
            f"{case.path.name}: the neutral write input supplies {len(expected)} write "
            f"value(s) but the golden binds carry {len(actual)} for {statement!r}."
        )
    for want, got in zip(expected, actual, strict=True):
        if not write_value_equal(want, got):
            raise CaseFailure(
                f"{case.path.name}: neutral write input value {want!r} != golden bind "
                f"{got!r} for {statement!r}."
            )


# --- inheritance routing and the tag guard ---------------------------------------


def _primary_key_columns(entity: Entity) -> list[str]:
    """The physical primary-key column(s) of *entity* (its flattened definition)."""
    return [a["column"] for a in entity.attributes if a.get("primaryKey")]


def assert_inheritance_write_routing(
    case: Case,
    entity: Entity,
    step_statements: list[str],
    step_binds: list[list[Any]],
    dialect: str,
) -> None:
    """Assert an inheritance write's golden DML routes and guards correctly.

    A no-op on a non-inheritance entity. For a TABLE-PER-HIERARCHY concrete subtype
    every EXISTING-ROW statement in the step — a plain ``update`` / ``delete`` OR a
    milestone TEMPORAL close / inactivation (m-txtime-write / m-bitemp-write) — MUST
    carry the tag GUARD among the identity predicates, canonically right after the
    primary key (m-inheritance, m-sql); a chained milestone INSERT derives the tag
    COLUMN instead, cross-checked where that statement's own column list is graded.
    For a TABLE-PER-CONCRETE-SUBTYPE concrete subtype
    every write (insert / close / delete) MUST target the subtype's OWN table (no
    shared table, no tag).

    Both facts are read off the golden's PARSE for the executing *dialect*, never off
    its text: the physical table and the guarded columns are rendered quoted where
    they are reserved or otherwise non-simple, and the quote character itself diverges
    per dialect (`m-dialect`).
    """
    discriminator = tag(entity)
    if discriminator is not None:  # table-per-hierarchy concrete subtype
        for statement, binds in zip(step_statements, step_binds, strict=True):
            if is_existing_row_statement(statement):
                _assert_existing_row_tag_guard(case, entity, statement, binds, dialect)
        return
    if entity.role == "concrete-subtype":  # table-per-concrete-subtype (tag is None)
        for statement in step_statements:
            _assert_concrete_table_routing(case, entity, statement, dialect)


def _assert_existing_row_tag_guard(
    case: Case, entity: Entity, statement: str, binds: list[Any], dialect: str
) -> None:
    """A table-per-hierarchy existing-row write carries the tag guard after the PK.

    The tag guard is the ``<tag.column> = ?`` equality joining the identity predicates
    immediately after the primary-key equality (m-inheritance / m-sql; resolved Q9),
    and its ``?`` binds the concrete subtype's ``tagValue`` — framework-derived, so it
    is pinned to the model, never authored. The optimistic version gate, when present,
    still binds LAST (after the tag).

    Both halves are read off the statement's own parse — the guard's shape from the
    predicate's first two conjuncts (:func:`_existing_row_write`), its bind position
    from the scanned placeholder count (:func:`_predicate_bind_offset`) — because a
    literal ``<pk> = ? and <tag> = ?`` fragment finds neither a quoted physical column
    nor a legally reformatted predicate, and a textual ``?`` count includes the ones
    inside string literals and quoted identifiers, which bind nothing.
    """
    tag_column, tag_value = tag(entity)  # type: ignore[misc]
    pk_columns = _primary_key_columns(entity)
    if len(pk_columns) != 1:  # the inheritance families key on a single-column pk (`id`)
        return
    write = _existing_row_write(statement, dialect)
    offset = _predicate_bind_offset(statement)
    guarded = (
        write is not None
        and len(write.conjuncts) > 1
        and _gates_on(write.conjuncts[0], pk_columns[0])
        and _gates_on(write.conjuncts[1], tag_column)
    )
    if not guarded or offset is None:
        raise CaseFailure(
            f"{case.path.name}: a table-per-hierarchy existing-row write of "
            f"{entity.name} MUST carry the tag guard immediately after the primary-key "
            f"equality (`{pk_columns[0]} = ? and {tag_column} = ?`), not found in golden "
            f"{statement!r}."
        )
    # The pk equality opens the predicate and binds one placeholder, so the tag's own
    # bind lands one past it — after the SET placeholders, before any opt-lock gate,
    # in either concurrency mode.
    tag_bind_index = offset + 1
    if tag_bind_index >= len(binds) or not write_value_equal(tag_value, binds[tag_bind_index]):
        actual = binds[tag_bind_index] if tag_bind_index < len(binds) else "<missing>"
        raise CaseFailure(
            f"{case.path.name}: the tag guard binds {actual!r} at position "
            f"{tag_bind_index}, but concrete subtype {entity.name}'s tagValue is "
            f"{tag_value!r} (the tag is framework-derived, never authored)."
        )


def _assert_concrete_table_routing(
    case: Case, entity: Entity, statement: str, dialect: str
) -> None:
    """A table-per-concrete-subtype write targets the subtype's OWN table.

    There is no shared table and no tag column (m-inheritance), so the concrete
    subtype is selected by WHICH table the DML targets: an insert / delete of that
    subtype MUST name its own table. The golden's target is compared to the model by
    the identifier it SPELLS (:func:`_dml_target`, :func:`_names`), so a reserved
    physical table routes correctly under the quoting each dialect renders it with.
    """
    target = _dml_target(statement, dialect)
    if target is None:
        raise CaseFailure(
            f"{case.path.name}: could not read the DML target table from golden {statement!r}."
        )
    if not _names(target, entity.table):
        raise CaseFailure(
            f"{case.path.name}: a table-per-concrete-subtype write of {entity.name} MUST "
            f"target its own table {entity.table!r} (no shared table), but the golden "
            f"targets {target.sql(dialect=sqlglot_dialect(dialect))}: {statement!r}."
        )
