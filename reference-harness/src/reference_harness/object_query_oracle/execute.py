"""Running an accepted read's statements, and reading the shape of the SQL it ran.

Three things belong together here because they are all about the golden statement
itself rather than about what its rows mean:

* **Execution.** The golden statement and the independent ``referenceSql`` oracle
  both run through the executor the caller supplied — the same one, so a read
  through a held session compares against state that session can see.
* **Statement shape.** An abstract read's projection, a ``union all``'s branches,
  and a Relational Document Layout's presence cell are all read off the golden
  text, so a zero-row read still witnesses a dropped column or a mis-lowered
  partition.
* **Temporal Selection.** A read's ``temporal`` clause decides which binds its
  statements must carry, so the derivation sits beside the execution it constrains
  rather than in a module of its own.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import sqlglot
from sqlglot import exp

from .._statement_bind_inference import managed_statement_binds
from ..case import Case, Entity, Model
from ..case_assertions import CaseFailure, scalars_equal
from ..sql_canonical import sqlglot_dialect
from ..sql_normalize import detach_read_lock, is_union_all
from ..storage_layout import ColumnTier
from .executor import ReadExecutor

# --- statement shape --------------------------------------------------------


def projection_expr(projection: Any) -> Any:
    """The underlying expression of a (possibly aliased) projection."""
    return projection.this if isinstance(projection, exp.Alias) else projection


def string_literal_value(projection: Any) -> str | None:
    """The string value of a (possibly aliased) string-literal projection, else None."""
    node = projection_expr(projection)
    if isinstance(node, exp.Literal) and node.is_string:
        return node.this
    return None


def union_branch_selects(tree: Any) -> list[Any]:
    """The leaf SELECT branches of a (possibly nested) `union all`, in order.

    A plain SELECT is a single branch; a `SetOperation` yields its arms left to
    right (``A union all B union all C`` nests left, so the walk restores authored
    branch order). Callers assert `union all`-only separately
    (:func:`assert_union_all_only`).
    """
    if isinstance(tree, exp.Select):
        return [tree]
    if isinstance(tree, exp.SetOperation):
        return union_branch_selects(tree.this) + union_branch_selects(tree.expression)
    return []


def _select_branches(tree: Any) -> list[Any]:
    """Every SELECT a statement projects through: a union's arms, else the one SELECT."""
    branches = union_branch_selects(tree)
    if branches:
        return branches
    select = tree if isinstance(tree, exp.Select) else tree.find(exp.Select)
    return [] if select is None else [select]


def assert_union_all_only(case: Case, tree: Any) -> None:
    """Reject any set operation in *tree* that is not a canonical `union all` (m-sql).

    The abstract-read lowering is `union all` — a plain `union` silently
    de-duplicates rows (changing the read's semantics) and `intersect` / `except` are
    never emitted. sqlglot parses all of these into `exp.SetOperation`, so a branch
    walk would happily accept them; this guard makes the oracle reject a golden that
    used the wrong set operation, mirroring the normalizer's canonicality gate.
    """
    for setop in tree.find_all(exp.SetOperation):
        if not is_union_all(setop):
            raise CaseFailure(
                f"{case.path.name}: table-per-concrete-subtype abstract read uses set "
                f"operation {setop.key!r}, not `union all`; only `union all` is a "
                f"canonical TPCS lowering (a plain `union` de-duplicates rows; m-sql)."
            )


def _identifier_identity(name: str, dialect: str, *, quoted: bool) -> str:
    """Database identity used when allocating unquoted execution aliases."""
    if quoted:
        return name
    if dialect in {"postgres", "mariadb"}:
        return name.casefold()
    return name


def _projection_identity(projection: Any, dialect: str) -> str | None:
    """The database identity of a projection's output name, or ``None`` if it has none."""
    output = projection.args.get("alias") if isinstance(projection, exp.Alias) else None
    if not isinstance(output, exp.Identifier) and isinstance(projection, exp.Column):
        output = projection.this
    if isinstance(output, exp.Identifier):
        return _identifier_identity(output.name, dialect, quoted=bool(output.args.get("quoted")))
    return (
        _identifier_identity(projection.output_name, dialect, quoted=False)
        if projection.output_name
        else None
    )


