from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from typing import Any, Literal, Protocol, Self, cast, overload

from parallax.core import deep_fetch, inheritance
from parallax.core._execution._family import entity_layout
from parallax.core._execution._keyed_writes import (
    KeyedInsertSource,
    KeyedWriteSource,
    OpenedKeyedWrite,
    TargetRevisionArguments,
    keyed_insert,
    keyed_write,
    stated_valid_from,
    target_revision_arguments,
    window_mutation,
)
from parallax.core._execution._options import OMITTED, Omitted, ReadOnlyTxnOptions, TxnOptions
from parallax.core._execution._publication import SelectedReadModel, SelectedWriteModel
from parallax.core._execution._read_policy import (
    ReadInputs,
    ReadQuery,
    read_graph,
    read_page,
    read_rows,
    resolved,
)
from parallax.core._execution._transaction._lifetime import TxnAttemptLifetime
from parallax.core._execution._unit_work.acquisition import (
    CompletionRequest,
    CoverageReadRequest,
    RowConsumer,
    RowReadRequest,
    RowRequest,
    SelectionReadRequest,
    TargetReadRequest,
)
from parallax.core._execution._unit_work.clock import Clock
from parallax.core._execution._unit_work.instructions import (
    KeyedMutation,
    PredicateMutation,
    PreparedPredicateWrite,
    PreparedTargetWrite,
    TargetMutation,
)
from parallax.core._execution._unit_work.retain import ReadEvidence
from parallax.core._execution._unit_work.strategy import ActorIdentity
from parallax.core._execution._unit_work.uow import (
    Concurrency,
    TransactionSettings,
    UnitOfWork,
    WriteBatchReason,
)
from parallax.core._execution._write_step_executor import WriteStepExecutor
from parallax.core.base import ManagedValue
from parallax.core.db_port import DatabaseConnection
from parallax.core.deep_fetch import PlannedEntityQuery
from parallax.core.dialect import LockMode
from parallax.core.entity import EntityRowCodec
from parallax.core.entity._layout import CatalogedModel
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
from parallax.core.object_query._resolved import (
    ResolvedObjectQuery,
    latest_temporal_selections,
    selections_at_valid_time,
)
from parallax.core.read_delivery import RowsResult
from parallax.core.read_delivery._fetch import entity_read_lock, execute_read
from parallax.core.read_delivery._page import ABSENT, release_page_rows
from parallax.core.read_delivery._page_reader import FlatPageRequest, PageReader, StreamPageResult
from parallax.core.read_delivery._paging import At, PagingPlan
from parallax.core.read_delivery._publication import Publication
from parallax.core.read_delivery._read_plan import ReadPlanner
from parallax.core.read_delivery._row_lane import (
    admitted_member_rows,
    completed_member_row,
    publishable_member_rows,
)
from parallax.core.read_delivery._stream import StreamDelivery, check_batch_size
from parallax.core.sql_gen._compile import CompiledRead, compile_read
from parallax.core.temporal_read import Pin
from parallax.core.write_plan.plan import WriteStepView

__all__ = [
    "PredicateWriteAdapter",
    "PredicateWriteVerb",
    "ReadOnlyTxnAttempt",
    "TargetWriteAdapter",
    "TargetWriteVerb",
    "TxnAttempt",
]


PredicateWriteVerb = Literal["amend", "delete", "terminate"]
"""The intent a predicate-selected write states: the base verb, never its
bounded token, which the attempt selects from the caller's ``until``."""


class PredicateWriteAdapter(Protocol):
    """A representation's predicate-selected write, inert until the attempt asks
    for it.

    Constructed around the caller's original selection and assignments, judging
    nothing, so no representation refusal precedes the attempt's re-entry and
    stated-start checks. :meth:`prepare` is asked once, after both: it captures
    that input, authors the canonical instruction, and returns what the one
    write preparation produced for it, borrowing ``write_model`` for the call
    alone.
    """

    def prepare(
        self,
        write_model: SelectedWriteModel,
        mutation: PredicateMutation,
        *,
        valid_from: dt.datetime | None,
        until: dt.datetime | None,
    ) -> PreparedPredicateWrite: ...


