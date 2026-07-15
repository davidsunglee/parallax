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
on the transaction's own connection. Per ledger D-16 the :class:`Transaction`
verbs are **neutral and provisional**: they buffer keyed write *documents* and
``find`` returns *rows*; the entity-instance signatures (materialized finds,
``insert(instance)`` / sparse ``update(edited_copy)``) graduate with the Phase-7
instance model.

:meth:`Transaction.find` is also where ``m-navigate`` composes (COR-3 Phase 7
increment 3, the same M2-precedent composition order the conformance engine
uses): ``m-temporal-read``'s root as-of injection runs first, then
``parallax.core.navigate.canonicalize`` rewrites every navigation hop's own
per-hop as-of propagation, both before ``compile_read`` — the module DAG
forbids ``m-sql`` from ever seeing a temporal wrapper.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Final, cast

from parallax.core import deep_fetch, navigate, op_algebra
from parallax.core.auto_retry import run_with_retry
from parallax.core.db_port import DbPort, JsonDocument, Row
from parallax.core.descriptor import Entity, Metamodel, column_order
from parallax.core.dialect import POSTGRES, Dialect, LockMode
from parallax.core.sql_gen import Statement, apply_family_variant, compile_read, family_variant_plan
from parallax.core.temporal_read import (
    AXIS_ORDER,
    Edge,
    inject_as_of,
    milestone_edge,
    resolve_pinned_instants,
)
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
)
from parallax.snapshot import materialize

__all__ = [
    "Database",
    "ExecutedStatement",
    "Execution",
    "FindResult",
    "HistoryFindResult",
    "MilestoneGraph",
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
    if entity.is_temporal:
        raise WriteLoweringError(
            f"temporal write on {entity.name!r} ({entity.temporal}): milestone lowering "
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
    compile-eligibility posture is not this module's concern)."""

    sql: str
    binds: tuple[object, ...]


@dataclass(frozen=True, slots=True)
class Execution:
    """The ordered record of every statement one `find` / `find_history` call
    executed — the production analogue of the conformance adapter's `emissions`
    + `roundTrips`, built once here and consumed by both."""

    statements: tuple[ExecutedStatement, ...]

    @property
    def round_trips(self) -> int:
        return len(self.statements)


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
    entity = meta.entity(target)
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
    statements.append(ExecutedStatement(statement.sql, statement.binds))
    return port.execute(dialect.to_driver_sql(statement.sql), list(statement.binds))


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
    The verbs are the **neutral, provisional** D-16 surface: the write triad
    buffers keyed write *documents* (deserialized and member-validated on
    entry), and :meth:`find` runs a participating read returning *rows*; the
    entity-instance signatures graduate with the Phase-7 instance model. A
    reference used after its owning scope ends raises
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

    def insert(self, entity: str, row: Mapping[str, object]) -> None:
        """Buffer a keyed ``insert`` of one full row (attribute name -> value)."""
        self._buffer("insert", entity, row)

    def update(self, entity: str, row: Mapping[str, object]) -> None:
        """Buffer a keyed ``update``: the primary key plus the changed members."""
        self._buffer("update", entity, row)

    def delete(self, entity: str, row: Mapping[str, object]) -> None:
        """Buffer a keyed ``delete`` of the row named by its primary key."""
        self._buffer("delete", entity, row)

    def find(self, entity: str, op: Mapping[str, object]) -> list[Row]:
        """Run a participating read for ``op`` (an operation document) on ``entity``.

        Read-your-own-writes: pending buffered writes are force-flushed inside
        the still-open atomic scope before the read runs. The transaction's
        participation mode renders the read-lock suffix (``locking`` takes the
        dialect's shared row lock; ``optimistic`` takes none). Navigation hops
        (``exists`` / ``notExists`` / ``navigate``) canonicalize their own
        per-hop as-of propagation immediately after the root's own injection —
        the same composition-at-the-engine order every read compile site shares
        (COR-3 Phase 7 increment 3).
        """
        raw_operation = op_algebra.deserialize(op)
        root_entity = self._meta.entity(entity)
        root_pins = resolve_pinned_instants(raw_operation, root_entity)
        injected = inject_as_of(raw_operation, root_entity)
        operation = navigate.canonicalize(injected, self._meta, root_pins)
        statement = compile_read(
            operation,
            self._meta,
            self._dialect,
            entity,
            result_form="row",
            lock=self._uow.settings.concurrency,
        )
        return self._uow.read(
            lambda: self._conn.execute(
                self._dialect.to_driver_sql(statement.sql), list(statement.binds)
            )
        )

    def _buffer(self, mutation: str, entity: str, row: Mapping[str, object]) -> None:
        # The document route buys the IR's structural validation (no `at` alias,
        # no observation keys) before member-name honesty against the metamodel.
        instruction = instructions.deserialize(
            {"mutation": mutation, "entity": entity, "rows": [dict(row)]}
        )
        instructions.validate_instruction(instruction, self._meta)
        self._uow.buffer(instruction)


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