def _source_relations(select: Any) -> dict[str, Any]:
    """Immediate FROM/JOIN relations in ``select``, keyed by their visible alias."""
    from_clause = select.args.get("from_")
    relations = ([] if from_clause is None else [from_clause.this, *from_clause.expressions]) + [
        join.this for join in select.args.get("joins") or ()
    ]
    return {
        relation.alias_or_name: relation
        for relation in relations
        if isinstance(relation, (exp.Table, exp.Subquery)) and relation.alias_or_name
    }


def _column_identity(column: Any, dialect: str) -> str:
    identifier = column.this
    return _identifier_identity(
        column.name,
        dialect,
        quoted=isinstance(identifier, exp.Identifier) and bool(identifier.args.get("quoted")),
    )


def _passthrough_projection(select: Any, column: Any, dialect: str) -> tuple[int, Any] | None:
    identity = _column_identity(column, dialect)
    matches = [
        (ordinal, projection)
        for ordinal, projection in enumerate(select.expressions)
        if _projection_identity(projection, dialect) == identity
    ]
    if len(matches) == 1:
        ordinal, projection = matches[0]
        candidate = projection_expr(projection)
        if isinstance(candidate, exp.Column) and not candidate.is_star:
            return ordinal, candidate
    return None


def _passthrough_column(select: Any, column: Any, dialect: str) -> Any | None:
    if (matched := _passthrough_projection(select, column, dialect)) is not None:
        return matched[1]
    stars = [
        projection
        for projection in select.expressions
        if isinstance(projection, exp.Star)
        or isinstance(projection, exp.Column)
        and projection.is_star
    ]
    if len(stars) != 1:
        return None
    relations = _source_relations(select)
    star = stars[0]
    qualifier = star.table if isinstance(star, exp.Column) else ""
    identifier = column.this
    quoted = isinstance(identifier, exp.Identifier) and bool(identifier.args.get("quoted"))
    if qualifier:
        return exp.column(column.name, table=qualifier, quoted=quoted)
    if len(relations) == 1:
        return exp.column(column.name, table=next(iter(relations)), quoted=quoted)
    return None


def _ordinal_passthrough_column(select: Any, ordinal: int) -> Any | None:
    if ordinal >= len(select.expressions):
        return None
    projection = select.expressions[ordinal]
    candidate = projection_expr(projection)
    return candidate if isinstance(candidate, exp.Column) and not candidate.is_star else None


def _physical_column_sources(
    select: Any, column: Any, dialect: str
) -> tuple[tuple[str, str], ...] | None:
    """Trace one selected Column through aliases to every physical Table and Column it
    can come from, or ``None`` where any branch of the trace stops.

    A derived table over a `union all` contributes one source PER BRANCH, and a
    table-per-concrete-subtype union's branches read DIFFERENT Tables by construction
    (m-inheritance) — so a wrapped such read is traceable only if the answer is the
    whole set. A caller asking a per-source question asks it of every member.
    """
    relations = _source_relations(select)
    relation = relations.get(column.table)
    if relation is None and not column.table and len(relations) == 1:
        relation = next(iter(relations.values()))
    if isinstance(relation, exp.Table):
        return ((relation.name, column.name),)
    if not isinstance(relation, exp.Subquery):
        return None
    branches = _select_branches(relation.this)
    if isinstance(relation.this, exp.SetOperation):
        if not branches:
            return None
        matched = _passthrough_projection(branches[0], column, dialect)
        if matched is None:
            return None
        ordinal = matched[0]
        passthroughs = [_ordinal_passthrough_column(branch, ordinal) for branch in branches]
    else:
        passthroughs = [_passthrough_column(branch, column, dialect) for branch in branches]
    sources: list[tuple[str, str]] = []
    for branch, passthrough in zip(branches, passthroughs, strict=True):
        if passthrough is None:
            return None
        traced = _physical_column_sources(branch, passthrough, dialect)
        if traced is None:
            return None
        sources.extend(traced)
    return tuple(dict.fromkeys(sources))


