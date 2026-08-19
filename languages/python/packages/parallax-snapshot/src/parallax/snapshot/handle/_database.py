"""``parallax.snapshot.handle._database`` — demarcation and the flush edge (spec §5).

The composition root's own module: :meth:`Database.connect` wires a concrete
``m-db-port`` adapter to a metamodel, :meth:`Database.find` runs the shared read
executor once outside any transaction, :meth:`Database.read_rows` runs the values
lane's own entry for a caller that wants the transformed row itself, and
:meth:`Database.transact` is the
callback demarcation — sentinel-backed options, join with the option-conflict
check, the ``m-auto-retry`` bounded retry loop, and the flush executor it injects
into the unit of work.

That injected executor is where the package's two halves meet: it lowers the
Write Plan the injected :class:`~parallax.core.unit_work.WritePlanner` produces
through :func:`~parallax.snapshot.handle._write_lowering.stream_lowered` and runs
each statement on the transaction's own connection, so an abort rolls back
force-flushed writes with everything else. ``parallax.core.auto_retry`` may not
import ``parallax.core.opt_lock``, so the ``retry_optimistic_conflicts`` opt-in's
classification branch (``_optimistic_conflict_retriable``) is composed here too.

This is the TOP of the package's internal graph: it imports
:mod:`parallax.snapshot.handle._read`, :mod:`~parallax.snapshot.handle._transaction`,
:mod:`~parallax.snapshot.handle._preflight` for the shared read gate,
:mod:`~parallax.snapshot.handle._write_lowering`,
:mod:`~parallax.snapshot.handle._write_types`, and
:mod:`~parallax.snapshot.handle._planning` for the one Write Planner it builds
once per connected Metamodel, and nothing in the package imports it except
``handle/__init__.py``, which re-exports its five public names
(:class:`Database`, :func:`connect`, :class:`TransactionOptionConflictError`,
:class:`TransactionOwnershipError`, :class:`TransactionRollbackError`) through
the frozen ``__all__``. Because only
those five cross the boundary, every helper here keeps its leading underscore —
the cross-module bare-name convention the sibling modules follow has nothing to
bite on.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Final

from parallax.core.auto_retry import run_with_retry
from parallax.core.db_port import (
    BeginFailed,
    Committed,
    DbPort,
    RollbackFailed,
    RolledBack,
    TransactionOutcome,
)
from parallax.core.dialect import POSTGRES, Dialect

# Sibling implementation modules. None of these names carries a leading
# underscore, precisely because it crosses a module boundary: privacy is carried
# by the private MODULE names and by the package's frozen `__all__`, not by
# per-name underscores, which under pyright strict would make every intra-package
# import a reportPrivateUsage error.
# First-party support, deliberately absent from `parallax.core.entity`'s exports:
# this composition root connects to an accepted `Metamodel` and materializes
# rows, so it needs both facts out of a Domain Model.
from parallax.core.entity import (
    DomainModel,
    EntityGraphConstruction,
    EntityRowCodec,
    graph_construction_of,
    row_codec_of,
)
from parallax.core.entity._model import class_index, model_of
from parallax.core.execution_lifecycle import ExecutionLifecycleProvider
from parallax.core.execution_lifecycle._activity import INERT, WriteBatchActivity, open_read_root
from parallax.core.metamodel import Metamodel
from parallax.core.object_query import ObjectQueryNode
from parallax.core.object_query._fluent import ObjectQuery, object_query_node
from parallax.core.temporal_read import scans_an_axis
from parallax.core.unit_work import (
    Clock,
    Concurrency,
    FlushExecutor,
    OptimisticLockConflictError,
    RollbackOnlyError,
    SubjectIdentity,
    SystemClock,
    TransactionSettings,
    UnitOfWork,
    UnitOfWorkError,
    WriteBatchTrigger,
    WritePlan,
    WritePlanner,
    active_unit_of_work,
    capture_subject_identity,
    enforce_affected_rows,
    run_unit_of_work,
)
from parallax.snapshot.handle._errors import SnapshotConnectionError
from parallax.snapshot.handle._planning import build_write_planner
from parallax.snapshot.handle._preflight import preflight
from parallax.snapshot.handle._read import (
    ResultPublication,
    RowsResult,
    Snapshot,
    find,
    find_history,
    find_rows,
    typed_publication,
    wire_publication,
)
from parallax.snapshot.handle._transaction import Transaction
from parallax.snapshot.handle._wire import WireDatabaseView
from parallax.snapshot.handle._write_lowering import stream_lowered

__all__ = [
    "Database",
    "TransactionOptionConflictError",
    "TransactionOwnershipError",
    "TransactionRollbackError",
    "connect",
]

# The audit-neutral Subject Identity every production planning request carries
# while no Principal attributes one: private, module-local, and captured through
# the boundary's own nonempty check (`capture_subject_identity`) — never a
# Principal implementation, a default identity, or a public caller option.
# Attributed capture belongs to the outer database-operation boundary a Principal
# is read at, which is the only place that can name a subject.
_UNATTRIBUTED_SUBJECT_IDENTITY: Final[SubjectIdentity] = capture_subject_identity("unattributed")


class TransactionOptionConflictError(ValueError):
    """A joining ``db.transact`` call tried to re-negotiate the boundary.

    A joining call may not change the active transaction's settings: an explicit
    (non-``None``) option whose value conflicts with the outermost boundary's
    resolved setting raises; an explicit equal value and an omitted option are
    accepted (spec §5).
    """


class TransactionOwnershipError(RuntimeError):
    """A nested ``db.transact`` call was made through a foreign ``Database``.

    The active demarcation records the exact ``Database`` object that opened it,
    and a nested call joins only through that same object. An alias of the owner
    joins and receives the identical :class:`Transaction`; every different handle
    is refused even when it carries the same model, adapter, dialect, clock, or
    otherwise equivalent configuration, because the owner is scoped state rather
    than a registry keyed by any of those.

    The refusal precedes rollback-only joining, the option-conflict check,
    closure execution, Unit of Work mutation, SQL, and adapter access, and
    retains neither handle — :data:`code` and the message are its whole public
    state.
    """

    code: Final[str] = "transaction-owner-mismatch"


class TransactionRollbackError(RuntimeError):
    """The transaction could not be undone after something ended it.

    Two failures are live at once and reporting either alone misreports what
    happened: :attr:`triggering_error` ended the transaction, and
    :attr:`rollback_error` is why undoing it did not complete. The rollback error
    is the ``__cause__`` as well, so a reader of the traceback sees why the
    trigger is no longer the whole story.

    What the transaction left behind is therefore unknown, which is why this is
    never retried however retriable the trigger was, and why the port discards
    the connection it happened on. A control-flow or fatal trigger — a
    ``KeyboardInterrupt``, a cancellation — is never wrapped in this: it stays
    primary and carries the rollback failure as its own cause instead, so a
    shutdown in progress is not downgraded to an ordinary error.
    """

    def __init__(self, triggering_error: BaseException, rollback_error: Exception) -> None:
        super().__init__(
            f"the transaction could not be rolled back after {triggering_error!r}; "
            f"the rollback failed with {rollback_error!r}, so what it left behind is unknown"
        )
        self.triggering_error = triggering_error
        self.rollback_error = rollback_error


class _UnattemptedBoundary(Exception):
    """A begin failure in transit past the bounded retry loop.

    A transaction that never began ran no attempt, so `m-execution-lifecycle`
    makes its failure terminal however retriable the error's own category is —
    but ``m-auto-retry`` classifies by the exception it catches, and a begin
    failure is an ordinary :class:`~parallax.core.db_error.DatabaseError` like
    any other. Travelling as a type the loop does not catch is what makes it
    terminal; :meth:`Database.transact` unwraps it immediately outside the loop,
    so nothing above ever sees this class.
    """

    def __init__(self, error: Exception) -> None:
        super().__init__(error)
        self.error = error


@dataclass(frozen=True, slots=True)
class _ConnectedModel:
    """The model one ``Database`` serves: its accepted metadata, the Entity Row
    Codec every write derives its rows through, and — for a class-backed model —
    the Entity Graph Construction collaboration that materializes rows into
    instances of the classes it composed.

    Owned by the Database rather than by any query value, and carrying no
    identity of its own — two Databases over one Domain Model hold equal state
    and neither is preferred, while a query built from classes this model never
    composed is refused by target resolution rather than by ownership. Holding
    the construction rather than the raw class index keeps materialization
    capability behind ONE seam: there is no second capability bag to widen when a
    new entry point (a Session) reaches the same materializer.

    The two capabilities are held as two references rather than as one composite
    value, and only one of them can be absent: a row is derived from accepted
    metadata alone, so the bare-Metamodel connection the conformance adapter
    constructs for the write lanes reaches a fully functional codec while
    reaching no materializer at all.
    """

    meta: Metamodel
    codec: EntityRowCodec
    construction: EntityGraphConstruction | None

    def materializing(self) -> EntityGraphConstruction:
        """The graph construction a modeled read needs, or refuse before any I/O."""
        if self.construction is None:
            raise SnapshotConnectionError(
                "this Database was connected to a model that composed no Entity Class, so it "
                "cannot materialize a Snapshot (snapshot-class-backed-model-required)"
            )
        return self.construction


@dataclass(frozen=True, slots=True)
class _ResolvedOptions:
    """The outermost boundary's resolved ``db.transact`` options.

    ``concurrency`` also lives on the core :class:`TransactionSettings`;
    ``retries`` and ``retry_optimistic_conflicts`` are demarcation-level only
    (the core unit of work never sees them). ``retry_optimistic_conflicts``
    is stored for the join/conflict contract AND gates
    :func:`_optimistic_conflict_retriable` — the opt-in-only classification
    branch :meth:`Database.transact` injects into
    :func:`~parallax.core.auto_retry.run_with_retry` (`m-opt-lock`
    "Retry contract").
    """

    retries: int
    concurrency: Concurrency
    retry_optimistic_conflicts: bool


@dataclass(frozen=True, slots=True)
class _Demarcation:
    """What the outermost boundary publishes on the unit of work's ``companion``.

    A joining ``db.transact`` call needs the same :class:`Transaction` to hand
    its closure, the boundary's resolved options for the conflict check, and the
    exact :class:`Database` that opened the boundary so ownership can be settled
    before either; all three ride core's single per-thread active binding, so
    their visibility ends exactly when it does (no handle-owned thread-local,
    nothing to clean up). ``owner`` is a strong reference deliberately: it is
    scoped state whose lifetime is the demarcation's, not a registry entry.
    """

    tx: Transaction
    options: _ResolvedOptions
    owner: Database


class Database:
    """A connected Parallax database handle: one adapter, one metamodel (spec §5)."""

    __slots__ = (
        "_clock",
        "_connected",
        "_dialect",
        "_lifecycle",
        "_meta",
        "_planner",
        "_port",
    )

    def __init__(
        self,
        port: DbPort,
        model: DomainModel | Metamodel,
        *,
        dialect: Dialect = POSTGRES,
        clock: Clock | None = None,
        lifecycle_provider: ExecutionLifecycleProvider | None = None,
    ) -> None:
        """Connect to ``model``, which the developer entry point narrows further.

        A bare accepted Metamodel is the first-party neutral-write form the
        conformance adapter constructs: it serves the write lanes, which name
        Entities rather than classes, and refuses every modeled read.
        :meth:`connect` admits only a class-backed Domain Model, so an
        application never reaches that state.
        """
        self._connected = (
            _ConnectedModel(
                meta=model_of(model),
                codec=row_codec_of(model),
                construction=(None if class_index(model) is None else graph_construction_of(model)),
            )
            if isinstance(model, DomainModel)
            else _ConnectedModel(meta=model, codec=EntityRowCodec(model), construction=None)
        )
        self._port = port
        self._meta: Metamodel = self._connected.meta
        self._dialect = dialect
        self._clock: Clock = clock if clock is not None else SystemClock()
        # Absent by default, and absence is the whole default path: every
        # operation below branches on it before allocating a UUID, a descriptor,
        # a publisher, a counter, an event, or a lifecycle clock read
        # (`m-execution-lifecycle` "Cost and retention").
        self._lifecycle = lifecycle_provider
        # One Write Planner per connected Metamodel, reused across every
        # `transact()` attempt (`m-unit-work`: the planner is constructed once
        # per accepted Metamodel with its strategy adapters already wired).
        self._planner: WritePlanner = build_write_planner(self._meta)

    @classmethod
    def connect(
        cls,
        adapter: DbPort,
        model: DomainModel,
        *,
        dialect: Dialect = POSTGRES,
        clock: Clock | None = None,
        lifecycle_provider: ExecutionLifecycleProvider | None = None,
    ) -> Database:
        """Wire a concrete ``m-db-port`` adapter to the Domain Model it will serve.

        The composition-root entry point (spec §8): only the root names a
        concrete adapter; everything above works against the port. ``dialect``
        defaults to the sole adapter's; ``clock`` defaults to the system clock
        (inject a fixed clock in tests). ``lifecycle_provider`` is the ONE
        execution-lifecycle seam (`m-execution-lifecycle`): the Provider owns
        its own error reporter, so there is no second argument, and omitting it
        is what makes this connection's operations do no lifecycle work at all.

        ``model`` is a Domain Model of either provenance, and WHICH provenance
        decides capability rather than which constructor ran: a class-backed
        model supports both public read interfaces, and a descriptor-backed one
        supports Wire and refuses Typed materialization at the read call, before
        any I/O. Only a bare accepted Metamodel — the first-party form
        :meth:`__init__` still admits — is refused here with
        :class:`~parallax.snapshot.handle._errors.SnapshotConnectionError`,
        before the adapter is inspected: it is a model no descriptor produced and
        no application holds. One model connects to any number of Databases, and
        one Entity Class participates in any number of models.
        """
        if not isinstance(model, DomainModel):  # pyright: ignore[reportUnnecessaryIsInstance] - the runtime half of the same narrowing: an untyped caller reaches this with the bare Metamodel `__init__` admits
            raise SnapshotConnectionError(
                "connect() takes a Domain Model — one composed from Entity Classes, or one "
                "a descriptor produced (snapshot-class-backed-model-required); a bare "
                "accepted Metamodel is a first-party form no application holds"
            )
        return cls(
            adapter, model, dialect=dialect, clock=clock, lifecycle_provider=lifecycle_provider
        )

    def find[S](self, query: ObjectQuery[Any, S]) -> Snapshot[S]:
        """Execute ``query`` exactly once, materializing fully, and return
        ``Snapshot[S]`` (spec §3). Non-transactional: no read lock, no
        Concurrency Preference. ``.history()`` / ``.as_of_range()`` return one root
        per milestone, each edge-pinned at its own milestone's from-instant.

        Target resolution and query validation are the shared
        :func:`~parallax.snapshot.handle._preflight.preflight` seam's, so this
        and :meth:`Transaction.find` differ only in locking, unit-of-work
        wrapping, and participation. The canonical query is read once here and
        kept locally through this execution.

        A STANDALONE read still retains the write evidence its rows observed onto
        the values it publishes — a value's evidence belongs to the value — and
        simply stamps no participation on them, which is what lets an
        effective-Optimistic write import that evidence while an
        effective-Locking one cannot.

        The Snapshot's parameter is the query's RESULT — what ``narrow`` moved
        it to, or the queried Entity itself — so a narrowed find yields the
        narrowed rows' type without a caller-side annotation.
        """
        # The connection refusal precedes preflight, exactly as it does on
        # `Transaction.find`: a Database that cannot materialize a Snapshot at
        # all answers that before it answers anything about this query, so the
        # two entry points refuse a classless connection in the same order.
        construction = self._connected.materializing()
        node = object_query_node(query)
        return self._read(node, typed_publication(self._meta, construction))

    @property
    def wire(self) -> WireDatabaseView:
        """This connection's Wire read interface (spec §3).

        A lightweight view over the SAME connected model, adapter, and dialect —
        not a second connection and not a format switch. It needs no Entity
        Class, which is why a descriptor-backed connection answers this and
        refuses :meth:`find`.
        """
        return WireDatabaseView(self._wire_find)

    def _wire_find(self, node: ObjectQueryNode) -> Snapshot[Any]:
        """One Wire read: :meth:`_read` under the wire publication."""
        return self._read(node, wire_publication(self._meta))

    def _read[R](self, node: ObjectQueryNode, publication: ResultPublication[R]) -> R:
        """One non-transactional read of ``node``, published through
        ``publication`` — the whole composition both read interfaces run.

        The gate, the milestone-set dispatch, and the executor entry are the
        read; which materializer publishes its result is decided only after
        execution has finished. Non-transactional in the same three ways for
        both: no read lock, no Concurrency Preference, and no participation
        stamped on the values it publishes. Their evidence is their own: a
        standalone read retains the state each row observed exactly as a
        participating one does, and differs only in the license that carries.

        The Root Execution opens AFTER the gate and spans through publication:
        the gate is deterministic and reaches no port, so a refused read creates
        no root and calls no Provider, while planning, lowering, every Database
        Call, conversion, and materialization are all inside the Read activity.
        """
        preflight(node, model=self._meta, form="graph")
        with open_read_root(
            self._lifecycle, target=node.target, interface=publication.interface
        ) as read:
            if scans_an_axis(node):
                return publication.from_history(
                    find_history(node, self._meta, self._dialect, self._port, read=read)
                )
            return publication.from_find(
                find(node, self._meta, self._dialect, self._port, read=read)
            )

    def read_rows(self, query: ObjectQueryNode) -> RowsResult:
        """Execute ``query`` exactly once outside any transaction and return its
        published rows — the values lane, first-party rather than a third public
        result format.

        It shares the canonicalization, the compilation, and the recorded call
        with :meth:`find`, and fetches no relationship level and builds no graph
        at all, because the transformed row is already the representation. A row
        whose stored state contradicted the model publishes its
        :class:`~parallax.snapshot.materialize.InvalidData` record in place of
        itself, exactly as a graph-form root does.

        Non-transactional, exactly as :meth:`find` is: no read lock, no
        Concurrency Preference, and no stamped participation — and, like every
        row-form read, no retained evidence at all. It opens its own Read root
        after the same gate the graph form crosses.
        """
        preflight(query, model=self._meta, form="rows")
        root = open_read_root(self._lifecycle, target=query.target, interface="ROWS")
        with root as read:
            return find_rows(query, self._meta, self._dialect, self._port, read=read)

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
        ``concurrency="optimistic"``, ``retry_optimistic_conflicts=False``) *and
        inherit the active transaction's settings when it joins one*.
        ``concurrency`` is a Concurrency PREFERENCE: each Entity's own Optimistic
        Lock Facet decides whether it participates optimistically or falls back
        to the shared read lock, so one transaction mixes both (`m-unit-work`
        "Strategy selection"). A call
        while a transaction is active on the current thread joins it, but only
        through the exact ``Database`` that opened the boundary — any other
        handle raises :class:`TransactionOwnershipError` before every later
        joining check. A joining call's closure receives the **same**
        :class:`Transaction`, its value returns immediately, and an explicit
        option that conflicts with the boundary raises
        :class:`TransactionOptionConflictError`. The outermost boundary
        owns commit, abort, and the ``m-auto-retry`` bounded retry loop; abort
        withholds the callback value, and an inner failure dooms the whole
        transaction (rollback-only) even if caught.

        A failure that ends the transaction reaches the caller as itself once the
        rollback has completed — the callback's own exception, or the database's.
        The exception is a rollback that did NOT complete: both live errors then
        matter, so the caller sees :class:`TransactionRollbackError` carrying
        each, and that outcome is never retried. A boundary that never began is
        terminal for the same reason inverted: no attempt ran, so there is
        nothing to re-execute.

        The callback's value is what this answers, directly: an invocation
        retains no record of what it did, and what a Provider observed about it
        was delivered while it ran (`m-execution-lifecycle`).
        """
        active = active_unit_of_work()
        if active is not None:
            demarcation = active.companion
            if not isinstance(demarcation, _Demarcation):
                raise UnitOfWorkError(
                    "a bare unit of work is active on this thread; db.transact can "
                    "only join a transaction it opened"
                )
            if demarcation.owner is not self:
                raise TransactionOwnershipError(
                    "this Database did not open the active transaction, so it cannot "
                    "join it (transaction-owner-mismatch); only the exact Database "
                    "object that opened the boundary joins, however equivalent "
                    "another handle's model, adapter, dialect, or clock may be"
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
                write_batch_starting=active.write_batch_starting,
                planner=self._planner,
                subject_identity=_UNATTRIBUTED_SUBJECT_IDENTITY,
            )
        options = _ResolvedOptions(
            retries=retries if retries is not None else 10,
            concurrency=concurrency if concurrency is not None else "optimistic",
            retry_optimistic_conflicts=(
                retry_optimistic_conflicts if retry_optimistic_conflicts is not None else False
            ),
        )

        # The unit of work plans against the accepted model the ``Database`` already
        # holds; a joining call inherits the active unit of work's own.
        model = self._meta

        construction = self._connected.construction
        codec = self._connected.codec

        def attempt() -> T:
            def in_txn(conn: DbPort) -> T:
                def body(uow: UnitOfWork) -> T:
                    tx = Transaction(
                        uow,
                        conn,
                        self._meta,
                        self._dialect,
                        construction,
                        codec,
                    )
                    # Published for joining calls; visible only while core's
                    # active-transaction binding is, so it needs no cleanup.
                    uow.companion = _Demarcation(tx=tx, options=options, owner=self)
                    return fn(tx)

                return run_unit_of_work(
                    body,
                    settings=TransactionSettings(concurrency=options.concurrency),
                    clock=self._clock,
                    meta=model,
                    flush_executor=_flush_executor(conn, model, self._dialect, INERT),
                    # The injected Write Planner — `parallax.snapshot.handle`
                    # is the sole module cleared to import both `batch_write`
                    # and `m-unit-work`, so it alone builds the strategy
                    # adapters `build_write_planner` wires. The conformance
                    # compile lane calls the SAME factory, so the two lanes
                    # plan through one deterministic computation.
                    planner=self._planner,
                    subject_identity=_UNATTRIBUTED_SUBJECT_IDENTITY,
                )

            return _attempted(self._port.transaction(in_txn))

        try:
            return run_with_retry(
                attempt,
                retries=options.retries,
                extra_retriable=(
                    _optimistic_conflict_retriable if options.retry_optimistic_conflicts else None
                ),
            )
        except _UnattemptedBoundary as unattempted:
            # Re-raised here rather than at the port, so the loop sees a type it
            # does not retry. `from` its own cause keeps the carrier out of the
            # chain the caller reads, leaving exactly the error the port made.
            raise unattempted.error from unattempted.error.__cause__


