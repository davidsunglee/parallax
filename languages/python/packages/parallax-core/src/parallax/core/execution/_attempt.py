from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from typing import Any

from parallax.core import deep_fetch
from parallax.core.db_port import DatabaseConnection
from parallax.core.entity import EntityRowCodec
from parallax.core.entity._layout import CatalogedModel
from parallax.core.execution._keyed_writes import (
    KeyedInsertSource,
    KeyedWriteSource,
    OpenedKeyedWrite,
    keyed_insert,
    keyed_write,
)
from parallax.core.execution._options import DatabaseOptions
from parallax.core.execution._predicate_writes import (
    acquire_coverage,
    buffer_predicate_instruction,
    buffer_target_instruction,
)
from parallax.core.execution._publication import SelectedReadModel, SelectedWriteModel
from parallax.core.execution._read_policy import (
    ReadInputs,
    read_graph,
    read_page,
    read_rows,
    validated,
)
from parallax.core.execution._write_lowering import lowered, stream_lowered
from parallax.core.execution_lifecycle import ReadInterface
from parallax.core.execution_lifecycle._activity import (
    INERT,
    ActivityTarget,
    DatabaseCallScope,
    InstalledLifecycle,
    JoinedInvocationActivity,
    ReadActivity,
    StreamActivity,
    StreamBatchActivity,
    TransactionAttemptActivity,
    WriteBatchActivity,
    refuse_reentry,
)
from parallax.core.metamodel import Metamodel
from parallax.core.object_query import ObjectQueryNode
from parallax.core.object_query._validated import ValidatedObjectQuery
from parallax.core.read_delivery import RowsResult
from parallax.core.read_delivery._page_reader import StreamPageResult
from parallax.core.read_delivery._paging import At, PagingPlan
from parallax.core.read_delivery._publication import Publication
from parallax.core.read_delivery._read_plan import ReadPlanner
from parallax.core.read_delivery._stream import StreamDelivery, check_batch_size
from parallax.core.sql_gen import LoweredStatement
from parallax.core.unit_work import (
    Clock,
    KeyedMutation,
    ReadOrigin,
    TransactionSettings,
    UnitOfWork,
    WriteBatchTrigger,
    allocated_keys,
    enforce_affected_rows,
    returns_rows,
)
from parallax.core.unit_work.instructions import PreparedPredicateWrite, PreparedTargetWrite
from parallax.core.unit_work.strategy import ActorIdentity
from parallax.core.unit_work.uow import DeferredBinder, UnitReport
from parallax.core.write_plan import WritePlan
from parallax.core.write_plan.plan import ExecutionUnit
from parallax.core.write_plan.steps import PlannedInsert
from parallax.core.write_plan.steps import PlannedWrite as PlannedStep

__all__ = ["Attempt"]