def _document_presence_projection(projection: Any) -> bool:
    """Whether an expression has the physical document-presence syntax."""
    return (
        isinstance(projection, exp.Not)
        and isinstance(projection.this, exp.Is)
        and isinstance(projection.this.this, exp.Column)
        and isinstance(projection.this.expression, exp.Null)
    )


def _same_projected_document(
    presence: Any,
    document: Any,
    select: Any,
    document_columns: Mapping[str, frozenset[str]],
    dialect: str,
) -> bool:
    if not _document_presence_projection(presence):
        return False
    candidate = projection_expr(document)
    if not isinstance(candidate, exp.Column):
        return False
    source = presence.this.this
    if source.name != candidate.name or source.table != candidate.table:
        return False
    physical = _physical_column_sources(select, source, dialect)
    return bool(physical) and all(
        column in document_columns.get(table, frozenset()) for table, column in physical
    )


def _false_presence_padding(projection: Any) -> bool:
    return isinstance(projection, exp.Boolean) and projection.this is False


def document_presence_ordinals(selects: list[Any], model: Model, dialect: str) -> tuple[int, ...]:
    """Presence ordinals proved by layout metadata and adjacency across branches."""
    if not selects:
        return ()
    width = len(selects[0].expressions)
    if any(len(select.expressions) != width for select in selects):
        return ()
    document_columns = {
        table.table: frozenset(
            slot.column for slot in table.columns if slot.tier is ColumnTier.DOCUMENT
        )
        for table in model.storage_layout.tables
    }
    ordinals: list[int] = []
    for ordinal in range(width - 1):
        arms = [select.expressions[ordinal] for select in selects]
        next_arms = [select.expressions[ordinal + 1] for select in selects]
        structural = [
            _same_projected_document(arm, next_arm, select, document_columns, dialect)
            for arm, next_arm, select in zip(arms, next_arms, selects, strict=True)
        ]
        if any(structural) and all(
            proved or _false_presence_padding(arm)
            for proved, arm in zip(structural, arms, strict=True)
        ):
            ordinals.append(ordinal)
    return tuple(ordinals)


def golden_projection_columns(case: Case) -> set[str]:
    """The OUTPUT column names the case's (single) golden SELECT projects.

    Parses the golden ``select`` with sqlglot and returns each projection's output
    name — a plain ``t0.col`` projects ``col`` (the table alias is dropped), matching
    the DB result-key semantics. This reads the projection SHAPE from the SQL text,
    not a sample row, so the abstract-read projection check that consumes it is
    row-count-INDEPENDENT (a zero-row read still witnesses a dropped column).

    Postgres is parsed when present (the abstract-read goldens author it), else the
    first declared golden dialect. A ``*`` or a function-wrapped / literal projection
    contributes no static column name, so it is skipped: canonical m-sql golden SQL
    always projects explicit, qualified columns, so this only trims degenerate shapes.
    """
    dialects = case.golden_dialects
    dialect = "postgres" if "postgres" in dialects else next(iter(dialects), None)
    if dialect is None:
        return set()
    statements = case.golden_statements(dialect)
    if not statements:
        return set()
    tree = sqlglot.parse_one(statements[0], read=sqlglot_dialect(dialect))
    branches = _select_branches(tree)
    if not branches:
        return set()
    select = branches[0]
    presence_ordinals = set(document_presence_ordinals(branches, case.model, dialect))
    return {
        name
        for ordinal, projection in enumerate(select.expressions)
        if ordinal not in presence_ordinals
        if (name := projection.output_name) and name != "*"
    }


# --- execution --------------------------------------------------------------


