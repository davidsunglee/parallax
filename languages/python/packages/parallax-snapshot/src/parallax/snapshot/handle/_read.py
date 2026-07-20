"""``parallax.snapshot.handle._read`` — the production find executor and the
Snapshot result surface (m-deep-fetch / m-snapshot-read; COR-3 Phase 7
increment 5).

The module DAG's snapshot-handle scope already reaches `materialize` + `m-sql`
+ `m-db-port`, so the deliberate DAG-forbidden edges (`m-deep-fetch`/
`m-snapshot-read` may not import `m-sql`; `m-sql` may not import `m-navigate`/
`m-temporal-read`) are composed HERE, exactly like `_write_lowering` composes
the write-side `m-unit-work` x `m-sql` edge — one executor, production-owned:
`db.find`/`tx.find` and the conformance run lane both call the SAME
:func:`find` / :func:`find_history`, wrap or render the SAME neutral
:class:`~parallax.snapshot.materialize.Node`s, and no engine-local level loop
exists anywhere in this codebase.

The executor's own results (:class:`ExecutedStatement`, :class:`Execution`,
:class:`FindResult`, :class:`MilestoneGraph`, :class:`HistoryFindResult`) stay
co-located with it, together with the developer-facing :class:`Snapshot`
surface they convert into and the pin helpers that carry a statement's or a
milestone's as-of coordinates across that conversion. Those helpers stay here
rather than moving to the write side: `_write_inputs` imports this module, so
the reverse edge would close a cycle.
"""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, cast

from parallax.core import deep_fetch, inheritance, op_algebra
from parallax.core.db_port import DbPort, Row
from parallax.core.descriptor import Entity, Metamodel
from parallax.core.dialect import Dialect, LockMode
from parallax.core.sql_gen import (
    Statement,
    apply_family_variant,
    compile_read,
    family_variant_plan,
    read_narrow_to,
)
from parallax.core.temporal_read import AXIS_ORDER, Edge, Pin, milestone_edge, statement_pin
from parallax.snapshot import materialize
from parallax.snapshot.handle._wrap import wrap_graph

__all__ = [
    "ExecutedStatement",
    "Execution",
    "FindResult",
    "HistoryFindResult",
    "MilestoneGraph",
    "NoResultFound",
    "Snapshot",
    "TooManyResultsFound",
    "find",
    "find_history",
]


@dataclass(frozen=True, slots=True)
class ExecutedStatement:
    """One statement this executor actually ran (or would run — the caller's own
    compile-eligibility posture is not this module's concern). ``duration`` is
    the WALL-CLOCK seconds the port's own ``execute`` call took — informational
    only (spec §3: never graded, never used for control flow)."""

    sql: str
    binds: tuple[object, ...]
    duration: float = 0.0


@dataclass(frozen=True, slots=True)
class Execution:
    """The ordered record of every statement one `find` / `find_history` call
    executed — the production analogue of the conformance adapter's `emissions`
    + `roundTrips`, built once here and consumed by both."""

    statements: tuple[ExecutedStatement, ...]

    @property
    def round_trips(self) -> int:
        return len(self.statements)


class NoResultFound(RuntimeError):
    """``Snapshot.result()`` matched zero roots (spec §2/§3)."""


class TooManyResultsFound(RuntimeError):
    """``Snapshot.result()`` / ``.result_or_none()`` matched more than one root
    (spec §2/§3)."""


class Snapshot[T]:
    """The Python reification of a core Snapshot Graph (spec §3): ``db.find`` /
    ``tx.find``'s result. The complete surface: :meth:`result`,
    :meth:`result_or_none`, :meth:`results` (a FRESH ``list[T]`` per call),
    :attr:`pin` (the lowered as-of coordinates — only genuinely PINNED axes; a
    scanned axis is absent), :attr:`execution` (per-statement ``sql`` /
    ``binds``, informational ``duration``, and ``round_trips``), and
    ``__repr__``. Deliberately ABSENT: iteration / ``len`` / truthiness /
    indexing on the container, refresh or write methods, and any lazy
    behavior — every accessor is a pure in-memory read over roots already
    materialized in full by ``db.find`` / ``tx.find``.
    """

    __slots__ = ("_execution", "_pin", "_roots")

    _roots: tuple[T, ...]
    _pin: Pin
    _execution: Execution

    def __init__(self, roots: tuple[T, ...], pin: Pin, execution: Execution) -> None:
        self._roots = roots
        self._pin = pin
        self._execution = execution

    def result(self) -> T:
        """The single matched root; raises on zero or more than one."""
        count = len(self._roots)
        if count == 0:
            raise NoResultFound("the snapshot matched no roots")
        if count > 1:
            raise TooManyResultsFound(f"the snapshot matched {count} roots, expected exactly 1")
        return self._roots[0]

    def result_or_none(self) -> T | None:
        """The single matched root, or ``None`` on zero; raises on more than one."""
        count = len(self._roots)
        if count == 0:
            return None
        if count > 1:
            raise TooManyResultsFound(f"the snapshot matched {count} roots, expected 0 or 1")
        return self._roots[0]

    def results(self) -> list[T]:
        """Every matched root as an ordinary ``list[T]`` the caller owns (a
        fresh copy per call — this accessor is unaffected by node immutability)."""
        return list(self._roots)

    @property
    def pin(self) -> Pin:
        """The statement's OWN lowered as-of coordinates (spec §3): only
        genuinely pinned axes — a scanned (``history`` / ``as_of_range``) axis
        is absent, per the core rule that a scan is not a pin."""
        return self._pin

    @property
    def execution(self) -> Execution:
        """This find's execution record (per-statement ``sql`` / ``binds``,
        informational ``duration``, and ``round_trips``)."""
        return self._execution

    def __repr__(self) -> str:
        return (
            f"Snapshot(roots={len(self._roots)}, pin={self._pin!r}, "
            f"round_trips={self._execution.round_trips})"
        )


