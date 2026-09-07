"""``parallax.snapshot.handle._database`` — preparation and the composition root.

:func:`prepare_model` runs every finite, fallible model-only derivation into
one complete :class:`~parallax.snapshot.handle._publication.ModelSelection`,
and :meth:`Database.connect` wires a concrete ``m-db-port`` adapter to the
Serving Model it will serve. The handle itself retains nothing model-derived:
:meth:`Database.find`, :meth:`Database.stream`, and :meth:`Database.read_rows`
delegate to the one :class:`~parallax.snapshot.handle._read_scope.ReadScope`
this connection owns — the same scope its Wire view retains, and the same scope
every stream it opens is delivered through — and :meth:`Database.transact`
refuses re-entry and delegates to the one
:class:`~parallax.snapshot.handle._demarcation.Demarcation` it built at connect.
Both hold the Serving Model and adopt its current selection per execution, so
a publication reaches every later execution of this handle without the handle
caching, rebuilding, or comparing anything.

Preparation lives here rather than beside the selection it builds because a
Write Planner's strategy adapters reach the SQL-lowering group, which the sealed
:mod:`~parallax.snapshot.handle._publication` scope may not; that scope owns
:func:`~parallax.snapshot.handle._publication.select_model`, the one builder of
a :class:`~parallax.snapshot.handle._publication.ModelSelection`, and this
module is its one caller. A ``Database`` connected to a bare Domain Model
prepares it once under a generated edition into a private Serving Model of its
own, so the static shorthand and an explicitly shared Serving Model enter the
same execution paths.

This is the TOP of the package's internal graph: it imports
:mod:`~parallax.snapshot.handle._demarcation` for the transaction demarcation,
:mod:`~parallax.snapshot.handle._read_scope` for the read composition it owns
one of, :mod:`~parallax.snapshot.handle._publication` for the selection it
prepares and the Serving Model it holds, and
:mod:`~parallax.snapshot.handle._planning` for the one Write Planner each
selection carries, and nothing in the package imports it except
``handle/__init__.py``, which re-exports its three public names
(:class:`Database`, :func:`connect`, :func:`prepare_model`) through the frozen
``__all__``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import uuid4

from parallax.core.db_port import DbPort, IsolationLevel

# Sibling implementation modules. None of these names carries a leading
# underscore, precisely because it crosses a module boundary: privacy is carried
# by the private MODULE names and by the package's frozen `__all__`, not by
# per-name underscores, which under pyright strict would make every intra-package
# import a reportPrivateUsage error.
# First-party support, deliberately absent from `parallax.core.entity`'s exports:
# preparation derives every model-bound capability from the accepted `Metamodel`
# and the class index, which are the two facts a Domain Model answers.
from parallax.core.entity import DomainModel, EntityGraphConstruction, EntityRowCodec
from parallax.core.entity._layout import CatalogedModel
from parallax.core.entity._model import class_index, model_of
from parallax.core.execution_lifecycle import ExecutionLifecycleProvider
from parallax.core.execution_lifecycle._activity import (
    InstalledLifecycle,
    installed_lifecycle,
    refuse_reentry,
)
from parallax.core.object_query import ObjectQueryNode
from parallax.core.object_query._fluent import ObjectQuery
from parallax.core.unit_work import Clock, Concurrency, SystemClock
from parallax.snapshot.handle._demarcation import Demarcation
from parallax.snapshot.handle._errors import SnapshotConnectionError
from parallax.snapshot.handle._planning import build_write_planner
from parallax.snapshot.handle._publication import (
    ModelSelection,
    ServingModel,
    check_edition,
    select_model,
)
from parallax.snapshot.handle._read import RowsResult, Snapshot
from parallax.snapshot.handle._read_scope import standalone_read_scope
from parallax.snapshot.handle._stream import SnapshotStream
from parallax.snapshot.handle._transaction import Transaction
from parallax.snapshot.handle._wire import WireDatabaseView

__all__ = [
    "Database",
    "connect",
    "prepare_model",
]


def prepare_model(model: DomainModel, *, edition: str) -> ModelSelection:
    """Prepare ``model`` under ``edition``: one complete selection, or raise.

    Preparing means constructing every model-bound capability whole — the
    exact-model layouts, the row codec's per-Entity facts, and, for a
    class-backed model, the graph construction's — so nothing fallible that
    depends on the model alone remains to run on a request path. Each
    collaborator raises on its first refusal and no partial selection escapes.
    A descriptor-backed model prepares with no graph construction: it serves
    Wire and the write lanes and refuses Typed materialization at the read call.

    Preparation runs no query, inspects no schema, and promises nothing about
    stored data, future queries, or database availability. The selection is
    process-local and holds no connection, transaction, Clock, or lifecycle
    provider. ``edition`` is an opaque nonempty token compared only for
    equality; :class:`ValueError` refuses an empty one before any derivation,
    and :class:`TypeError` refuses a value that is no Domain Model.
    """
    check_edition(edition)
    if not isinstance(model, DomainModel):  # pyright: ignore[reportUnnecessaryIsInstance] - the runtime half of the annotation, so an untyped caller is named
        raise TypeError(
            f"prepare_model takes a Domain Model — one composed from Entity Classes, or one a "
            f"descriptor produced — not {model!r}"
        )
    catalog = CatalogedModel(model_of(model))
    classes = class_index(model)
    return select_model(
        model,
        edition=edition,
        catalog=catalog,
        construction=(
            None
            if classes is None
            else EntityGraphConstruction(catalog.meta, classes, catalog.layouts)
        ),
        codec=EntityRowCodec(catalog.meta),
        planner=build_write_planner(catalog.meta),
    )


class Database:
    """A connected Parallax database handle: one adapter, one Serving Model (spec §5)."""

    __slots__ = (
        "_clock",
        "_demarcation",
        "_lifecycle",
        "_port",
        "_reads",
    )

    def __init__(
        self,
        port: DbPort,
        model: DomainModel | ServingModel,
        *,
        clock: Clock | None = None,
        lifecycle_provider: ExecutionLifecycleProvider | None = None,
    ) -> None:
        """Connect to ``model``: a Serving Model, or a Domain Model of either
        provenance.

        A Domain Model is prepared once, here, under a generated opaque edition
        that stays fixed for this connection's life, and held in a private
        Serving Model nothing else can publish to; a Serving Model handed in is
        held as itself, so two connections over one flip together when it
        publishes. Either way the connection retains no selection: every
        transaction attempt and every standalone read adopts whatever the
        Serving Model holds when it begins, and runs against products derived
        whole at preparation. Provenance decides capability rather than which
        constructor ran: a descriptor-backed model composes no Entity Class, so
        it serves Wire and the write lanes — which name Entities rather than
        classes — and refuses every modeled read at the read call.
        """
        if isinstance(model, ServingModel):
            serving = model
        elif isinstance(model, DomainModel):  # pyright: ignore[reportUnnecessaryIsInstance] - the runtime half of the same narrowing, so an untyped caller is named rather than failing on a missing attribute
            # One static selection, prepared whole before this handle can
            # serve. Two independent connections over one model carry two
            # generated editions; sharing one is explicit preparation's job.
            serving = ServingModel(prepare_model(model, edition=f"static-{uuid4().hex}"))
        else:
            raise SnapshotConnectionError(
                "a Database connects to a Domain Model — one composed from Entity Classes, or "
                "one a descriptor produced — or to a ServingModel holding a prepared one; a "
                "bare accepted Metamodel names no model a connection can serve "
                "(snapshot-class-backed-model-required)"
            )
        self._port = port
        self._clock: Clock = clock if clock is not None else SystemClock()
        # Absent by default, and absence is the whole default path: every
        # operation below branches on it before allocating a UUID, a descriptor,
        # a publisher, a counter, an event, or a lifecycle clock read
        # (`m-execution-lifecycle` "Cost and retention"). What is present when a
        # Provider is installed is that Provider plus this handle's own
        # per-thread re-entry state, because every call into the Provider has to
        # be made inside it for an operation coming back OUT of the Provider to
        # be refusable.
        self._lifecycle: InstalledLifecycle | None = installed_lifecycle(lifecycle_provider)
        # The one Read Scope this connection's eager reads run through — its
        # own Typed verbs and the Wire view it answers alike (spec §5 "Private
        # read composition") — and the one demarcation its transactions run
        # through. Both adopt from the same Serving Model.
        self._reads = standalone_read_scope(lifecycle=self._lifecycle, serving=serving, port=port)
        self._demarcation = Demarcation(port, self._clock, self._lifecycle, serving)

    @classmethod
    def connect(
        cls,
        adapter: DbPort,
        model: DomainModel | ServingModel,
        *,
        clock: Clock | None = None,
        lifecycle_provider: ExecutionLifecycleProvider | None = None,
    ) -> Database:
        """Wire a concrete ``m-db-port`` adapter to the model it will serve.

        The composition-root entry point (spec §8): only the root names a
        concrete adapter; everything above works against the port, and the
        dialect every statement is spelled in is that adapter's own.
        ``clock`` defaults to the system clock
        (inject a fixed clock in tests). ``lifecycle_provider`` is the ONE
        execution-lifecycle seam (`m-execution-lifecycle`): the Provider owns
        its own error reporter, so there is no second argument, and omitting it
        is what makes this connection's operations do no lifecycle work at all.

        ``model`` is a :class:`ServingModel`, whose current selection every
        execution of this handle adopts, or a Domain Model of either
        provenance — the static shorthand, prepared once into a private Serving
        Model. WHICH provenance decides capability rather than which
        constructor ran: a class-backed model supports both public read
        interfaces, and a descriptor-backed one supports Wire and refuses Typed
        materialization at the read call, before any I/O. A value that is
        neither is refused here with
        :class:`~parallax.snapshot.handle._errors.SnapshotConnectionError`,
        before the adapter is inspected, and :meth:`__init__` refuses the same
        shape one level down. One model connects to any number of Databases, and
        one Entity Class participates in any number of models.
        """
        if not isinstance(model, DomainModel | ServingModel):  # pyright: ignore[reportUnnecessaryIsInstance] - the runtime half of the same narrowing, kept here so the developer entry point diagnoses in its own words
            raise SnapshotConnectionError(
                "connect() takes a Domain Model — one composed from Entity Classes, or one "
                "a descriptor produced — or a ServingModel holding a prepared one "
                "(snapshot-class-backed-model-required); a bare accepted Metamodel is a "
                "form no application holds"
            )
        return cls(adapter, model, clock=clock, lifecycle_provider=lifecycle_provider)

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

        The read adopts the Serving Model's current selection once, for its
        whole execution, and the Snapshot retains that edition as
        ``snapshot.edition``. An ordinary failure escaping the execution — a
        statement, conversion, materialization — surfaces as
        :class:`~parallax.snapshot.handle.ExecutionFailure` under that edition;
        the deterministic refusals before it, re-entry and the read gate, keep
        their own types, and so does a lifecycle Provider that fails to open.
        """
        return self._reads.find(query)

    def stream[S](self, query: ObjectQuery[Any, S], *, batch_size: int = 1000) -> SnapshotStream[S]:
        """Deliver ``query``'s roots one at a time, in the Continuation Order,
        as the scope-bound single-pass peer of :meth:`find`.

        Nothing executes until the returned stream's scope is entered, and the
        whole result is never materialized: each page of ``batch_size`` root
        positions is deep-fetched into one sealed graph and published one root
        at a time, so what Parallax holds is one page plus one root rather than
        the result.

        ``batch_size`` counts ROOT positions — never included relationship rows
        — and, over storage the model describes, is a performance dial alone: it
        changes neither the order roots arrive in, nor which roots arrive, nor
        what any of them carries. :class:`SnapshotStream` names the one stored
        value that falls outside that. It is validated exactly as ``limit`` is,
        at this call and before any I/O.

        This call judges what it was handed — re-entry first, then the query
        and the page size — and adopts nothing. The stream adopts the Serving
        Model's current selection when its scope is entered, which is where a
        connection that can materialize no Snapshot at all refuses it, and
        retains that selection through every page; ``stream.edition`` names
        it inside the scope. An ordinary failure escaping the delivery
        surfaces as :class:`~parallax.snapshot.handle.ExecutionFailure` under
        that edition.
        """
        return self._reads.stream(query, batch_size)

    @property
    def wire(self) -> WireDatabaseView:
        """This connection's Wire read interface (spec §3).

        A lightweight view over the SAME connected model and adapter —
        not a second connection and not a format switch. It needs no Entity
        Class, which is why a descriptor-backed connection answers this and
        refuses :meth:`find`.

        The view retains this connection's one Read Scope, so a Wire read enters
        at that scope's own verb rather than at anything this property built:
        re-entry is refused there, at the same first line ``db.find`` crosses.
        """
        return WireDatabaseView(self._reads)

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
        return self._reads.read_rows(query)

    def transact[T](
        self,
        fn: Callable[[Transaction], T],
        *,
        retries: int | None = None,
        concurrency: Concurrency | None = None,
        retry_optimistic_conflicts: bool | None = None,
        isolation: IsolationLevel | None = None,
    ) -> T:
        """Run ``fn(tx)`` in a transaction, returning its value only after commit.

        Every option is sentinel-backed (spec §5): ``None`` means *apply the
        outermost defaults when this call opens the transaction* (``retries=10``,
        ``concurrency="optimistic"``, ``retry_optimistic_conflicts=False``) *and
        inherit the active transaction's settings when it joins one*.
        ``concurrency`` is a Concurrency PREFERENCE: each Entity's own Optimistic
        Lock Facet decides whether it participates optimistically or falls back
        to the shared read lock, so one transaction mixes both (`m-unit-work`
        "Strategy selection"). ``retries`` bounds re-executions rather than total
        attempts, and a negative bound is a deterministic refusal raised before
        any transaction is opened or observed. ``isolation`` names one of the
        three portable Isolation Levels (:data:`~parallax.core.db_port.
        IsolationLevel`), each defined by the anomalies it forbids and mapped by
        the adapter to its own database; omitting it asks for nothing and leaves
        whatever the adapter or its driver defaults to. Any other value is a
        deterministic :class:`ValueError`, raised — like a negative retry bound —
        before any transaction is opened or observed, and before this call is
        even compared against an active boundary, so a joining call naming a
        level outside the vocabulary is refused as invalid rather than as a
        conflict. Every physical attempt of one invocation opens at the same
        requested level, and `tx.stream` inherits it. A call
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

        Each outer attempt adopts the Serving Model's current selection before
        its boundary is asked to begin and retains it through commit or
        rollback; ``tx.edition`` names it. A retry adopts afresh, so one
        invocation may run attempts under two editions, and a joining call
        inherits the active attempt's selection without adopting.

        An ordinary failure that ends the invocation reaches the caller as
        :class:`~parallax.snapshot.handle.ExecutionFailure`, carrying the
        edition of the attempt that failed last and, as its cause, the error
        itself once the rollback has completed — the callback's own exception,
        or the database's. A rollback that did NOT complete leaves both live
        errors mattering, so the cause is then
        :class:`~parallax.snapshot.handle.TransactionRollbackError` carrying
        each, and that outcome is never retried. A boundary that never opened is
        terminal for the same reason inverted: no callback ran, so there is
        nothing to re-execute. The deterministic refusals above, a lifecycle
        Provider that fails to open, and a control-flow or fatal exception keep
        their own types and are never contextualized.

        The callback's value is what this answers, directly: an invocation
        retains no record of what it did, and what a Provider observed about it
        was delivered while it ran (`m-execution-lifecycle`).
        """
        refuse_reentry(self._lifecycle)
        return self._demarcation.transact(
            fn,
            owner=self,
            retries=retries,
            concurrency=concurrency,
            retry_optimistic_conflicts=retry_optimistic_conflicts,
            isolation=isolation,
        )


# The spec §8 module-level spelling of the composition-root entry point.
connect = Database.connect