def _alias_document_presence_projections(
    sql: str, dialect: str, model: Model
) -> tuple[str, frozenset[str]]:
    """Give only proven physical presence cells collision-safe execution aliases."""
    tree = sqlglot.parse_one(sql, read=sqlglot_dialect(dialect))
    selects = _select_branches(tree)
    ordinals = document_presence_ordinals(selects, model, dialect)
    reserved = {
        identity
        for select in selects
        for projection in select.expressions
        if (identity := _projection_identity(projection, dialect)) is not None
    }
    aliases: dict[int, str] = {}
    for ordinal in ordinals:
        base = f"__parallax_document_presence_{ordinal}"
        alias = base
        suffix = 1
        while _identifier_identity(alias, dialect, quoted=False) in reserved:
            alias = f"{base}_{suffix}"
            suffix += 1
        aliases[ordinal] = alias
        reserved.add(_identifier_identity(alias, dialect, quoted=False))
    keys = frozenset(aliases.values())
    for select in selects:
        projections = list(select.expressions)
        for ordinal in ordinals:
            projections[ordinal] = exp.alias_(projections[ordinal], aliases[ordinal])
        select.set("expressions", projections)
    if not ordinals:
        return sql, keys
    lock_suffix = detach_read_lock(tree, dialect)
    return tree.sql(dialect=sqlglot_dialect(dialect)) + lock_suffix, keys


def query_rows(
    case: Case, reader: ReadExecutor, sql: str, binds: Sequence[Any]
) -> list[dict[str, Any]]:
    """Run one golden statement and return its rows.

    Two anonymous adjacent projections over the same Structured Column would
    collide in the result mapping, so a proven physical document-presence cell is
    given a collision-safe execution alias before the statement runs and the alias
    is stripped back out of every row afterwards. The read observes exactly the
    columns the golden projects.
    """
    executable, presence_keys = _alias_document_presence_projections(
        sql, reader.dialect, case.model
    )
    rows = (
        reader.query(
            executable,
            managed_statement_binds(case, executable, binds, reader.dialect),
        )
        if binds
        else reader.query(executable)
    )
    if not presence_keys:
        return rows
    return [{key: value for key, value in row.items() if key not in presence_keys} for row in rows]


def reference_rows(reader: ReadExecutor, sql: str) -> list[dict[str, Any]]:
    """Run the independent ``then.referenceSql`` oracle verbatim.

    On the SAME executor as the golden read it grades, never a fresh connection:
    a read taken through a held session must compare against the state that
    session sees, or an uncommitted write in the group would leave the two
    observations answering different questions. Nothing is aliased — the naive
    oracle is executed exactly as authored.
    """
    return reader.query(sql)


