"""``parallax.snapshot.handle._read`` — the production find executor and the
Snapshot result surface (m-deep-fetch / m-snapshot-read).

The module DAG's snapshot-handle scope already reaches `materialize` + `m-sql`
+ `m-db-port`, so the deliberate DAG-forbidden edges (`m-deep-fetch`/
`m-snapshot-read` may not import `m-sql`; `m-sql` may not import `m-navigate`/
`m-temporal-read`) are composed HERE, exactly like `_write_lowering` composes
the write-side `m-unit-work` x `m-sql` edge — one executor, production-owned:
`db.find` and `tx.find` both call the SAME :func:`find` / :func:`find_history`
and wrap the SAME neutral :class:`~parallax.snapshot.materialize.Node`s, so the
per-level loop exists exactly once on the developer-facing path.

The executor's own results (:class:`ExecutedStatement`, :class:`Execution`,
:class:`FindResult`, :class:`MilestoneGraph`, :class:`HistoryFindResult`) stay
co-located with it, together with the developer-facing :class:`Snapshot`
surface they convert into and the pin helpers that carry a query's or a
milestone's as-of coordinates across that conversion. Those helpers stay here
rather than moving to the write side: `_write_inputs` imports this module, so
the reverse edge would close a cycle.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, cast

from parallax.core import deep_fetch, inheritance, op_algebra
from parallax.core.db_port import DbPort, Row
from parallax.core.dialect import Dialect, LockMode
from parallax.core.entity import EntityGraphConstruction
from parallax.core.metamodel import AsOfAxisMetadata as AcceptedAsOfAxis
from parallax.core.metamodel import (
    EntityIdentity,
    EntityMetadata,
    Metamodel,
    TemporalDimension,
    entity_by_name,
)
from parallax.core.sql_gen import CompiledRead, MaterializedReadRow, Statement, compile_read
from parallax.core.temporal_read import Edge, Pin, milestone_edge, statement_pin
from parallax.snapshot import materialize
from parallax.snapshot.handle._errors import SnapshotMaterializationError
from parallax.snapshot.handle._wrap import wrap_graph

__all__ = [
    "ExecutedStatement",
    "Execution",
    "FindResult",
    "HistoryFindResult",
    "MilestoneGraph",
    "NoResultFound",
    "ObservedNode",
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
        """The query's OWN lowered as-of coordinates (spec §3): only
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
class ObservedNode:
    """One materialized node with everything a write-side observation needs of it.

    ``entity`` is the node's OWN target entity name (the same name a subsequent
    keyed write on that row would carry, `m-unit-work` `KeyedWrite.entity`),
    because ``Node`` carries no entity identity of its own (m-snapshot-read: a
    neutral, class-free field dict). ``document`` is the raw Structured Column the
    row arrived with under Relational Document Layout — provenance the fan-out
    drops from the node's fields, retained here so a Temporal Observation keeps it
    without a second read (`m-unit-work`) and absent under `Columns` layout.
    """

    entity: str
    node: materialize.Node
    document: object | None = None