class Attempt:
    """One physical transaction attempt: its unit of work, its connection, the
    selection it adopted, its activity, its resolved options, and the Write
    Batch its current flush runs inside.

    Constructed inside the port's transaction callback, after the attempt
    adopted and opened: every execution field is set before the unit of work is
    constructed over this attempt's own flush methods, so neither a lifecycle
    factory nor a callback can observe a partially wired attempt. A retry
    constructs a fresh one; a joining call reuses the active attempt and never
    constructs another.

    It is the attempt's participating read as well as its write door. Every
    read here runs inside the unit of work's read gate, so pending writes reach
    the database before a read that must see them, and opens its activity as a
    child of this attempt on this attempt's connection. Every write admits into
    the one unit of work, so no two doors of one attempt can disagree about what
    it stores.
    """

    __slots__ = (
        "_activity",
        "_batch",
        "_connection",
        "_inputs",
        "_lifecycle",
        "_options",
        "_planner",
        "_read",
        "_uow",
        "_write",
    )

    def __init__(
        self,
        connection: DatabaseConnection,
        read: SelectedReadModel,
        write: SelectedWriteModel,
        activity: TransactionAttemptActivity,
        *,
        lifecycle: InstalledLifecycle | None,
        planner: ReadPlanner,
        options: DatabaseOptions,
        clock: Clock,
        actor: ActorIdentity,
    ) -> None:
        self._connection = connection
        self._read = read
        self._write = write
        self._activity = activity
        self._lifecycle = lifecycle
        self._planner = planner
        # The invocation's resolved record, shared by reference across every
        # attempt of the invocation: what a joining call is compared against,
        # and what a caller inspects, without ambient state on either path.
        self._options = options
        # One flush is ONE Write Batch however many statements its plan lowers
        # to. The unit of work announces a flush before planning it and hands
        # the finished plan over afterwards, so the batch opened by the first
        # call is the one the second runs under; a flush never nests.
        self._batch: WriteBatchActivity = INERT
        self._uow = UnitOfWork(
            settings=TransactionSettings(
                concurrency=options.concurrency,
                counts_unchanged_rows=connection.dialect.counts_unchanged_rows,
            ),
            clock=clock,
            meta=write.model.meta,
            flush_executor=self._execute_flush,
            write_batch_opening=self._open_write_batch,
            # The adopted selection's Write Planner: retained by this unit of
            # work for its life, and reused by every join into it rather than
            # re-adopted.
            planner=write.planner,
            actor_identity=actor,
            evidence_policy_for=write.evidence_policy_for,
        )
        self._inputs = ReadInputs(connection, self._uow.settings.concurrency, self._uow)

    @property
    def uow(self) -> UnitOfWork:
        return self._uow

    @property
    def edition(self) -> str:
        """The Model Edition this attempt adopted before its boundary opened."""
        return self._write.edition

    @property
    def options(self) -> DatabaseOptions:
        """The resolved options this attempt's invocation runs under."""
        return self._options

    @property
    def lifecycle(self) -> InstalledLifecycle | None:
        """The installed lifecycle every door of this attempt refuses re-entry on."""
        return self._lifecycle

    @property
    def model(self) -> CatalogedModel:
        """The cataloged model every write of this attempt names its Entities in."""
        return self._write.model

    @property
    def codec(self) -> EntityRowCodec:
        """The Entity Row Codec the adopted selection derives write rows through."""
        return self._write.codec

    def joined_invocation(self) -> JoinedInvocationActivity:
        """The activity a joining invocation runs inside, as a child of this attempt."""
        return self._activity.joined_invocation()

    # Reads.

    def read[Q, Eager](
        self,
        query: Q,
        /,
        *,
        convert_query: Callable[[Q], ObjectQueryNode],
        build_publication: Callable[[SelectedReadModel], Publication[ReadOrigin, Eager]],
    ) -> Eager:
        """One participating whole-result read, published through
        ``build_publication``.

        Re-entry is refused first, then the publication is built over this
        attempt's selection — where a selection that cannot publish the
        requested representation refuses — before the query is lowered, before
        the gate, and before the force-flush.
        """
        refuse_reentry(self._lifecycle)
        publication = build_publication(self._read)
        return read_graph(self, convert_query(query), publication, self._planner)

    def stream[Q, P: Publication[ReadOrigin, Any]](
        self,
        query: Q,
        batch_size: int,
        /,
        *,
        convert_query: Callable[[Q], ObjectQueryNode],
        build_publication: Callable[[SelectedReadModel], P],
        on_page_start: Callable[[deep_fetch.IncludeTree], None],
        on_release: Callable[[], None],
    ) -> StreamDelivery[Attempt, P]:
        """One participating streamed delivery, constructed and not yet entered.

        Re-entry is refused, then the query is lowered and the page size judged;
        nothing model-dependent happens before the delivery is entered.
        """
        refuse_reentry(self._lifecycle)
        node = convert_query(query)
        check_batch_size(batch_size)
        return StreamDelivery(
            node,
            self,
            build_publication,
            batch_size=batch_size,
            on_page_start=on_page_start,
            on_release=on_release,
        )

    def read_rows(self, node: ObjectQueryNode) -> RowsResult:
        """One participating row-form read; it records no observation."""
        refuse_reentry(self._lifecycle)
        return read_rows(self, node, self._planner)

    def begin(self) -> Attempt:
        """The read a participating delivery is begun as: this attempt itself."""
        return self

    def validated(self, read: Attempt, node: ObjectQueryNode, /) -> ValidatedObjectQuery:
        return validated(read, node)

    def page(
        self,
        read: Attempt,
        paging: PagingPlan,
        at: At,
        batch: StreamBatchActivity,
        /,
        *,
        scanned: bool,
    ) -> StreamPageResult[ReadOrigin]:
        return read_page(read, paging, at, batch, self._planner, scanned=scanned)

    @property
    def selected(self) -> SelectedReadModel:
        return self._read

    @property
    def meta(self) -> Metamodel:
        return self._read.model.meta

    def open_stream(
        self, target: ActivityTarget, interface: ReadInterface, batch_size: int, /
    ) -> StreamActivity:
        return self._activity.stream(target, interface, batch_size)

    def release(self, failure: BaseException | None, /) -> None:
        """Nothing: participating work never checked anything out.

        The attempt owns the connection for its whole life, and a stream inside
        it is one more thing running on that connection rather than a second
        borrower of it.
        """
        del failure

    def advance[T](self, body: Callable[[], T], /) -> T:
        """Run ``body`` unwrapped: a participating failure propagates to the
        invocation, which names the attempt's edition once."""
        return body()

    def eager[T](
        self,
        target: ActivityTarget,
        interface: ReadInterface,
        body: Callable[[ReadActivity, ReadInputs], T],
        /,
    ) -> T:
        """Run ``body`` inside the read gate, so pending writes flush first.

        The activity opens INSIDE that flush, which is what makes the
        dependency batch the read forces out an ordered SIBLING of it under the
        same attempt rather than a scope containing it
        (`m-execution-lifecycle`).
        """
        return self._uow.read(lambda: self._inside_read(target, interface, body))

    def _inside_read[T](
        self,
        target: ActivityTarget,
        interface: ReadInterface,
        body: Callable[[ReadActivity, ReadInputs], T],
    ) -> T:
        with self._activity.read(target, interface) as read:
            return body(read, self._inputs)

    def paged[T](
        self, batch: StreamBatchActivity, body: Callable[[DatabaseCallScope, ReadInputs], T], /
    ) -> T:
        """Run one page's ``body`` inside the read gate and inside ``batch``,
        so read-your-own-writes holds at every page."""
        return self._uow.read(lambda: self._inside_page(batch, body))

    def _inside_page[T](
        self, batch: StreamBatchActivity, body: Callable[[DatabaseCallScope, ReadInputs], T]
    ) -> T:
        with batch as calls:
            return body(calls, self._inputs)

    # Writes.

    def keyed_write(
        self,
        source: KeyedWriteSource,
        mutation: KeyedMutation,
        /,
        *,
        until: dt.datetime | None = None,
    ) -> None:
        """Run one keyed write over existing state in the Keyed Write
        Validation Order."""
        keyed_write(self._write.model, self._uow, self._lifecycle, source, mutation, until=until)

    def keyed_insert(
        self,
        source: KeyedInsertSource,
        mutation: KeyedMutation,
        /,
        *,
        valid_from: dt.datetime | None = None,
        until: dt.datetime | None = None,
    ) -> OpenedKeyedWrite:
        """Open a row through the insert's own door, answering the authority
        its admission granted."""
        return keyed_insert(
            self._write.model,
            self._uow,
            self._lifecycle,
            source,
            mutation,
            valid_from=valid_from,
            until=until,
        )

    def predicate_write(self, prepared: PreparedPredicateWrite, /) -> None:
        """Buffer a prepared predicate-selected write, readless or
        materializing through a Read of its own under this attempt."""
        buffer_predicate_instruction(
            self._write.model, self._uow, self._connection, self._activity, prepared
        )

    def target_write(self, prepared: PreparedTargetWrite, /) -> None:
        """Buffer a prepared caller-addressed write, reading the state it starts
        from where its Effective Concurrency Strategy needs participation."""
        buffer_target_instruction(
            self._write.model, self._uow, self._connection, self._activity, prepared
        )

    # Flush execution.

    def _open_write_batch(self, trigger: WriteBatchTrigger, /) -> WriteBatchActivity:
        """The scope one flush of this attempt's buffer runs inside.

        The unit of work enters it before planning and leaves it when the flush
        is over, so a planning refusal is a failed batch rather than work outside
        every batch, and a batch planning reduces to no DML at all still
        completes.
        """
        batch = self._activity.write_batch(trigger)
        self._batch = batch
        return batch

    def _execute_flush(
        self,
        plan: WritePlan,
        /,
        *,
        trigger: WriteBatchTrigger,
        bind_deferred: DeferredBinder,
        completed: UnitReport,
    ) -> None:
        """Lower each planned step, execute every statement in order, hand each
        result back to the unit of work to interpret, and report each execution
        unit to it as soon as that unit's last step has been enforced.

        The single write-lowering seam (:func:`stream_lowered`) run on the
        transaction's own connection, inside the still-open ``port.transaction``
        scope — so an abort rolls back force-flushed writes with everything else.
        Every step lowers to exactly one statement, and a temporal mutation's
        effect on its predecessor precedes the rows it opens, so a failure there
        aborts BEFORE those rows ever execute. A unit is reported before any
        step of the next one runs, so what it changed is published before later
        work proceeds.

        A unit with a deferred range reaches its turn with no planned step: its
        coverage is read first (:func:`acquire_coverage`), the unit of work
        binds the range to it (``bind_deferred``), and the bound steps execute
        and are enforced exactly as planned ones are before the unit is
        reported with what it bound.

        This performs NO classification of its own: the adopted Write Planner
        already spent the concurrency mode while settling each step, and this
        reports only the driver's count to
        :func:`~parallax.core.unit_work.enforce_affected_rows`, which owns the
        authoritative reading of the step's Affected Rows Policy (ADR 0048).
        That enforcement runs inside its own attribution bracket, because a
        shortfall is judged AFTER the call it judges has already completed: the
        bracket is what lets the batch's failure name that completed call
        instead of the enforcement being read as a failure of the batch itself.

        An insert whose key the database allocates for a row the unit records
        answers that key: it runs as row-producing DML, core reads the key from
        the rows it returned (:func:`~parallax.core.unit_work.allocated_keys`)
        inside the same bracket, and the unit is reported with it.
        """
        # The trigger is the batch's, and the batch this runs inside already
        # carries it; taking it again here would be a second spelling of one
        # fact.
        del trigger
        meta = self._write.model.meta
        dialect = self._connection.dialect
        units = iter(plan.units)
        unit = next(units, None)
        executed = 0
        allocated: tuple[object, ...] = ()
        for step, statement in stream_lowered(plan, meta, dialect):
            while unit is not None and unit.end == executed:
                self._complete(unit, bind_deferred, completed, allocated)
                allocated = ()
                unit = next(units, None)
            if unit is not None and unit.opened.allocated and returns_rows(step):
                allocated = (*allocated, *self._run_returning(step, statement))
            else:
                self._run(step, statement)
            executed += 1
        while unit is not None and unit.end == executed:
            self._complete(unit, bind_deferred, completed, allocated)
            allocated = ()
            unit = next(units, None)

    def _complete(
        self,
        unit: ExecutionUnit,
        bind_deferred: DeferredBinder,
        completed: UnitReport,
        allocated: tuple[object, ...],
    ) -> None:
        deferred = unit.deferred
        if deferred is None:
            completed(unit, None, allocated=allocated)
            return
        model = self._write.model
        rows = acquire_coverage(model, self._connection, self._batch, deferred.acquisition)
        bound = bind_deferred(deferred, rows)
        meta = model.meta
        dialect = self._connection.dialect
        for step in bound.steps:
            self._run(step, lowered(step, meta, dialect))
        completed(unit, bound)

    def _run(self, step: PlannedStep, statement: LoweredStatement) -> None:
        batch = self._batch
        connection = self._connection
        with batch.database_call(statement, "write", step.entity) as call:
            affected = connection.execute_write(
                connection.dialect.to_driver_sql(statement.sql), list(statement.binds)
            )
            call.write_completed(affected)
        with batch.enforcing(call):
            enforce_affected_rows(step, affected)

    def _run_returning(
        self, step: PlannedInsert, statement: LoweredStatement
    ) -> tuple[object, ...]:
        batch = self._batch
        connection = self._connection
        with batch.database_call(statement, "write", step.entity) as call:
            rows = connection.execute(
                connection.dialect.to_driver_sql(statement.sql), list(statement.binds)
            )
            call.write_rows_completed(rows)
        with batch.enforcing(call):
            return allocated_keys(step, rows)