TargetWriteVerb = Literal["amend", "replace", "delete", "terminate"]
"""The intent a caller-addressed conditional write states: the base verb,
never its bounded token, which the attempt selects from the caller's
``until``."""


class TargetWriteAdapter(Protocol):
    """A representation's caller-addressed conditional write, inert until the
    attempt asks for it.

    Constructed around the caller's original addressed input, judging nothing,
    so no representation refusal precedes the attempt's re-entry and
    stated-start checks. :meth:`prepare` is asked once, after both, with the
    caller's revision keywords encoded but unjudged: it captures that input,
    authors the canonical instruction under ``revision_arguments``, and returns
    what the one write preparation produced for it, borrowing ``write_model``
    for the call alone. No source evidence, pin, provenance, or insertion
    authority admits the write.
    """

    def prepare(
        self,
        write_model: SelectedWriteModel,
        mutation: TargetMutation,
        revision_arguments: TargetRevisionArguments,
        *,
        valid_from: dt.datetime | None,
        until: dt.datetime | None,
    ) -> PreparedTargetWrite: ...


@overload
def _bounded_mutation(
    verb: PredicateWriteVerb, until: dt.datetime | Omitted
) -> tuple[PredicateMutation, dt.datetime | None]: ...
@overload
def _bounded_mutation(
    verb: TargetWriteVerb, until: dt.datetime | Omitted
) -> tuple[TargetMutation, dt.datetime | None]: ...
def _bounded_mutation(
    verb: TargetWriteVerb, until: dt.datetime | Omitted
) -> tuple[TargetMutation, dt.datetime | None]:
    """The instruction token and bound a base verb and its ``until`` select."""
    if verb == "amend":
        return window_mutation("amend", "amendUntil", until)
    if verb == "replace":
        return window_mutation("replace", "replaceUntil", until)
    if verb == "terminate":
        return window_mutation("terminate", "terminateUntil", until)
    # Deletion has no bounded form, so a stated bound reaches preparation beside
    # the unbounded verb, which refuses it.
    return window_mutation("delete", "delete", until)