@dataclass(frozen=True, slots=True)
class FindResult:
    """A single-graph find's root nodes plus its execution record.

    ``all_nodes`` is EVERY node this find materialized — root and every
    attached deep-fetch level — paired with its OWN target entity name (the
    same name a subsequent keyed write on that row would carry, `m-unit-work`
    `KeyedWrite.entity`): the seam :meth:`Transaction.find` walks to record a
    versioned row's observed version (`m-opt-lock`), since ``Node`` itself
    carries no entity identity of its own (m-snapshot-read: a neutral,
    class-free field dict).
    """

    nodes: tuple[materialize.Node, ...]
    execution: Execution
    all_nodes: tuple[tuple[str, materialize.Node], ...] = ()


@dataclass(frozen=True, slots=True)
class MilestoneGraph:
    """One `history` / `asOfRange` milestone's own edge-pinned graph (m-snapshot-
    read "The whole-graph pin"): ``pin`` maps each declared as-of attribute name
    to its edge (from-instant) coordinate for this milestone; ``nodes`` is the
    root-only graph at that milestone (a v1 milestone-set graph carries no
    includes, m-case-format)."""

    pin: Mapping[str, object]
    nodes: tuple[materialize.Node, ...]


@dataclass(frozen=True, slots=True)
class HistoryFindResult:
    """A milestone-set find's ordered per-milestone graphs plus its (single-
    statement) execution record."""

    graphs: tuple[MilestoneGraph, ...]
    execution: Execution


def find(
    op: op_algebra.Operation,
    meta: Metamodel,
    dialect: Dialect,
    target: str,
    port: DbPort,
    *,
    lock: LockMode | None = None,
) -> FindResult:
    """The one per-level deep-fetch / snapshot-materialization loop (m-deep-fetch
    "one query per non-empty relationship level"; m-snapshot-read "round trips").

    ``op`` is the read's raw operation: a `DeepFetch` node, or any other read
    operation planned with zero levels (root-only instance-form materialization
    — a plain snapshot read, or the source find behind a scenario `mutate`
    action). Canonicalizes the root query (`m-temporal-read` + `m-navigate`,
    composed here — the M2 precedent), compiles and executes it, then for each
    planned level: gathers the distinct non-null parent keys; an empty gathered
    set attaches the empty/null relationship result and issues no child SQL; a
    back-reference level issues no SQL either (resolved via the assembler's own
    graph-local identity map); otherwise compiles and executes ONE child query
    (declared relationship ordering rendered through the dialect's NULLs-last
    rule), applies `familyVariant` materialization (`m-sql`) to its rows, and
    feeds the assembler. The root's own authored narrow (if any,
    `~parallax.core.sql_gen.read_narrow_to`) threads into
    `Assembler.materialize_root` the SAME way a deep-fetch child level's own
    `FetchLevel.narrow_to` already threads through `attach_level` (S3, COR-3
    Phase 7 increment 7 round-2): a table-per-concrete-subtype root position
    resolving to exactly one concrete emits no `familyVariant` column, so this
    is what lets the assembler still recover the row's own concrete identity.
    Returns the root's own materialized nodes — reached from them, every
    attached level's nodes hang off `Node.fields` — plus the full ordered
    execution record.
    """
    plan_ = deep_fetch.plan(target, op, meta)
    statements: list[ExecutedStatement] = []

    root_statement = compile_read(
        plan_.root_operation, meta, dialect, target, result_form="instance", lock=lock
    )
    root_rows = _execute(port, dialect, root_statement, statements)
    root_plan = family_variant_plan(meta, target, plan_.root_operation)
    root_rows = [apply_family_variant(row, root_plan) for row in root_rows]

    assembler = materialize.Assembler(meta=meta)
    root_nodes = assembler.materialize_root(
        target, root_rows, narrow_to=read_narrow_to(plan_.root_operation)
    )
    all_nodes: list[tuple[str, materialize.Node]] = [(target, node) for node in root_nodes]

    level_rows: list[Sequence[Row]] = []
    level_nodes: list[list[materialize.Node]] = []
    for level in plan_.levels:
        parent_rows, parent_nodes = _parent_data(
            level.parent, root_rows, root_nodes, level_rows, level_nodes
        )
        if level.is_back_reference:
            nodes = assembler.attach_level(level, parent_nodes, parent_rows, None)
            level_rows.append(())
            level_nodes.append(nodes)
            continue
        keys = _distinct_keys(parent_rows, level.parent_column)
        if not keys:
            nodes = assembler.attach_level(level, parent_nodes, parent_rows, None)
            level_rows.append(())
            level_nodes.append(nodes)
            continue
        child_target, child_op = level.child_operation(keys)
        child_statement = compile_read(
            child_op,
            meta,
            dialect,
            child_target,
            result_form="instance",
            lock=lock,
            relationship_order=True,
        )
        rows = _execute(port, dialect, child_statement, statements)
        variant_plan = family_variant_plan(meta, child_target, child_op)
        rows = [apply_family_variant(row, variant_plan) for row in rows]
        nodes = assembler.attach_level(level, parent_nodes, parent_rows, rows)
        level_rows.append(rows)
        level_nodes.append(nodes)
        all_nodes.extend((child_target, node) for node in nodes)

    return FindResult(
        nodes=tuple(root_nodes), execution=Execution(tuple(statements)), all_nodes=tuple(all_nodes)
    )