def project_like(row: dict[str, Any], template_rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Keep only the columns the golden root projection carries.

    An independent oracle states its own naive SELECT, so it may project more than
    the golden read's roots do; what it is graded on is the root set the golden
    published, not the columns a second formulation chose to carry.
    """
    if not template_rows:
        return row
    keep = set(template_rows[0])
    return {key: value for key, value in row.items() if key in keep}


# --- Temporal Selection -----------------------------------------------------

# Canonical as-of dimension order: Valid Time precedes Transaction Time in both the
# golden SQL clause order and the bind order (m-bitemp-write bitemporal table;
# case m-temporal-read-015).
_CANONICAL_AXIS_ORDER: tuple[str, ...] = ("valid-time", "transaction-time")


@dataclass(frozen=True, slots=True)
class _AsOfSelection:
    coordinate: str


@dataclass(frozen=True, slots=True)
class _AsOfRangeSelection:
    start: str
    end: str


@dataclass(frozen=True, slots=True)
class _HistorySelection:
    pass


_TemporalSelection = _AsOfSelection | _AsOfRangeSelection | _HistorySelection


def query_temporal_selections(query: Any) -> dict[str, _TemporalSelection]:
    """One Object Query's Temporal Selection clause, keyed by dimension."""
    temporal = query.get("temporal") if isinstance(query, dict) else None
    if not isinstance(temporal, dict):
        return {}
    selections: dict[str, _TemporalSelection] = {}
    for dimension, selection in temporal.items():
        if not isinstance(selection, dict) or len(selection) != 1:
            continue
        tag = next(iter(selection))
        body = selection[tag]
        if tag == "asOf" and isinstance(body, str):
            selections[dimension] = _AsOfSelection(body)
        elif tag == "asOfRange" and isinstance(body, dict):
            start = body.get("start")
            end = body.get("end")
            if isinstance(start, str) and isinstance(end, str):
                selections[dimension] = _AsOfRangeSelection(start, end)
        elif tag == "history":
            selections[dimension] = _HistorySelection()
    return selections


def scans_an_axis(query: dict[str, Any]) -> bool:
    """Whether *query* is a milestone-set read — one root per milestone."""
    return any(
        isinstance(selection, _HistorySelection | _AsOfRangeSelection)
        for selection in query_temporal_selections(query).values()
    )


def root_asof_pins(query: dict[str, Any]) -> dict[str, str]:
    """Map ``{dimension: coordinate}`` from the read's own ``asOf`` selections.

    A dimension absent here defaults to the child's own ``latest`` value at
    propagation time, and a SCANNED dimension (``history`` / ``asOfRange``) pins
    nothing: it selects a milestone set rather than a coordinate. Empty when the
    root is unpinned.
    """
    return {
        dimension: selection.coordinate
        for dimension, selection in query_temporal_selections(query).items()
        if isinstance(selection, _AsOfSelection)
    }


def expected_pin_suffix(child_entity: Entity, pins: Mapping[str, str]) -> list[Any]:
    """The as-of binds a temporal child level MUST carry, after its IN-list.

    Per dimension, in canonical order (Valid Time, then Transaction Time): the
    propagated value is the root pin for that dimension, or the child's own
    ``default`` (``latest``) when the root did not pin it. ``latest`` lowers to the
    single equality bind (the axis's ``infinity``); a finite instant lowers to the
    half-open range's two binds ``[D, D]``. A non-temporal child yields ``[]``.
    """
    by_axis = {axis["dimension"]: axis for axis in child_entity.temporal_runtime_axes}
    suffix: list[Any] = []
    for dimension in _CANONICAL_AXIS_ORDER:
        axis = by_axis.get(dimension)
        if axis is None:
            continue
        coordinate = pins.get(dimension, axis.get("default", "latest"))
        if coordinate == "latest":
            suffix.append(axis["infinity"])
        else:
            suffix.extend([coordinate, coordinate])
    return suffix


def expected_temporal_suffix(
    case: Case, entity: Entity, selections: Mapping[str, _TemporalSelection]
) -> list[Any]:
    """The binds *entity*'s selected temporal predicates contribute, in axis order.

    Per As-Of Axis in canonical order (Valid Time, then Transaction Time): an
    ``asOf latest`` lowers to the single equality bind (the axis's ``infinity``), a
    finite instant to the half-open range's two binds ``[D, D]``, and an
    ``asOfRange`` to ``[end, start]``. ``history`` contributes none.
    """
    by_axis = {axis["dimension"]: axis for axis in entity.temporal_runtime_axes}
    suffix: list[Any] = []
    for dimension in _CANONICAL_AXIS_ORDER:
        axis = by_axis.get(dimension)
        if axis is None:
            continue
        selection = selections.get(dimension)
        if selection is None:
            raise CaseFailure(
                f"{case.path.name}: temporal selection oracle is missing {dimension!r} "
                f"for {entity.canonical_name}"
            )
        if isinstance(selection, _AsOfSelection):
            if selection.coordinate == "latest":
                suffix.append(axis["infinity"])
            else:
                suffix.extend([selection.coordinate, selection.coordinate])
        elif isinstance(selection, _AsOfRangeSelection):
            suffix.extend([selection.end, selection.start])
    return suffix


# --- bind comparison --------------------------------------------------------


def _bytes_to_hex(value: Any) -> Any:
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).hex()
    return value


def bind_value_equal(left: Any, right: Any) -> bool:
    """Scalar equality for a derived bind vs an authored golden bind.

    A date / timestamp the corpus YAML resolved into a ``date`` / ``datetime``
    object must still match the same instant authored as text, so the two are
    compared by ISO string form once the exact-Decimal comparison declines. A
    ``bytes`` bind is normalized to lowercase hex first, so its wire form and its
    raw form name the same value.
    """
    left = _bytes_to_hex(left)
    right = _bytes_to_hex(right)
    if scalars_equal(left, right, None):
        return True
    return str(left) == str(right)