class _TxnAttemptBase:
    """What every transaction attempt shares, whatever it may do: its
    connection, the read projection it adopted, its activity, and the lifetime
    the runner created for it — and the participating reads served on them.

    Private implementation reuse, not a mode of its own: :class:`TxnAttempt`
    and :class:`ReadOnlyTxnAttempt` are the two concrete attempts. Every read
    here opens its activity as a child of this attempt, on this attempt's
    connection, inside :meth:`_admit_read`, which refuses work the lifetime no
    longer admits; a writable attempt admits through its unit of work's read
    gate instead.
    """

    __slots__ = (
        "_activity",
        "_connection",
        "_inputs",
        "_lifecycle",
        "_lifetime",
        "_planner",
        "_read",
    )

    def __init__(
        self,
        connection: DatabaseConnection,
        read: SelectedReadModel,
        activity: TransactionAttemptActivity,
        *,
        lifecycle: InstalledLifecycle | None,
        planner: ReadPlanner,
        lifetime: TxnAttemptLifetime,
    ) -> None:
        self._connection = connection
        self._read = read
        self._activity = activity
        self._lifecycle = lifecycle
        self._planner = planner
        self._lifetime = lifetime
        # What every read of this attempt executes with; each concrete attempt
        # states its own before the attempt is handed to anyone.
        self._inputs: ReadInputs

    @property
    def lifetime(self) -> TxnAttemptLifetime:
        return self._lifetime

    @property
    def edition(self) -> str:
        """The Model Edition this attempt adopted before its boundary opened."""
        return self._read.edition

    @property
    def lifecycle(self) -> InstalledLifecycle | None:
        """The installed lifecycle every door of this attempt refuses re-entry on."""
        return self._lifecycle

    def joined_invocation(self) -> JoinedInvocationActivity:
        """The activity a joining invocation runs inside, as a child of this attempt."""
        return self._activity.joined_invocation()

    def complete(self) -> None:
        """The work an attempt does once its callback returned and before its
        boundary commits: none here."""

    def discard(self) -> None:
        """Drop what an attempt that will not commit holds: nothing here."""

    # Reads.

    def read[Q, Eager](
        self,
        query: Q,
        /,
        *,
        convert_query: Callable[[Q], ReadQuery],
        build_publication: Callable[[SelectedReadModel], Publication[ReadEvidence, Eager]],
    ) -> Eager:
        """One participating whole-result read, published through
        ``build_publication``.

        Re-entry is refused first, then the publication is built over this
        attempt's selection — where a selection that cannot publish the
        requested representation refuses — before the query is captured, before
        the gate resolves it under that selection, and before the read is
        admitted.
        """
        refuse_reentry(self._lifecycle)
        publication = build_publication(self._read)
        return read_graph(self, convert_query(query), publication, self._planner)

    def stream[Q, P: Publication[ReadEvidence, Any]](
        self,
        query: Q,
        batch_size: int,
        /,
        *,
        convert_query: Callable[[Q], ReadQuery],
        build_publication: Callable[[SelectedReadModel], P],
        on_page_start: Callable[[deep_fetch.IncludeTree], None],
        on_release: Callable[[], None],
    ) -> StreamDelivery[Self, ReadQuery, P]:
        """One participating streamed delivery, constructed and not yet entered.

        Re-entry is refused, then the query is captured and the page size judged;
        nothing model-dependent happens before the delivery is entered. Each
        page is admitted on its own, so a stream that outlived its attempt
        reads nothing more.
        """
        refuse_reentry(self._lifecycle)
        read_query = convert_query(query)
        check_batch_size(batch_size)
        return StreamDelivery(
            read_query,
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

    def begin(self) -> Self:
        """The read a participating delivery is begun as: this attempt itself."""
        return self

    def resolved(self, read: Self, query: ReadQuery, /) -> ResolvedObjectQuery:
        return resolved(read, query)

    def page(
        self,
        read: Self,
        paging: PagingPlan,
        at: At,
        batch: StreamBatchActivity,
        /,
        *,
        scanned: bool,
    ) -> StreamPageResult[ReadEvidence]:
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
        """Run ``body`` once the read is admitted, inside its own activity.

        The activity opens INSIDE the admission, which is what makes a
        dependency batch a writable attempt's admission forces out an ordered
        SIBLING of the read under the same attempt rather than a scope
        containing it (`m-execution-lifecycle`).
        """
        return self._admit_read(lambda: self._inside_read(target, interface, body))

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
        """Run one page's ``body`` once the page is admitted, inside ``batch``,
        so every page meets the admission a whole read does."""
        return self._admit_read(lambda: self._inside_page(batch, body))

    def _inside_page[T](
        self, batch: StreamBatchActivity, body: Callable[[DatabaseCallScope, ReadInputs], T]
    ) -> T:
        with batch as calls:
            return body(calls, self._inputs)

    def _admit_read[T](self, body: Callable[[], T], /) -> T:
        """Run ``body`` as one read of this attempt, once its lifetime admits work."""
        self._lifetime.ensure_open()
        return body()


class ReadOnlyTxnAttempt(_TxnAttemptBase):
    """One physical read-only transaction attempt: the shared reads, and
    nothing that writes.

    Its reads pass no Concurrency Preference and no evidence context, so they
    take no participation lock — the unversioned fallback included — and
    retain no Read Evidence on what they publish. It owns no unit of work, write
    projection, planner, or write-only state. A retry constructs a fresh one;
    a joining call reuses the active one.
    """

    __slots__ = ("_options",)

    def __init__(
        self,
        connection: DatabaseConnection,
        read: SelectedReadModel,
        activity: TransactionAttemptActivity,
        *,
        lifecycle: InstalledLifecycle | None,
        planner: ReadPlanner,
        options: ReadOnlyTxnOptions,
        lifetime: TxnAttemptLifetime,
    ) -> None:
        super().__init__(
            connection, read, activity, lifecycle=lifecycle, planner=planner, lifetime=lifetime
        )
        self._inputs = ReadInputs(connection, None, None)
        # The invocation's resolved record, shared by reference across every
        # attempt of the invocation, as a writable attempt's is.
        self._options = options

    @property
    def options(self) -> ReadOnlyTxnOptions:
        """The resolved options this attempt's invocation runs under."""
        return self._options


class TxnAttempt(_TxnAttemptBase):
    """One physical writable transaction attempt: its unit of work, its
    connection, the selection it adopted, its activity, its resolved options,
    and the Write Batch its current flush runs inside.

    Constructed inside the port's transaction callback, after the attempt
    adopted and opened: every execution field is set before the unit of work is
    constructed over this attempt's own step-execution, write-batch, and
    row-acquisition methods, so neither a lifecycle factory nor a callback can
    observe a partially wired attempt. A retry constructs a fresh one; a joining
    call reuses the active attempt and never constructs another.

    It is the attempt's participating read as well as its write door. Every
    read is admitted through the unit of work's read gate, so pending writes
    reach the database before a read that must see them. Every write admits
    into the one unit of work, so no two doors of one attempt can disagree
    about what it stores.
    """

    __slots__ = ("_batch", "_options", "_step_executor", "_uow", "_write")

    def __init__(
        self,
        connection: DatabaseConnection,
        read: SelectedReadModel,
        write: SelectedWriteModel,
        activity: TransactionAttemptActivity,
        *,
        lifecycle: InstalledLifecycle | None,
        planner: ReadPlanner,
        options: TxnOptions,
        clock: Clock,
        actor: ActorIdentity,
        lifetime: TxnAttemptLifetime,
    ) -> None:
        super().__init__(
            connection, read, activity, lifecycle=lifecycle, planner=planner, lifetime=lifetime
        )
        self._write = write
        # Every flush of this attempt executes its steps on this connection
        # through this one executor, handing it the flush's own Write Batch.
        self._step_executor = WriteStepExecutor(
            connection, payloads=write.planner.payloads, meta=write.model.meta
        )
        # The invocation's resolved record, shared by reference across every
        # attempt of the invocation: what a joining call is compared against,
        # and what a caller inspects, without ambient state on either path.
        self._options = options
        # One flush is ONE Write Batch however many statements its plan lowers
        # to. The unit of work opens it before planning and executes every span
        # of the plan inside it, so each span runs under the batch its flush
        # opened; a flush never nests.
        self._batch: WriteBatchActivity = INERT
        self._uow = UnitOfWork(
            settings=TransactionSettings(
                concurrency=options.concurrency,
                counts_unchanged_rows=connection.dialect.counts_unchanged_rows,
            ),
            lifetime=lifetime,
            clock=clock,
            meta=write.model.meta,
            execute_write_steps=self._execute_steps,
            write_batch_opening=self._open_write_batch,
            acquire_rows=self._acquire_rows,
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
    def options(self) -> TxnOptions:
        """The resolved options this attempt's invocation runs under."""
        return self._options

    @property
    def model(self) -> CatalogedModel:
        """The cataloged model every write of this attempt names its Entities in."""
        return self._write.model

    @property
    def codec(self) -> EntityRowCodec:
        """The Entity Row Codec the adopted selection derives write rows through."""
        return self._write.codec

    def complete(self) -> None:
        """Flush what is still buffered as the boundary's pre-commit batch, while
        the lifetime still admits work."""
        self._uow.flush(trigger="pre_commit")

    def discard(self) -> None:
        """Drop the buffered and in-memory writable state of an attempt that
        will not commit."""
        self._uow.discard()

    def _admit_read[T](self, body: Callable[[], T], /) -> T:
        """Admit ``body`` through the unit of work's read gate, which consults
        the same lifetime and flushes pending writes first, so a read observes
        this attempt's own writes."""
        return self._uow.read(body)

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
        valid_from: dt.datetime | Omitted = OMITTED,
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

    def predicate_write(
        self,
        adapter: PredicateWriteAdapter,
        verb: PredicateWriteVerb,
        /,
        *,
        valid_from: dt.datetime | Omitted = OMITTED,
        until: dt.datetime | Omitted = OMITTED,
    ) -> None:
        """Run one predicate-selected write in its ingress order, then buffer it
        readless or materializing through a Read of its own under this attempt.

        Re-entry is refused first, then a stated start judged, and only then is
        ``adapter`` asked to prepare the write under this attempt's write
        projection: the window and the predicate, the family, and the
        assignments are preparation's to judge. A stated ``until``, ``None``
        included, selects the bounded verb.
        """
        refuse_reentry(self._lifecycle)
        start = stated_valid_from(valid_from)
        mutation, bound = _bounded_mutation(verb, until)
        prepared = adapter.prepare(self._write, mutation, valid_from=start, until=bound)
        self._uow.buffer_predicate(prepared)

    def target_write(
        self,
        adapter: TargetWriteAdapter,
        verb: TargetWriteVerb,
        /,
        *,
        version: object = OMITTED,
        tx_start: object = OMITTED,
        valid_from: dt.datetime | Omitted = OMITTED,
        until: dt.datetime | Omitted = OMITTED,
    ) -> None:
        """Run one caller-addressed conditional write in its ingress order, then
        buffer it, reading the state it starts from where its Effective
        Concurrency Strategy needs participation.

        Re-entry is refused first, then a stated start judged, and only then is
        ``adapter`` asked to prepare the write under this attempt's write
        projection: the target, the window, the revision, and the payload are
        preparation's to judge. A stated ``until``, ``None`` included, selects
        the bounded verb, and every revision keyword stated, ``None`` included,
        reaches preparation as stated.
        """
        refuse_reentry(self._lifecycle)
        start = stated_valid_from(valid_from)
        mutation, bound = _bounded_mutation(verb, until)
        revision = target_revision_arguments(version=version, tx_start=tx_start)
        prepared = adapter.prepare(self._write, mutation, revision, valid_from=start, until=bound)
        self._uow.buffer_target(prepared)

    # Row acquisition.

    def _acquire_rows[Request: RowRequest, Result](
        self, request: Request, consumer: RowConsumer[Request, Result], /
    ) -> Result:
        """Read the rows ``request`` names on this attempt's connection and hand
        them to ``consumer``, executing no pending write and publishing nothing.

        A selection or target read is a Read of its own under this attempt
        (`m-execution-lifecycle`: every statement-reaching operation belongs to
        exactly one Read, Write Batch, or Stream Batch), spanning its planning,
        lowering, and the consumer, so a compile refusal or a root holding
        invalid stored data is a FAILED Read rather than work outside every
        activity. Its lock suffix derives from the target Entity's Effective
        Concurrency Strategy through the same seam a participating find takes.
        A coverage read runs while a flush is reaching a deferred range, so it
        is a read call of the Write Batch that flush runs inside, under the
        shared row lock where its range protects every affected row with one.

        Every read is row-form, over the target's own member selection: the
        identity under ``Columns`` layout and the document fan-out under
        Relational Document Layout, each raw Structured Column retained beside
        its row so evidence can carry the document the row actually held.

        A completion reads nothing and opens no activity: the rows a retaining
        target read left are judged where that read stopped, before any
        database work could begin.
        """
        if isinstance(request, CompletionRequest):
            return self._completed_rows(
                request, cast("RowConsumer[CompletionRequest, Result]", consumer)
            )
        if isinstance(request, CoverageReadRequest):
            return self._consume(self._coverage_read(request), self._batch, request, consumer)
        with self._activity.read(request.entity.identity, "rows") as read:
            compiled = (
                self._selection_read(request)
                if isinstance(request, SelectionReadRequest)
                else self._target_read(request)
            )
            return self._consume(compiled, read, request, consumer)

    def _completed_rows[Result](
        self, request: CompletionRequest, consumer: RowConsumer[CompletionRequest, Result]
    ) -> Result:
        """Run ``consumer`` over ``request``'s rows, each judged complete by the
        reader as it is asked for."""
        layout = self._write.model.layouts.entity(request.entity.identity)
        rows = request.rows
        return consumer(
            request,
            layout.member_selection,
            (completed_member_row(layout, row) for row in rows),
            ABSENT,
            request.documents,
            len(rows),
        )

    def _consume[Request: RowReadRequest, Result](
        self,
        compiled: CompiledRead,
        calls: DatabaseCallScope,
        request: Request,
        consumer: RowConsumer[Request, Result],
    ) -> Result:
        """Execute ``compiled`` as one flat Page and run ``consumer`` over its
        judged member rows, releasing the Page however the consumer left it —
        before starting the rows, part way through them, or by raising. A
        retaining target read's rows have only their Attributes judged."""
        model = self._write.model
        connection = self._connection
        layout = entity_layout(model.meta, request.entity)
        if layout is None:  # pragma: no cover - a write target always owns rows
            raise ValueError(f"{request.entity.identity.canonical}: write target has no Table")
        stage = PageReader().read_page(
            FlatPageRequest(
                model, compiled, lambda: execute_read(connection, compiled, calls), Pin()
            )
        )
        page = stage.page
        rows = (
            admitted_member_rows(page)
            if isinstance(request, TargetReadRequest) and request.retains
            else publishable_member_rows(page)
        )
        try:
            return consumer(
                request,
                layout.member_selection,
                rows,
                ABSENT,
                stage.documents if compiled.structured_column is not None else None,
                page.root_count,
            )
        finally:
            rows.close()
            release_page_rows(page)

    def _selection_read(self, request: SelectionReadRequest) -> CompiledRead:
        """The predicate's resolving read, at Latest on every declared temporal
        axis — or, where the request selects at a Valid-Time instant, as of that
        instant on Valid Time and Latest on Transaction Time: a
        mutation-compatible Object Query carries no as-of term, so the internal
        authoring boundary adds one per dimension and routes the read through
        the same root canonicalization every other read takes, rather than
        matching every historical milestone too.

        Its projection follows the evidence it becomes: a temporal target's
        rows are complete Predecessor Rows, so every declared document is
        projected whatever the verb does with it; a versioned target's are its
        key and version, so only the assigned documents its no-op elimination
        compares are."""
        meta = self._write.model.meta
        entity = request.entity
        predecessors = request.predecessors
        root = inheritance.root_metadata(inheritance.view(meta), meta, entity.identity)
        valid_from = request.valid_from
        query = deep_fetch.plan_mutation_read(
            request.write,
            model=meta,
            temporal=(
                latest_temporal_selections(root)
                if valid_from is None
                else selections_at_valid_time(root, valid_from)
            ),
            projection=deep_fetch.ReadProjectionRequest(
                "all" if predecessors else "none", predecessors
            ),
        )
        return self._row_read(query, entity_read_lock(meta, entity.identity, self._preference))

    def _target_read(self, request: TargetReadRequest) -> CompiledRead:
        """The point read of the row a caller-addressed write starts from: the
        current row at ``valid_from`` of a Bitemporal object, the current one of
        any other, read whole where the request retains it."""
        meta = self._write.model.meta
        entity = request.entity
        ((name, value),) = request.key.primary_key
        query = deep_fetch.plan_target_read(
            entity,
            model=meta,
            key=name,
            key_value=cast("ManagedValue", value),
            valid_from=request.valid_from,
            whole=request.retains,
        )
        return self._row_read(query, entity_read_lock(meta, entity.identity, self._preference))

    def _coverage_read(self, request: CoverageReadRequest) -> CompiledRead:
        query = deep_fetch.plan_coverage_read(
            request.entity,
            model=self._write.model.meta,
            key=request.key_attribute.name,
            terms=tuple((term.key_value, term.valid_time_windows) for term in request.terms),
        )
        return self._row_read(query, "locking" if request.locking else None)

    def _row_read(self, query: PlannedEntityQuery, lock: LockMode | None) -> CompiledRead:
        return compile_read(
            query, self._write.model.meta, self._connection.dialect, result_form="row", lock=lock
        )

    @property
    def _preference(self) -> Concurrency:
        return self._uow.settings.concurrency

    # Flush execution.

    def _open_write_batch(self, trigger: WriteBatchReason, /) -> WriteBatchActivity:
        """The scope one flush of this attempt's buffer runs inside.

        The unit of work enters it before planning and leaves it when the flush
        is over, so a planning refusal is a failed batch rather than work outside
        every batch, and a batch planning reduces to no DML at all still
        completes.
        """
        batch = self._activity.write_batch(trigger)
        self._batch = batch
        return batch

    def _execute_steps(self, steps: WriteStepView, /, *, allocates: bool) -> tuple[object, ...]:
        """Execute ``steps`` as calls of the Write Batch the current flush runs
        inside."""
        return self._step_executor.execute(steps, allocates=allocates, batch=self._batch)