@dataclass(frozen=True, slots=True)
class FindResult:
    """A single-graph find's root nodes plus its execution record.

    ``all_nodes`` is EVERY node this find materialized — root and every
    attached deep-fetch level: the seam :meth:`Transaction.find` walks to record a
    versioned row's observed version (`m-opt-lock`) and a temporal row's whole
    predecessor milestone (`m-unit-work`).
    """

    nodes: tuple[materialize.Node, ...]
    execution: Execution
    all_nodes: tuple[ObservedNode, ...] = ()


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
    composed here), compiles and executes it, then for each
    planned level: restricts the parent rows to the ones a path-root guard admits
    (`FetchLevel.source_position`, m-deep-fetch — an excluded parent contributes no
    key and receives no attachment, so its view stays unset); gathers the distinct
    non-null parent keys; an empty gathered
    set attaches the empty/null relationship result and issues no child SQL; a
    back-reference level issues no SQL either (resolved via the assembler's own
    graph-local identity map); otherwise compiles and executes ONE child query
    (carrying the level's declared relationship ordering), applies
    `familyVariant` materialization (`m-sql`) to its rows, and
    feeds the assembler. Every level is the same three steps — compile,
    execute, transform — with `familyVariant` materialization coming from that
    level's OWN `~parallax.core.sql_gen.CompiledRead.transform_row`, never
    re-derived here from the operation a second time. The root's own authored
    narrow (if any, `~parallax.core.sql_gen.CompiledRead.narrow_to`) threads
    into `Assembler.materialize_root` the SAME way a deep-fetch child level's own
    `FetchLevel.narrow_to` already threads through `attach_level`: a
    table-per-concrete-subtype root position
    resolving to exactly one concrete emits no `familyVariant` column, so this
    is what lets the assembler still recover the row's own concrete identity.
    Returns the root's own materialized nodes — reached from them, every
    attached level's nodes hang off `Node.relationships` — plus the full ordered
    execution record.
    """
    # ``meta`` is the accepted model the connected ``Database`` already holds, so
    # every level's own Entity resolves against it directly.
    root_entity = _metadata(meta, target)
    plan_ = deep_fetch.plan(root_entity, op, meta)
    statements: list[ExecutedStatement] = []

    root_compiled = compile_read(
        plan_.root_operation, meta, dialect, root_entity, result_form="instance", lock=lock
    )
    root_materialized = _execute_compiled(port, dialect, root_compiled, statements)
    root_rows = [row.values for row in root_materialized]

    assembler = materialize.Assembler(meta=meta)
    root_nodes = assembler.materialize_root(
        target,
        root_rows,
        narrow_to=root_compiled.narrow_to,
        resolved_position=root_compiled.resolved_position,
        resolved_entities=[row.resolved_entity for row in root_materialized],
        family_variants=[row.family_variant for row in root_materialized],
        documents=root_compiled.documents,
    )
    all_nodes: list[ObservedNode] = [
        ObservedNode(target, node, materialized.document)
        for node, materialized in zip(root_nodes, root_materialized, strict=True)
    ]

    level_rows: list[Sequence[Row]] = []
    level_nodes: list[list[materialize.Node]] = []
    for level in plan_.levels:
        parent_rows, parent_nodes = _guarded_parents(
            level, *_parent_data(level.parent, root_rows, root_nodes, level_rows, level_nodes)
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
        child_entity = _metadata(meta, child_target)
        child_compiled = compile_read(
            child_op,
            meta,
            dialect,
            child_entity,
            result_form="instance",
            lock=lock,
        )
        # A child level takes its narrow from `FetchLevel.narrow_to` (consumed
        # inside `attach_level`), never from the compiled read — only the ROOT
        # has no planner-supplied narrow to fall back on.
        child_materialized = _execute_compiled(port, dialect, child_compiled, statements)
        rows = [row.values for row in child_materialized]
        nodes = assembler.attach_level(
            level,
            parent_nodes,
            parent_rows,
            rows,
            resolved_position=child_compiled.resolved_position,
            resolved_entities=[row.resolved_entity for row in child_materialized],
            family_variants=[row.family_variant for row in child_materialized],
            documents=child_compiled.documents,
        )
        level_rows.append(rows)
        level_nodes.append(nodes)
        all_nodes.extend(
            ObservedNode(child_target, node, materialized.document)
            for node, materialized in zip(nodes, child_materialized, strict=True)
        )

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
    no includes). Rows are grouped in chronological edge order (Valid Time
    first, matching the corpus's own authored `then.graphs` order) rather than
    relying on the database's unspecified natural row order.
    """
    metadata = _metadata(meta, target)
    plan_ = deep_fetch.plan(metadata, op, meta)
    if plan_.levels:
        # m-case-format: a v1 milestone-set read carries no includes.
        raise ValueError("a milestone-set (history / asOfRange) read carries no deep-fetch levels")
    # `declaring_metadata` resolves the entity whose as-of axes are this target's
    # FAMILY's actual temporal declaration (the root, for a participant —
    # temporality is family-wide, `m-inheritance`); every
    # `~parallax.core.temporal_read` per-entity primitive below (`milestone_edge`,
    # `_edge_pin`, `_edge_sort_key`) MUST resolve through it rather than the
    # queried target's own (possibly locally-empty) axes.
    entity = declaring_metadata(meta, metadata.identity)
    compiled = compile_read(plan_.root_operation, meta, dialect, metadata, result_form="instance")
    statements: list[ExecutedStatement] = []
    materialized_rows = [
        compiled.materialize_row(row)
        for row in _execute(port, dialect, compiled.statement, statements)
    ]

    order: list[Edge] = []
    groups: dict[Edge, list[MaterializedReadRow]] = {}
    for row in sorted(materialized_rows, key=lambda row: _edge_sort_key(entity, row.values)):
        edge = milestone_edge(entity, row.values)
        if edge not in groups:
            groups[edge] = []
            order.append(edge)
        groups[edge].append(row)

    graphs = tuple(
        MilestoneGraph(
            pin=_edge_pin(entity, edge),
            nodes=tuple(
                materialize.Assembler(meta=meta).materialize_root(
                    target,
                    [row.values for row in groups[edge]],
                    narrow_to=compiled.narrow_to,
                    resolved_position=compiled.resolved_position,
                    resolved_entities=[row.resolved_entity for row in groups[edge]],
                    family_variants=[row.family_variant for row in groups[edge]],
                    documents=compiled.documents,
                )
            ),
        )
        for edge in order
    )
    return HistoryFindResult(graphs=graphs, execution=Execution(tuple(statements)))


def _execute_compiled(
    port: DbPort, dialect: Dialect, compiled: CompiledRead, statements: list[ExecutedStatement]
) -> list[MaterializedReadRow]:
    """Execute one compiled read, materializing its rows through its OWN transform.

    Takes the whole `~parallax.core.sql_gen.CompiledRead` rather than a statement
    plus a transform, so the two can only ever come from the same compile. That
    matters because `find` holds the root's and a child level's compiled reads in
    scope at the same time: crossing them is otherwise an ordinary-looking edit
    that raises deep inside the tag transform in one direction and, in the other,
    silently leaves the raw tag column standing where `familyVariant` should be.
    Keeping the pair bundled here is the caller-side half of `CompiledRead`'s own
    self-containment — it makes `find`'s "compile, execute, transform"
    structural rather than a convention every level has to remember.
    """
    return [
        compiled.materialize_row(row)
        for row in _execute(port, dialect, compiled.statement, statements)
    ]


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


def _guarded_parents(
    level: deep_fetch.FetchLevel,
    parent_rows: Sequence[Row],
    parent_nodes: Sequence[materialize.Node],
) -> tuple[Sequence[Row], Sequence[materialize.Node]]:
    """The parent rows and nodes a path-root guard admits into ``level``
    (m-deep-fetch "Path-root guards").

    A guard is a SOURCE filter, not a view: it selects which already-materialized
    parents this level gathers keys from and attaches to, so an excluded parent
    never sees the level's ``attach_key`` at all — the closed-world distinction
    between "no such related row" and "this object never participated". Selection
    is by each parent's OWN resolved concrete Entity, which is exactly what a
    guard's resolved source set enumerates. An unguarded level returns both
    sequences unchanged.
    """
    if level.source_position is None:
        return parent_rows, parent_nodes
    admitted = frozenset(level.source_position)
    pairs = [
        (row, node)
        for row, node in zip(parent_rows, parent_nodes, strict=True)
        if node.resolved_entity in admitted
    ]
    return [row for row, _ in pairs], [node for _, node in pairs]


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


# The wire spelling each Temporal Dimension is emitted under in a milestone-set
# graph's `then.graphs` pin entry (`m-case-format`). The dimension itself is
# structured everywhere above this seam.
_DIMENSION_NAMES: Final[Mapping[TemporalDimension, str]] = {
    TemporalDimension.VALID_TIME: "valid-time",
    TemporalDimension.TRANSACTION_TIME: "transaction-time",
}


def _metadata(meta: Metamodel, name: str) -> EntityMetadata:
    """``name``'s accepted Metadata within ``meta``, raising when the model
    declares no such Entity."""
    metadata = entity_by_name(meta, name)
    if metadata is None:  # pragma: no cover - a queried target is always declared
        raise KeyError(name)
    return metadata


def declaring_metadata(model: Metamodel, target: EntityIdentity) -> EntityMetadata:
    """The accepted Metadata of the position that DECLARES ``target``'s family
    facts — its family root, which for a standalone Entity is itself.

    Temporality and the physical primary key are family-wide and root-owned
    (`m-inheritance` "Inherited members"), so every per-entity milestone
    primitive below resolves through this rather than through the queried
    target's own (possibly locally empty) declaration.

    Keyed by Entity Identity rather than by an already-resolved Metadata, because
    a read's preflight answers an identity: the resolution is exact and the
    caller keeps no metadata it would otherwise have to thread.
    """
    position = inheritance.view(model).entity(target)
    root = model.entity(target if position is None else position.root)
    if root is None:  # pragma: no cover - preflight resolved this identity in this model
        raise ValueError(f"{target.canonical}: the model declares no family root")
    return root


def _start_column(entity: EntityMetadata, axis: AcceptedAsOfAxis) -> str:
    declared = entity.attribute(axis.start_attribute.name)
    if declared is None:  # pragma: no cover - an accepted axis names a declared Attribute
        raise ValueError(f"{entity.identity.canonical}: {axis.start_attribute.name} is undeclared")
    return declared.storage.name


def _edge_sort_key(entity: EntityMetadata, row: Row) -> tuple[object, ...]:
    """Valid Time first, then Transaction Time (m-sql's bind-order convention),
    each dimension's start-column value — used only to chronologically order a
    milestone-set read's grouped graphs, never to select or filter rows. A
    Temporal Dimension's member value IS that canonical rank."""
    ordered = sorted(entity.declared_as_of_axes, key=lambda axis: axis.dimension.value)
    return tuple(row[_start_column(entity, axis)] for axis in ordered)


def _edge_pin(entity: EntityMetadata, edge: Edge) -> dict[str, object]:
    """The milestone-set `then.graphs` `pin` entry keyed by dimension."""
    return {
        _DIMENSION_NAMES[axis.dimension]: (
            edge.valid_time if axis.dimension is TemporalDimension.VALID_TIME else edge.tx_time
        )
        for axis in entity.declared_as_of_axes
    }


def deep_fetch_statement_pin(op: op_algebra.Operation, entity: EntityMetadata) -> Pin:
    """``snapshot.pin`` for ``op`` (spec §3): identical to
    ``~parallax.core.temporal_read.statement_pin``, except that an outer
    ``DeepFetch`` directive (``.include(...)`` composed after ``.as_of(...)``)
    is peeled first. ``m-temporal-read`` never imports ``m-deep-fetch`` (the
    DAG forbids the reverse dependency direction), so `statement_pin`'s own
    directive-peeling (`Limit`/`OrderBy`/`Distinct` only) cannot see a
    `DeepFetch` wrapper — this composition is the
    handle's own job. A milestone-set read (`.history()`/`.as_of_range()`)
    never reaches here carrying an outer `DeepFetch`: that combination builds as
    an ordinary valid Find Query and the read preflight refuses it by name
    (spec §3 ``snapshot-history-includes``) before any pin is derived, so this
    peel is unconditionally safe.
    """
    pin_op = op.operand if isinstance(op, op_algebra.DeepFetch) else op
    return statement_pin(pin_op, entity)


def _pin_from_milestone(entity: EntityMetadata, milestone_pin: Mapping[str, object]) -> Pin:
    """One milestone's own edge, rendered as a :class:`Pin` (spec §3: each
    milestone-set root is edge-pinned at its own milestone's from-instant)."""
    coords: dict[str, object] = {}
    for axis in entity.declared_as_of_axes:
        name = _DIMENSION_NAMES[axis.dimension]
        if name in milestone_pin:
            coords[name] = milestone_pin[name]
    return Pin(
        tx_time=cast("Any", coords.get("transaction-time")),
        valid_time=cast("Any", coords.get("valid-time")),
    )


def snapshot_from_find_result(
    result: FindResult, target: str, meta: Metamodel, pin: Pin, runtime: EntityGraphConstruction
) -> Snapshot[Any]:
    roots = _materialized(lambda: wrap_graph(result.nodes, target, meta, pin, runtime))
    return Snapshot(roots, pin, result.execution)


def snapshot_from_history_result(
    result: HistoryFindResult, target: str, meta: Metamodel, runtime: EntityGraphConstruction
) -> Snapshot[Any]:
    entity = declaring_metadata(meta, _metadata(meta, target).identity)
    roots: list[Any] = []
    for graph in result.graphs:
        milestone_pin = _pin_from_milestone(entity, graph.pin)
        roots.extend(
            _materialized(lambda: wrap_graph(graph.nodes, target, meta, milestone_pin, runtime))  # noqa: B023
        )
    return Snapshot(tuple(roots), Pin(), result.execution)


def _materialized(build: Callable[[], tuple[object, ...]]) -> tuple[Any, ...]:
    """One graph's roots, or the single translation of a materialization failure.

    This is the ONE boundary where graph construction, lifecycle build, and
    state-factory failures become
    :class:`~parallax.snapshot.handle._errors.SnapshotMaterializationError`, so a
    caller sees exactly one wrapping with the original cause chained. Everything
    that failed BEFORE a graph was being built — the query, the connection, the
    transaction, the adapter, SQL generation, neutral decoding — has already
    raised with its own classification and never reaches here.
    """
    try:
        return build()
    except Exception as exc:
        raise SnapshotMaterializationError(
            "the read succeeded but its Entity graph could not be built "
            "(snapshot-materialization-failed)",
            cause=exc,
        ) from exc