def _attempted[T](outcome: TransactionOutcome[T]) -> T:
    """What one physical attempt answers, from the boundary outcome the port reported.

    The port reports what happened; this decides what a caller sees, which is the
    only place the two can be reconciled — the port cannot know that a rollback
    failure must never be retried while a rolled-back deadlock must be, and the
    retry loop cannot know which phase failed.

    A rolled-back transaction propagates its triggering error unchanged, so what
    a caller catches is what their own callback or the database raised. Only a
    failed rollback substitutes an error of its own, because then neither live
    error tells the whole story.
    """
    match outcome:
        case Committed(value):
            return value
        case BeginFailed(error):
            raise _UnattemptedBoundary(error) from error
        case RolledBack(trigger):
            raise trigger.error
        case RollbackFailed(trigger, rollback_error):
            triggering_error = trigger.error
            if isinstance(triggering_error, Exception):
                raise TransactionRollbackError(triggering_error, rollback_error) from rollback_error
            # A control-flow or fatal trigger stays primary: an interrupt or a
            # cancellation is not an ordinary failure to be wrapped in one.
            raise triggering_error from rollback_error


def _optimistic_conflict_retriable(exc: BaseException) -> bool:
    """The ``retry_optimistic_conflicts`` opt-in's own retriability verdict
    (`m-opt-lock` "Retry contract"; `m-auto-retry.md` "Which failures are
    retriable"; ADR 0008 / `python.md` §5 L622-624) — injected into
    :func:`~parallax.core.auto_retry.run_with_retry` as its
    ``extra_retriable`` extension ONLY when the resolved option is set
    (:meth:`Database.transact`, above).

    The retry loop already recognizes the canonical conflict; what stays
    caller policy is whether a recognized conflict is RETRIED, which is what
    this predicate answers. It covers the SAME two raise shapes
    :func:`~parallax.core.auto_retry._retriable_failure` already distinguishes
    for a transient database failure: the conflict itself, or the rollback-only
    refusal whose ``__cause__`` preserves it (the JOIN case — an inner joined
    scope's own conflict marks the root rollback-only, and the outermost retry
    loop still applies per the original failure's category, spec §5). The
    remaining Write Effect Errors are never named here: a Stale Write, a Missing
    Target, and a Cardinality Corruption stay outside the retriable set
    unconditionally, opt-in or not.
    """
    if isinstance(exc, OptimisticLockConflictError):
        return True
    if isinstance(exc, RollbackOnlyError):
        return isinstance(exc.__cause__, OptimisticLockConflictError)
    return False


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


