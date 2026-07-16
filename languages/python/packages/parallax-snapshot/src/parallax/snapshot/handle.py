"""``parallax.snapshot.handle`` — the composition surface (connect / transact / lowering).

This is the layer that legally sees **both** the neutral write-instruction IR /
flush planner (``m-unit-work``) **and** SQL generation (``m-sql`` / ``m-dialect``):
the module DAG forbids ``m-unit-work`` from importing ``m-sql`` (why the planner
emits a neutral :class:`~parallax.core.unit_work.FlushPlan`) and forbids ``m-sql``
from importing ``m-unit-work``, so the write-DML → SQL lowering — the deliberate
``m-sql`` edge M3 deferred — is composed **here**. :func:`lower_write` is the single
lowering function; both the developer transaction path (the injected
``FlushExecutor``) and the conformance engine reuse it (the conformance family is
the import-side DAG exemption), so there is exactly one write-lowering seam.

M4 lowers the **non-temporal keyed** write forms (`insert` / `update` / `delete` on
a non-temporal, non-inheritance entity, version carried as plain column data). The
temporal milestone forms (close-and-chain, rectangle splits), the optimistic-lock
version gate/advance, predicate-selected (set-based) writes, and inheritance-family
DML land with the write path (COR-3 Phase 8); reaching one raises a loud
:class:`WriteLoweringError` naming the deferral, never a wrong emission — mirroring
the read compiler's forward-error posture.

The **developer transaction surface** (spec §5) also composes here:
:meth:`Database.connect` wires a concrete ``m-db-port`` adapter to a metamodel,
and :meth:`Database.transact` is the callback demarcation — sentinel-backed
options, join with the option-conflict check, the ``m-auto-retry`` bounded retry
loop, and the injected flush executor that lowers each planned write and runs it
on the transaction's own connection. Per ledger D-16 (COR-3 Phase 7 increment
6a, full graduation) the :class:`Transaction` verbs take entity instances:
``insert(instance)`` (the Create Payload), ``update(edited_copy)`` (the sparse
row: primary key + effective change set), ``delete(node_or_instance)`` (keys
off it); :meth:`Database.find` / :meth:`Transaction.find` both wrap the SAME
production find executor below in ``Snapshot[T]`` (DQ6).

:meth:`Transaction.find` participates in the transaction (force-flush +
read-your-own-writes, the transaction's own lock suffix) by running the shared
:func:`find` / :func:`find_history` executor through
:meth:`~parallax.core.unit_work.UnitOfWork.read` — root canonicalization
(``m-temporal-read`` + ``m-navigate``) happens inside the shared executor via
``parallax.core.deep_fetch.plan``, never re-derived here.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, cast

from parallax.core import deep_fetch, inheritance, op_algebra
from parallax.core.auto_retry import run_with_retry
from parallax.core.db_port import DbPort, JsonDocument, Row
from parallax.core.descriptor import Entity, Metamodel, column_order
from parallax.core.dialect import POSTGRES, Dialect, LockMode
from parallax.core.entity import Entity as EntityBase
from parallax.core.entity import Statement as EntityStatement
from parallax.core.entity import (
    canonical_row,
    effective_change_set,
    entity_record_of,
    framework_owned_advance,
    full_row,
    primary_key_row,
)
from parallax.core.sql_gen import Statement, apply_family_variant, compile_read, family_variant_plan
from parallax.core.temporal_read import AXIS_ORDER, Edge, Pin, milestone_edge, statement_pin
from parallax.core.unit_work import (
    Clock,
    Concurrency,
    FlushExecutor,
    FlushPlan,
    KeyedWrite,
    PlannedWrite,
    PredicateWrite,
    SystemClock,
    TransactionSettings,
    UnitOfWork,
    UnitOfWorkError,
    active_unit_of_work,
    instructions,
    run_unit_of_work,
    validate_write,
)
from parallax.snapshot import materialize, wrap

__all__ = [
    "Database",
    "ExecutedStatement",
    "Execution",
    "FindResult",
    "HistoryFindResult",
    "MilestoneGraph",
    "NoResultFound",
    "Snapshot",
    "TooManyResultsFound",
    "Transaction",
    "TransactionOptionConflictError",
    "WriteLoweringError",
    "connect",
    "find",
    "find_history",
    "lower_write",
]

# The keyed mutation verbs M4 lowers (the non-temporal write triad). The temporal
# `*Until` / `terminate` verbs open / split / close milestones and land with the
# write path (Phase 8).
_NON_TEMPORAL_VERBS: Final[frozenset[str]] = frozenset({"insert", "update", "delete"})


class WriteLoweringError(ValueError):
    """A planned write cannot be lowered to DML by the M4 (non-temporal keyed) path."""


def lower_write(planned: PlannedWrite, meta: Metamodel, dialect: Dialect) -> list[Statement]:
    """Lower one planned write to its ordered DML statements (m-sql write DML).

    ``planned`` is one execution-ordered item of a :class:`FlushPlan`: a (coalesced,
    FK-ordered, elided) write instruction plus its bound transaction observation.
    Returns the ordered statements the write emits — one for a keyed non-temporal
    write, more once the temporal / rectangle-split forms land (Phase 8). The
    temporal forms will additionally consume the flush's Clock-supplied processing
    instant (``FlushPlan.tx_instant``, bound as ``in_z`` / the close instant); the
    non-temporal forms M4 lowers do not, so it is threaded in with those forms.
    """
    instruction = planned.instruction
    if isinstance(instruction, PredicateWrite):
        raise WriteLoweringError(
            f"predicate-selected (set-based) write on {instruction.target.entity!r}: "
            "materialize-then-lower lands with the write path (COR-3 Phase 8; m-batch-write / "
            "m-opt-lock)"
        )
    observation = planned.observation
    if observation is not None and (
        observation.version is not None or observation.in_z is not None
    ):
        raise WriteLoweringError(
            f"optimistic-lock gated write on {instruction.entity!r}: the version gate / advance "
            "lands with the write path (COR-3 Phase 8; m-opt-lock)"
        )
    entity = meta.entity(instruction.entity)
    # Temporal classification MUST be the family-EFFECTIVE one (ADR 0026): an
    # inheritance participant declares its as-of axes on the root alone, so
    # `entity.is_temporal` (a bare, non-flattening LOCAL view) would silently
    # miss a temporal-family concrete's own write here — it would still be
    # refused just below (any inheritance participant is out of scope for
    # M4), but with the wrong reason and the wrong classification printed.
    declaring = inheritance.declaring_entity(meta, entity)
    if declaring.is_temporal:
        raise WriteLoweringError(
            f"temporal write on {entity.name!r} ({declaring.temporal}): milestone lowering "
            "(close-and-chain / rectangle split) lands with the write path (COR-3 Phase 8; "
            "m-audit-write / m-bitemp-write)"
        )
    if entity.inheritance is not None:
        raise WriteLoweringError(
            f"inheritance-family write on {entity.name!r}: tag / concrete-subtype DML lands with "
            "the write path (COR-3 Phase 8; m-inheritance)"
        )
    if instruction.business_from is not None or instruction.business_to is not None:
        raise WriteLoweringError(
            f"{instruction.mutation!r} on the non-temporal entity {entity.name!r} carries a "
            "business bound; bounded writes are temporal (COR-3 Phase 8)"
        )
    if instruction.mutation not in _NON_TEMPORAL_VERBS:
        raise WriteLoweringError(
            f"{instruction.mutation!r} is a temporal milestone verb; its lowering lands with the "
            "write path (COR-3 Phase 8)"
        )
    if len(instruction.rows) != 1:
        raise WriteLoweringError(
            f"multi-row keyed {instruction.mutation!r} on {entity.name!r} "
            f"({len(instruction.rows)} rows): the set-based collapse lands with the write path "
            "(COR-3 Phase 8; m-batch-write) — M4 lowers single-row keyed writes only"
        )
    _refuse_computed_markers(entity, instruction)
    if instruction.mutation == "insert":
        return [_lower_insert(entity, instruction, dialect)]
    if instruction.mutation == "update":
        return [_lower_update(entity, instruction, dialect)]
    return [_lower_delete(entity, instruction, dialect)]


def _refuse_computed_markers(entity: Entity, instruction: KeyedWrite) -> None:
    """Refuse a row whose scalar-attribute value is a DB-computed marker.

    The write-instruction schema classifies a row value by the member's metamodel
    role, not its shape: a value-object member legitimately carries a whole
    document, but a **scalar** attribute carrying a mapping (e.g. the pk-gen
    ``{increment: n}`` / ``{computed: …}`` marker) means the database derives the
    value, so the generating implementation must emit the strategy's SQL fragment
    — a lowering M4 does not have. Refusing here (before any plan executes) keeps
    the forward-error posture: never a wrong emission, never a literally-bound
    marker document.
    """
    members = _members(entity)
    for name, value in instruction.rows[0].items():
        _column, is_value_object = members[name]
        if not is_value_object and isinstance(value, Mapping):
            raise WriteLoweringError(
                f"DB-computed marker on {entity.name!r}.{name}: computed-column emission "
                "(the pk-gen registry strategies and friends) lands with the write path "
                "(COR-3 Phase 8; m-pk-gen)"
            )


def _lower_insert(entity: Entity, instruction: KeyedWrite, dialect: Dialect) -> Statement:
    """`insert into <table>(<present columns in columnOrder>) values (?, …)`.

    Only the columns the write input names are emitted — a row omitting a nullable
    column produces a narrower `INSERT` (never an explicit `NULL` bind), matching the
    corpus (`m-unit-work-003` inserts 4 of OrderItem's 5 columns).
    """
    cells = _ordered_cells(entity, instruction.rows[0])
    columns = ", ".join(dialect.quote(column) for _, column, _ in cells)
    holes = ", ".join("?" for _ in cells)
    binds = tuple(bind for _, _, bind in cells)
    return Statement(f"insert into {entity.table}({columns}) values ({holes})", binds)


def _lower_update(entity: Entity, instruction: KeyedWrite, dialect: Dialect) -> Statement:
    """`update <table> set <non-pk columns in columnOrder> = ? where <pk> = ?`.

    The `SET` columns follow descriptor `columnOrder` (not the row's data order); the
    `WHERE` keys on the primary key. Binds are the set values then the key values.
    """
    pk_columns = {attr.column for attr in entity.primary_key}
    set_cells = [
        cell for cell in _ordered_cells(entity, instruction.rows[0]) if cell[1] not in pk_columns
    ]
    assignments = ", ".join(f"{dialect.quote(column)} = ?" for _, column, _ in set_cells)
    where_sql, key_binds = _key_predicate(entity, instruction.rows[0], dialect)
    binds = (*(bind for _, _, bind in set_cells), *key_binds)
    return Statement(f"update {entity.table} set {assignments} where {where_sql}", binds)


def _lower_delete(entity: Entity, instruction: KeyedWrite, dialect: Dialect) -> Statement:
    """`delete from <table> where <pk> = ?` — keyed by the primary key."""
    where_sql, key_binds = _key_predicate(entity, instruction.rows[0], dialect)
    return Statement(f"delete from {entity.table} where {where_sql}", key_binds)


def _ordered_cells(entity: Entity, row: Mapping[str, object]) -> list[tuple[int, str, object]]:
    """The row's present members as `(columnOrder index, column, bind)`, ordered.

    Each row key names a declared scalar attribute or a value object; a value-object
    member binds as one :class:`JsonDocument` in its `columnOrder` position (the
    whole document — the write never decomposes it), a scalar binds its value.
    """
    members = _members(entity)
    order = {column: index for index, column in enumerate(column_order(entity))}
    cells: list[tuple[int, str, object]] = []
    for name, value in row.items():
        column, is_value_object = members[name]
        bind = JsonDocument(value) if is_value_object else value
        cells.append((order[column], column, bind))
    cells.sort(key=lambda cell: cell[0])
    return cells


def _key_predicate(
    entity: Entity, row: Mapping[str, object], dialect: Dialect
) -> tuple[str, tuple[object, ...]]:
    """The `<pk1> = ? [and <pk2> = ?]` predicate and its ordered key binds."""
    keys = entity.primary_key
    predicate = " and ".join(f"{dialect.quote(attr.column)} = ?" for attr in keys)
    binds = tuple(row[attr.name] for attr in keys)
    return predicate, binds


def _members(entity: Entity) -> dict[str, tuple[str, bool]]:
    """Map each writable member name to `(column, is_value_object)`."""
    members: dict[str, tuple[str, bool]] = {
        attr.name: (attr.column, False) for attr in entity.attributes
    }
    for value_object in entity.value_objects:
        members[value_object.name] = (value_object.column, True)
    return members


# --------------------------------------------------------------------------- #
# The production find executor (m-deep-fetch / m-snapshot-read; COR-3 Phase 7  #
# increment 5). The module DAG's snapshot-handle scope already reaches         #
# `materialize` + `m-sql` + `m-db-port`, so the deliberate DAG-forbidden edges  #
# (`m-deep-fetch`/`m-snapshot-read` may not import `m-sql`; `m-sql` may not    #
# import `m-navigate`/`m-temporal-read`) are composed HERE, exactly like       #
# `lower_write` composes the write-side `m-unit-work` x `m-sql` edge above —   #
# one executor, production-owned: `db.find`/`tx.find` (a later increment) and  #
# the conformance run lane both call the SAME `find`/`find_history`, wrap or   #
# render the SAME neutral `materialize.Node`s, and no engine-local level loop  #
# exists anywhere in this codebase.                                            #
# --------------------------------------------------------------------------- #
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
    """A single-graph find's root nodes plus its execution record."""

    nodes: tuple[materialize.Node, ...]
    execution: Execution


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
    feeds the assembler. Returns the root's own materialized nodes — reached
    from them, every attached level's nodes hang off `Node.fields` — plus the
    full ordered execution record.
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
    root_nodes = assembler.materialize_root(target, root_rows)

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

    return FindResult(nodes=tuple(root_nodes), execution=Execution(tuple(statements)))


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
        raise ValueError(  # pragma: no cover - m-case-format: v1 carries no includes
            "a milestone-set (history / asOfRange) read carries no deep-fetch levels"
        )
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


# --------------------------------------------------------------------------- #
# The developer transaction surface (spec §5) — connect / transact.           #
# --------------------------------------------------------------------------- #


class TransactionOptionConflictError(ValueError):
    """A joining ``db.transact`` call tried to re-negotiate the boundary.

    A joining call may not change the active transaction's settings: an explicit
    (non-``None``) option whose value conflicts with the outermost boundary's
    resolved setting raises; an explicit equal value and an omitted option are
    accepted (spec §5).
    """


@dataclass(frozen=True, slots=True)
class _ResolvedOptions:
    """The outermost boundary's resolved ``db.transact`` options.

    ``concurrency`` also lives on the core :class:`TransactionSettings`;
    ``retries`` and ``retry_optimistic_conflicts`` are demarcation-level only
    (the core unit of work never sees them). ``retry_optimistic_conflicts`` is
    stored for the join/conflict contract but cannot alter retry classification
    yet — no optimistic-conflict error category exists until ``m-opt-lock``
    (COR-3 Phase 8; see ``parallax.core.auto_retry``).
    """

    retries: int
    concurrency: Concurrency
    retry_optimistic_conflicts: bool


@dataclass(frozen=True, slots=True)
class _Demarcation:
    """What the outermost boundary publishes on the unit of work's ``companion``.

    A joining ``db.transact`` call needs the same :class:`Transaction` to hand
    its closure and the boundary's resolved options for the conflict check;
    both ride core's single per-thread active binding, so their visibility ends
    exactly when it does (no handle-owned thread-local, nothing to clean up).
    """

    tx: Transaction
    options: _ResolvedOptions


class Transaction:
    """The developer transaction handed to a ``db.transact`` closure (spec §5).

    A facade over the active unit of work and the transaction's own connection.
    The graduated D-16 verbs take entity instances: :meth:`insert` a full
    instance (the Create Payload), :meth:`update` an edited copy (the sparse
    row: primary key + effective change set — an empty effective set is a
    no-op, zero round trips), :meth:`delete` a node or instance (keys off its
    primary key). :meth:`find` runs a participating read and returns
    ``Snapshot[T]`` (DQ6): force-flush + the transaction's own lock suffix,
    otherwise identical to :meth:`Database.find`. A reference used after its
    owning scope ends raises
    :class:`~parallax.core.unit_work.EscapedTransactionError` (every verb
    delegates to the unit of work, which fences use-after-scope).
    """

    __slots__ = ("_conn", "_dialect", "_meta", "_uow")

    def __init__(
        self,
        uow: UnitOfWork,
        conn: DbPort,
        meta: Metamodel,
        dialect: Dialect,
    ) -> None:
        self._uow = uow
        self._conn = conn
        self._meta = meta
        self._dialect = dialect

    def insert(self, instance: EntityBase) -> None:
        """Buffer a keyed ``insert`` of a full instance (the Create Payload,
        spec §5): every member the instance actually SET."""
        record = _entity_record_of_instance(instance)
        self._buffer("insert", record.name, full_row(instance))

    def update(self, copy: EntityBase) -> None:
        """Buffer a sparse keyed ``update``: primary key + the effective change
        set of an edited copy (touched fields whose current value differs from
        the recorded original, spec §3/§5). An EMPTY effective change set
        issues no DML at all (zero round trips, the net-zero-chain no-op rule).
        Raises :class:`~parallax.core.entity.ProvenanceError` for a
        provenance-less instance (never produced via ``model_copy``)."""
        record = _entity_record_of_instance(copy)
        effective = effective_change_set(copy)
        if not effective:
            return
        row: dict[str, object] = primary_key_row(copy)
        row.update(canonical_row(copy, effective))
        row.update(framework_owned_advance(copy))
        self._buffer("update", record.name, row)

    def delete(self, node_or_instance: EntityBase) -> None:
        """Buffer a keyed ``delete``, keyed off ``node_or_instance``'s primary
        key (a frozen ``Snapshot`` node, a fresh instance, or an edited copy —
        all carry valid primary-key values, spec §5)."""
        record = _entity_record_of_instance(node_or_instance)
        self._buffer("delete", record.name, primary_key_row(node_or_instance))

    def find(self, statement: EntityStatement) -> Snapshot[Any]:
        """Run a participating read for ``statement`` and return ``Snapshot[T]``
        (DQ6): force-flushes pending writes first (read-your-own-writes), and
        the transaction's participation mode renders the read-lock suffix
        (``locking`` takes the dialect's shared row lock; ``optimistic`` takes
        none). Otherwise identical to :meth:`Database.find` — the SAME shared
        find executor, the SAME frozen-node wrapping. Returns ``Snapshot[Any]``:
        the concrete root type is resolved only at runtime (from the
        statement's own target), so callers annotate their own binding
        (``snapshot: Snapshot[Order] = tx.find(...)``) for static typing.
        """
        target = statement.target
        op = statement.operation()
        entity = inheritance.declaring_entity(self._meta, self._meta.entity(target))
        pin = _statement_pin(op, entity)
        lock = self._uow.settings.concurrency
        if _is_milestone_set_op(op):
            history_result = self._uow.read(
                lambda: find_history(op, self._meta, self._dialect, target, self._conn)
            )
            return _snapshot_from_history_result(history_result, target, self._meta)
        find_result = self._uow.read(
            lambda: find(op, self._meta, self._dialect, target, self._conn, lock=lock)
        )
        return _snapshot_from_find_result(find_result, target, self._meta, pin)

    def _buffer(self, mutation: str, entity: str, row: Mapping[str, object]) -> None:
        # The document route buys the IR's structural validation (no `at` alias,
        # no observation keys) first (`deserialize`), then the model-aware
        # `validate_write` (the SAME validator the conformance engine's
        # rejected lane calls, COR-3 Phase 8 increment 2 — one validator, two
        # callers): its inheritance payload-shape checks
        # (`subtype-write-metadata-field` / `-sibling-attribute` /
        # `-set-based-unsupported`, m-inheritance) classify a framework-owned
        # metadata key or a cross-branch field MORE SPECIFICALLY than the
        # generic member-name-honesty gate below ever could, so it runs
        # first — member-name honesty (`validate_instruction`) still catches
        # any OTHERWISE-unknown member a validate_write pass left unexamined
        # (it walks only DECLARED members, never flags a stray key itself).
        instruction = instructions.deserialize(
            {"mutation": mutation, "entity": entity, "rows": [dict(row)]}
        )
        validate_write(self._meta.entity(entity), row, self._meta, mutation=mutation)
        instructions.validate_instruction(instruction, self._meta)
        self._uow.buffer(instruction)


def _entity_record_of_instance(instance: EntityBase) -> Entity:
    record = entity_record_of(type(instance))
    if record is None:  # pragma: no cover - guards a non-Parallax-compiled class
        raise TypeError(f"{type(instance).__name__} is not a registered Parallax entity class")
    return record


def _statement_pin(op: op_algebra.Operation, entity: Entity) -> Pin:
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


def _is_milestone_set_op(op: op_algebra.Operation) -> bool:
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


def _snapshot_from_find_result(
    result: FindResult, target: str, meta: Metamodel, pin: Pin
) -> Snapshot[Any]:
    roots = wrap.wrap_graph(result.nodes, target, meta, pin)
    return Snapshot(roots, pin, result.execution)


def _snapshot_from_history_result(
    result: HistoryFindResult, target: str, meta: Metamodel
) -> Snapshot[Any]:
    entity = inheritance.declaring_entity(meta, meta.entity(target))
    roots: list[Any] = []
    for graph in result.graphs:
        milestone_pin = _pin_from_milestone(entity, graph.pin)
        roots.extend(wrap.wrap_graph(graph.nodes, target, meta, milestone_pin))
    return Snapshot(tuple(roots), Pin(), result.execution)


class Database:
    """A connected Parallax database handle: one adapter, one metamodel (spec §5)."""

    __slots__ = ("_clock", "_dialect", "_meta", "_port")

    def __init__(
        self,
        port: DbPort,
        meta: Metamodel,
        *,
        dialect: Dialect = POSTGRES,
        clock: Clock | None = None,
    ) -> None:
        self._port = port
        self._meta = meta
        self._dialect = dialect
        self._clock: Clock = clock if clock is not None else SystemClock()

    @classmethod
    def connect(
        cls,
        adapter: DbPort,
        meta: Metamodel,
        *,
        dialect: Dialect = POSTGRES,
        clock: Clock | None = None,
    ) -> Database:
        """Wire a concrete ``m-db-port`` adapter to the metamodel it will serve.

        The composition-root entry point (spec §8): only the root names a
        concrete adapter; everything above works against the port. ``dialect``
        defaults to the sole adapter's; ``clock`` defaults to the system clock
        (inject a fixed clock in tests).
        """
        return cls(adapter, meta, dialect=dialect, clock=clock)

    def find(self, statement: EntityStatement) -> Snapshot[Any]:
        """Execute ``statement`` exactly once, materializing fully, and return
        ``Snapshot[T]`` (spec §3). Non-transactional: no read lock, no
        participation mode. ``.history()`` / ``.as_of_range()`` return one root
        per milestone, each edge-pinned at its own milestone's from-instant.
        Returns ``Snapshot[Any]``: the concrete root type is resolved only at
        runtime (from the statement's own target), so callers annotate their
        own binding (``snapshot: Snapshot[Order] = db.find(...)``) for static
        typing.
        """
        target = statement.target
        op = statement.operation()
        entity = inheritance.declaring_entity(self._meta, self._meta.entity(target))
        pin = _statement_pin(op, entity)
        if _is_milestone_set_op(op):
            history_result = find_history(op, self._meta, self._dialect, target, self._port)
            return _snapshot_from_history_result(history_result, target, self._meta)
        find_result = find(op, self._meta, self._dialect, target, self._port)
        return _snapshot_from_find_result(find_result, target, self._meta, pin)

    def transact[T](
        self,
        fn: Callable[[Transaction], T],
        *,
        retries: int | None = None,
        concurrency: Concurrency | None = None,
        retry_optimistic_conflicts: bool | None = None,
    ) -> T:
        """Run ``fn(tx)`` in a transaction, returning its value only after commit.

        Every option is sentinel-backed (spec §5): ``None`` means *apply the
        outermost defaults when this call opens the transaction* (``retries=10``,
        ``concurrency="locking"``, ``retry_optimistic_conflicts=False``) *and
        inherit the active transaction's settings when it joins one*. A call
        while a transaction is active on the current thread joins it — the
        closure receives the **same** :class:`Transaction`, its value returns
        immediately, and an explicit option that conflicts with the boundary
        raises :class:`TransactionOptionConflictError`. The outermost boundary
        owns commit, abort, and the ``m-auto-retry`` bounded retry loop; abort
        withholds the callback value, and an inner failure dooms the whole
        transaction (rollback-only) even if caught.
        """
        active = active_unit_of_work()
        if active is not None:
            demarcation = active.companion
            if not isinstance(demarcation, _Demarcation):
                raise UnitOfWorkError(
                    "a bare unit of work is active on this thread; db.transact can "
                    "only join a transaction it opened"
                )
            _check_join_options(
                demarcation.options,
                retries=retries,
                concurrency=concurrency,
                retry_optimistic_conflicts=retry_optimistic_conflicts,
            )
            # The join path returns immediately and ignores these arguments in
            # favor of the active transaction's own (m-unit-work); rollback-only
            # foreclosure happens before the closure runs.
            return run_unit_of_work(
                lambda _: fn(demarcation.tx),
                settings=active.settings,
                clock=active.clock,
                meta=active.meta,
                flush_executor=active.flush_executor,
            )
        options = _ResolvedOptions(
            retries=retries if retries is not None else 10,
            concurrency=concurrency if concurrency is not None else "locking",
            retry_optimistic_conflicts=(
                retry_optimistic_conflicts if retry_optimistic_conflicts is not None else False
            ),
        )

        def attempt() -> T:
            def in_txn(conn: DbPort) -> T:
                def body(uow: UnitOfWork) -> T:
                    tx = Transaction(uow, conn, self._meta, self._dialect)
                    # Published for joining calls; visible only while core's
                    # active-transaction binding is, so it needs no cleanup.
                    uow.companion = _Demarcation(tx=tx, options=options)
                    return fn(tx)

                return run_unit_of_work(
                    body,
                    settings=TransactionSettings(concurrency=options.concurrency),
                    clock=self._clock,
                    meta=self._meta,
                    flush_executor=_flush_executor(conn, self._meta, self._dialect),
                )

            return self._port.transaction(in_txn)

        return run_with_retry(attempt, retries=options.retries)


# The spec §8 module-level spelling of the composition-root entry point.
connect = Database.connect


def _check_join_options(
    active: _ResolvedOptions,
    *,
    retries: int | None,
    concurrency: Concurrency | None,
    retry_optimistic_conflicts: bool | None,
) -> None:
    """Refuse a joining call's explicit option that conflicts with the boundary."""
    _refuse_conflict("retries", retries, active.retries)
    _refuse_conflict("concurrency", concurrency, active.concurrency)
    _refuse_conflict(
        "retry_optimistic_conflicts", retry_optimistic_conflicts, active.retry_optimistic_conflicts
    )


def _refuse_conflict(name: str, explicit: object | None, active_value: object) -> None:
    if explicit is not None and explicit != active_value:
        raise TransactionOptionConflictError(
            f"cannot join the active transaction with {name}={explicit!r}: the boundary "
            f"was opened with {name}={active_value!r} (a joining call may not "
            "re-negotiate; omit the option to inherit)"
        )


def _flush_executor(conn: DbPort, meta: Metamodel, dialect: Dialect) -> FlushExecutor:
    """The unit of work's injected flush sink: lower each planned write, execute it.

    The single write-lowering seam (:func:`lower_write`) run on the transaction's
    own connection, inside the still-open ``port.transaction`` scope — so an
    abort rolls back force-flushed writes with everything else.
    """

    def execute(plan: FlushPlan) -> None:
        for planned in plan.writes:
            for statement in lower_write(planned, meta, dialect):
                conn.execute_write(dialect.to_driver_sql(statement.sql), list(statement.binds))

    return execute