def find_history(
    op: op_algebra.Operation, meta: Metamodel, dialect: Dialect, target: str, port: DbPort
) -> HistoryFindResult:
    """The milestone-set snapshot read (m-snapshot-read "The whole-graph pin";
    m-case-format "Milestone-set graphs"): `history` / `asOfRange` return the
    full matching milestone SET in one statement, partitioned here by each
    row's own edge (`~parallax.core.temporal_read.milestone_edge`) into one
    root-only graph per milestone — no levels (a v1 milestone-set graph carries
    no includes). Rows are grouped in chronological edge order (business axis
    first, matching the corpus's own authored `then.graphs` order) rather than
    relying on the database's unspecified natural row order.
    """
    plan_ = deep_fetch.plan(target, op, meta)
    if plan_.levels:
        # m-case-format: a v1 milestone-set read carries no includes.
        raise ValueError("a milestone-set (history / asOfRange) read carries no deep-fetch levels")
    # `inheritance.declaring_entity` resolves the entity whose `as_of_attributes`
    # are this target's FAMILY's actual temporal declaration (the root, for a
    # participant — temporality is family-wide, `m-inheritance`); every
    # `~parallax.core.temporal_read` per-entity primitive below (`milestone_edge`,
    # `_edge_pin`, `_edge_sort_key`) MUST resolve through it rather than the
    # queried target's own (possibly locally-empty) `as_of_attributes`.
    entity = inheritance.declaring_entity(meta, meta.entity(target))
    statement = compile_read(plan_.root_operation, meta, dialect, target, result_form="instance")
    statements: list[ExecutedStatement] = []
    rows = _execute(port, dialect, statement, statements)

    order: list[Edge] = []
    groups: dict[Edge, list[Row]] = {}
    for row in sorted(rows, key=lambda row: _edge_sort_key(entity, row)):
        edge = milestone_edge(entity, row)
        if edge not in groups:
            groups[edge] = []
            order.append(edge)
        groups[edge].append(row)

    graphs = tuple(
        MilestoneGraph(
            pin=_edge_pin(entity, edge),
            nodes=tuple(materialize.Assembler(meta=meta).materialize_root(target, groups[edge])),
        )
        for edge in order
    )
    return HistoryFindResult(graphs=graphs, execution=Execution(tuple(statements)))


def _execute(
    port: DbPort, dialect: Dialect, statement: Statement, statements: list[ExecutedStatement]
) -> list[Row]:
    started = time.perf_counter()
    rows = port.execute(dialect.to_driver_sql(statement.sql), list(statement.binds))
    statements.append(
        ExecutedStatement(statement.sql, statement.binds, time.perf_counter() - started)
    )
    return rows


def _parent_data(
    parent: deep_fetch.ParentRef,
    root_rows: Sequence[Row],
    root_nodes: Sequence[materialize.Node],
    level_rows: Sequence[Sequence[Row]],
    level_nodes: Sequence[list[materialize.Node]],
) -> tuple[Sequence[Row], Sequence[materialize.Node]]:
    if isinstance(parent, deep_fetch.RootRef):
        return root_rows, root_nodes
    return level_rows[parent.index], level_nodes[parent.index]