def _flush_executor(
    conn: DbPort, model: Metamodel, dialect: Dialect, batch: WriteBatchActivity
) -> FlushExecutor:
    """The unit of work's injected flush sink: lower each planned step, execute
    every statement in order, and hand each result back to the unit of work to
    interpret.

    The single write-lowering seam (:func:`stream_lowered`) run on the
    transaction's own connection, inside the still-open ``port.transaction``
    scope — so an abort rolls back force-flushed writes with everything else.
    Every step lowers to exactly one statement, and a temporal mutation's close
    precedes the rows it chains, so a failure on the close aborts BEFORE those
    rows ever execute.

    This executor performs NO classification of its own: the injected Write
    Planner already spent the concurrency mode while settling each step, and
    this reports only the driver's count to
    :func:`~parallax.core.unit_work.enforce_affected_rows`, which owns the
    authoritative reading of the step's Affected Rows Policy (ADR 0048).

    One flush is ONE Write Batch (`m-execution-lifecycle`) however many
    statements the plan lowers to — a batch is a flush, not a statement — and
    each statement is one Database Call child of it. ``batch`` is the activity
    that batch publishes under: the transactional caller supplies the shared
    inert activity, whose Database Call scopes emit nothing.
    """

    def execute(plan: WritePlan, *, trigger: WriteBatchTrigger) -> None:
        for step, statement in stream_lowered(plan, model, dialect):
            with batch.database_call(statement, "WRITE", step.entity) as call:
                affected = conn.execute_write(
                    dialect.to_driver_sql(statement.sql), list(statement.binds)
                )
                call.write_completed(affected)
            enforce_affected_rows(step, affected)

    return execute
