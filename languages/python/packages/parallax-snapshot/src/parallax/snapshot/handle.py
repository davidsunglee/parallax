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
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Final

from parallax.core import op_algebra
from parallax.core.auto_retry import run_with_retry
from parallax.core.db_port import DbPort, JsonDocument, Row
from parallax.core.descriptor import Entity, Metamodel, column_order
from parallax.core.dialect import POSTGRES, Dialect
from parallax.core.sql_gen import Statement, compile_read
from parallax.core.temporal_read import inject_as_of
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

__all__ = [
    "Database",
    "Transaction",
    "TransactionOptionConflictError",
    "WriteLoweringError",
    "connect",
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
                "(a later write increment; m-pk-gen)"
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
        dialect's shared row lock; ``optimistic`` takes none).
        """
        operation = inject_as_of(op_algebra.deserialize(op), self._meta.entity(entity))
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