def _distinct_keys(rows: Sequence[Row], column: str) -> list[op_algebra.Scalar]:
    """The distinct NON-NULL values of ``column`` across ``rows``, in first-
    encountered order (m-deep-fetch: the gathered set is unordered for grading
    purposes — an implementation MUST NOT sort at runtime to match a fixture —
    so encounter order is as good as any, and deterministic run to run).

    A gathered key is always a declared PRIMARY-KEY (or unique FK) attribute's
    own value — one of `m-op-algebra`'s neutral scalar types — even though the
    port's own row values are typed as plain ``object`` (`m-db-port`); the cast
    reflects that runtime invariant, not a widening of the membership node's
    own typed-literal contract.
    """
    values = dict.fromkeys(row[column] for row in rows if row[column] is not None)
    return cast("list[op_algebra.Scalar]", list(values))


def _edge_sort_key(entity: Entity, row: Row) -> tuple[object, ...]:
    """Business axis first, then processing (m-sql's own bind-order convention),
    each axis's own from-column value — used only to chronologically order a
    milestone-set read's grouped graphs, never to select or filter rows."""
    ordered = sorted(entity.as_of_attributes, key=lambda aoa: AXIS_ORDER[aoa.axis])
    return tuple(row[aoa.from_column] for aoa in ordered)


def _edge_pin(entity: Entity, edge: Edge) -> dict[str, object]:
    """The milestone-set `then.graphs` `pin` entry: each declared as-of attribute
    name mapped to its edge (from-instant) coordinate on that axis."""
    return {
        aoa.name: (edge.business if aoa.axis == "business" else edge.processing)
        for aoa in entity.as_of_attributes
    }


def deep_fetch_statement_pin(op: op_algebra.Operation, entity: Entity) -> Pin:
    """``snapshot.pin`` for ``op`` (spec §3): identical to
    ``~parallax.core.temporal_read.statement_pin``, except that an outer
    ``DeepFetch`` directive (``.include(...)`` composed after ``.as_of(...)``)
    is peeled first. ``m-temporal-read`` never imports ``m-deep-fetch`` (the
    DAG forbids the reverse dependency direction), so `statement_pin`'s own
    directive-peeling (`Limit`/`OrderBy`/`Distinct` only) cannot see a
    `DeepFetch` wrapper — this composition, mirroring the M2 precedent, is the
    handle's own job. A milestone-set read (`.history()`/`.as_of_range()`)
    never carries an outer `DeepFetch` (`Statement.include`/`.history`/
    `.as_of_range` mutually refuse the combination, spec §3
    ``snapshot-history-includes``), so this peel is unconditionally safe.
    """
    pin_op = op.operand if isinstance(op, op_algebra.DeepFetch) else op
    return statement_pin(pin_op, entity)


def is_milestone_set_op(op: op_algebra.Operation) -> bool:
    """Whether ``op``'s temporal wrapper SCANS an axis (``history`` /
    ``as_of_range``) rather than pinning it — the milestone-set find shape
    (spec §3 "one root per milestone")."""
    current: op_algebra.Operation = op
    while isinstance(current, (op_algebra.Limit, op_algebra.OrderBy, op_algebra.Distinct)):
        current = current.operand
    return isinstance(current, (op_algebra.AsOfRange, op_algebra.History))


def _pin_from_milestone(entity: Entity, milestone_pin: Mapping[str, object]) -> Pin:
    """One milestone's own edge, rendered as a :class:`Pin` (spec §3: each
    milestone-set root is edge-pinned at its own milestone's from-instant)."""
    coords: dict[str, object] = {}
    for aoa in entity.as_of_attributes:
        if aoa.name in milestone_pin:
            coords[aoa.axis] = milestone_pin[aoa.name]
    return Pin(
        processing=cast("Any", coords.get("processing")),
        business=cast("Any", coords.get("business")),
    )


def snapshot_from_find_result(
    result: FindResult, target: str, meta: Metamodel, pin: Pin
) -> Snapshot[Any]:
    roots = wrap_graph(result.nodes, target, meta, pin)
    return Snapshot(roots, pin, result.execution)


def snapshot_from_history_result(
    result: HistoryFindResult, target: str, meta: Metamodel
) -> Snapshot[Any]:
    entity = inheritance.declaring_entity(meta, meta.entity(target))
    roots: list[Any] = []
    for graph in result.graphs:
        milestone_pin = _pin_from_milestone(entity, graph.pin)
        roots.extend(wrap_graph(graph.nodes, target, meta, milestone_pin))
    return Snapshot(tuple(roots), Pin(), result.execution)
