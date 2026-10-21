from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Mapping, Set
from dataclasses import dataclass
from typing import Any, Literal, Protocol, Self, cast

from parallax.core import deep_fetch
from parallax.core._execution._family import entity_layout
from parallax.core._execution._keyed_writes import (
    KeyedInsertSource,
    KeyedWriteSource,
    OpenedKeyedWrite,
    keyed_insert,
    keyed_write,
    stated_valid_from,
    target_revision_arguments,
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
    TargetReadRequest,
)
from parallax.core._execution._unit_work.clock import Clock
from parallax.core._execution._unit_work.instructions import (
    KeyedMutation,
    PredicateMutation,
    PreparedPredicateWrite,
    TargetMutation,
    TargetWriteInstruction,
    prepare_typed_write,
    prepare_wire_write,
)
from parallax.core._execution._unit_work.retain import ReadEvidence
from parallax.core._execution._unit_work.strategy import ActorIdentity
from parallax.core._execution._unit_work.uow import (
    Concurrency,
    FlushTrigger,
    TransactionSettings,
    UnitOfWork,
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
    FlushActivity,
    InstalledLifecycle,
    JoinedInvocationActivity,
    ReadActivity,
    StreamActivity,
    StreamBatchActivity,
    TransactionAttemptActivity,
    refuse_reentry,
)
from parallax.core.metamodel import Metamodel
from parallax.core.object_query import ObjectQueryNode
from parallax.core.object_query._resolved import ResolvedObjectQuery
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
from parallax.core.write_plan.payload import PatchedDocument
from parallax.core.write_plan.steps import (
    PlannedDelete,
    PlannedStep,
    PlannedTemporalRevision,
    PlannedUpdate,
    WriteRow,
)

__all__ = [
    "PredicateWriteAdapter",
    "ReadOnlyTxnAttempt",
    "TargetWriteAdapter",
    "TargetWriteInput",
    "TxnAttempt",
    "WriteVerb",
]


class PredicateWriteAdapter(Protocol):
    """A representation's predicate-selected write, inert until the attempt asks
    for it.

    Constructed around the caller's original selection and payload, judging
    nothing, so no representation refusal precedes the attempt's re-entry
    check. :meth:`prepare` is asked once, after it: it captures that input,
    authors the canonical instruction, and returns what the one write
    preparation produced for it, borrowing ``write_model`` for the call alone.
    """

    def prepare(
        self, write_model: SelectedWriteModel, mutation: PredicateMutation
    ) -> PreparedPredicateWrite: ...


WriteVerb = Literal["amend", "replace", "delete", "terminate"]
"""The base verb a write over an existing object states, before its ``until``
selects the bounded form."""


@dataclass(frozen=True, slots=True)
class TargetWriteInput:
    """What a representation answers about one target write: the Entity
    spelling, the row naming the object beside the members it states, which
    leaf converter judges its values, and the members preparation judges as
    assignments — named outright, or produced once the write is admitted.
    The attempt states every other part of the canonical instruction."""

    entity: str
    row: Mapping[str, object]
    representation: Literal["typed", "wire"]
    authored_members: Set[str] | None = None
    members: Callable[[], Mapping[str, object]] | None = None


class TargetWriteAdapter(Protocol):
    """A representation's target write, inert until the attempt asks for it.

    Constructed around the caller's original addressed input, judging nothing,
    so no representation refusal precedes the attempt's re-entry and
    stated-start checks. :meth:`write_input` is asked once, after both: it
    captures that input and judges its shape, borrowing ``write_model`` for
    the call alone. No source evidence, pin, provenance, or insertion
    authority admits the write.
    """

    def write_input(
        self, write_model: SelectedWriteModel, mutation: TargetMutation
    ) -> TargetWriteInput: ...


def _window_mutation[M: KeyedMutation](
    unbounded: M, bounded: M, until: dt.datetime | Omitted
) -> tuple[M, dt.datetime | None]:
    """The token a caller's ``until`` selects, beside the bound it carries.

    Omission selects the unbounded token; any stated argument selects the
    bounded one with that argument as its bound, ``None`` included, so
    preparation refuses a missing bound rather than reading it as omission.
    """
    if isinstance(until, Omitted):
        return unbounded, None
    return bounded, until


def _bounded_mutation(
    verb: WriteVerb, until: dt.datetime | Omitted
) -> tuple[TargetMutation, dt.datetime | None]:
    """The instruction token and bound a base verb and its ``until`` select."""
    if verb == "amend":
        return _window_mutation("amend", "amendUntil", until)
    if verb == "replace":
        return _window_mutation("replace", "replaceUntil", until)
    if verb == "terminate":
        return _window_mutation("terminate", "terminateUntil", until)
    # Deletion has no bounded form, so a stated bound reaches preparation beside
    # the unbounded verb, which refuses it.
    return _window_mutation("delete", "delete", until)


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
        dependency flush a writable attempt's admission forces out an ordered
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
    and the Flush activity of its current flush.

    Constructed inside the port's transaction callback, after the attempt
    adopted and opened: every execution field is set before the unit of work is
    constructed over this attempt's own step-execution, flush, and
    row-acquisition methods, so neither a lifecycle factory nor a callback can
    observe a partially wired attempt. A retry constructs a fresh one; a joining
    call reuses the active attempt and never constructs another.

    It is the attempt's participating read as well as its write door. Every
    read is admitted through the unit of work's read gate, so pending writes
    reach the database before a read that must see them. Every write admits
    into the one unit of work, so no two doors of one attempt can disagree
    about what it stores.
    """

    __slots__ = ("_flush", "_options", "_step_executor", "_uow", "_write")

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
        # through this one executor, handing it that flush's own activity.
        self._step_executor = WriteStepExecutor(
            connection, payloads=write.planner.payloads, meta=write.model.meta
        )
        # The invocation's resolved record, shared by reference across every
        # attempt of the invocation: what a joining call is compared against,
        # and what a caller inspects, without ambient state on either path.
        self._options = options
        # One flush is ONE Flush activity however many statements its plan
        # lowers to. The unit of work opens it before planning and executes
        # every Write Group of the plan inside it, and a predicate-selected
        # write's own statement after them, so each step runs under the
        # activity its flush opened; a flush never nests.
        self._flush: FlushActivity = INERT
        self._uow = UnitOfWork(
            settings=TransactionSettings(
                concurrency=options.concurrency,
                counts_unchanged_rows=connection.dialect.counts_unchanged_rows,
            ),
            lifetime=lifetime,
            clock=clock,
            meta=write.model.meta,
            execute_write_steps=self._execute_write_steps,
            execute_counted_step=self._execute_counted_step,
            flush_opening=self._open_flush,
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
        """Flush what is still buffered as the boundary's pre-commit flush, while
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
        verb: WriteVerb,
        /,
        *,
        until: dt.datetime | Omitted = OMITTED,
    ) -> None:
        """Run one keyed write over existing state in the Keyed Write
        Validation Order, its ``until`` selecting the bounded verb as
        :meth:`target_write`'s does."""
        mutation, bound = _bounded_mutation(verb, until)
        keyed_write(self._write.model, self._uow, self._lifecycle, source, mutation, until=bound)

    def keyed_insert(
        self,
        source: KeyedInsertSource,
        /,
        *,
        valid_from: dt.datetime | Omitted = OMITTED,
        until: dt.datetime | Omitted = OMITTED,
    ) -> OpenedKeyedWrite:
        """Open a row through the insert's own door, answering the authority
        its admission granted; a stated ``until``, ``None`` included, selects
        the bounded insert."""
        mutation, bound = _window_mutation("insert", "insertUntil", until)
        return keyed_insert(
            self._write.model,
            self._uow,
            self._lifecycle,
            source,
            mutation,
            valid_from=valid_from,
            until=bound,
        )

    def predicate_write(
        self, adapter: PredicateWriteAdapter, mutation: PredicateMutation, /
    ) -> int:
        """Run one predicate-selected write in its ingress order, then execute
        it readless, answering the affected-row count its statement reported.

        Re-entry is refused first, and only then is ``adapter`` asked to
        prepare the write under this attempt's write projection: the target's
        kind, the predicate, the family, and the payload are preparation's
        to judge. Only a prepared write executes, together with what is
        buffered before it
        (:meth:`~parallax.core._execution._unit_work.uow.UnitOfWork.execute_predicate`).
        """
        refuse_reentry(self._lifecycle)
        return self._uow.execute_predicate(adapter.prepare(self._write, mutation))

    def target_write(
        self,
        adapter: TargetWriteAdapter,
        verb: WriteVerb,
        /,
        *,
        version: object = OMITTED,
        tx_start: object = OMITTED,
        valid_from: dt.datetime | Omitted = OMITTED,
        until: dt.datetime | Omitted = OMITTED,
    ) -> None:
        """Run one target write in its ingress order, then
        buffer it, reading the state it starts from where its Effective
        Concurrency Strategy needs participation.

        Re-entry is refused first, then a stated start judged, and only then is
        ``adapter`` asked for its input under this attempt's write projection.
        The canonical instruction states that input under the caller's
        revision and window, and the target, the window, the revision, and the
        payload are preparation's to judge. A stated ``until``, ``None``
        included, selects the bounded verb, and every revision keyword stated,
        ``None`` included, reaches preparation as stated.
        """
        refuse_reentry(self._lifecycle)
        start = stated_valid_from(valid_from)
        mutation, bound = _bounded_mutation(verb, until)
        revision = target_revision_arguments(version=version, tx_start=tx_start)
        write = adapter.write_input(self._write, mutation)
        instruction = TargetWriteInstruction(
            mutation,
            write.entity,
            write.row,
            revision.if_version,
            revision.if_tx_start,
            start,
            bound,
            revision.stated,
        )
        prepare = prepare_typed_write if write.representation == "typed" else prepare_wire_write
        self._uow.buffer_target(
            prepare(
                instruction,
                self._write.model.meta,
                authored_members=write.authored_members,
                members=write.members,
            )
        )

    # Row acquisition.

    def _acquire_rows[Request: RowRequest, Result](
        self, request: Request, consumer: RowConsumer[Request, Result], /
    ) -> Result:
        """Read the rows ``request`` names on this attempt's connection and hand
        them to ``consumer``, executing no pending write and publishing nothing.

        A target read is a Read of its own under this attempt
        (`m-execution-lifecycle`: every statement-reaching operation belongs to
        exactly one Read, Flush, or Stream Batch), spanning its planning,
        lowering, and the consumer, so a compile refusal or a root holding
        invalid stored data is a FAILED Read rather than work outside every
        activity. Its lock suffix derives from the target Entity's Effective
        Concurrency Strategy through the same seam a participating find takes.
        A coverage read runs while a flush is reaching a deferred range, so it
        is a read call of that flush's Flush activity, under the shared row lock
        where its range protects every affected row with one.

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
            return self._consume(self._coverage_read(request), self._flush, request, consumer)
        with self._activity.read(request.entity.identity, "rows") as read:
            return self._consume(self._target_read(request), read, request, consumer)

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

    def _target_read(self, request: TargetReadRequest) -> CompiledRead:
        """The point read of the row a target write starts from: the
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

    def _open_flush(self, trigger: FlushTrigger, /) -> FlushActivity:
        """The scope one flush of this attempt's buffer runs inside.

        The unit of work enters it before planning and leaves it when the flush
        is over, so a planning refusal is a failed Flush rather than work outside
        every Flush, and a Flush planning reduces to no DML at all still
        completes.
        """
        flush = self._activity.flush(trigger)
        self._flush = flush
        return flush

    def _execute_counted_step(self, step: PlannedUpdate | PlannedDelete, /) -> int:
        """Execute ``step`` as one call of the current flush's Flush activity,
        answering its affected-row count."""
        return self._step_executor.execute_with_count(step, flush=self._flush)

    def _execute_write_steps(
        self,
        steps: tuple[PlannedStep, ...],
        /,
        *,
        allocates: bool,
        capture_insert: Callable[[WriteRow, object | None], None] | None = None,
        capture_revision: Callable[[PlannedTemporalRevision, PatchedDocument | None], None]
        | None = None,
    ) -> tuple[object, ...]:
        """Execute ``steps`` as calls of the current flush's Flush activity,
        handing their demanded payloads to the capture hooks the unit of work
        gives."""
        executor = self._step_executor
        if capture_insert is None and capture_revision is None:
            return executor.execute(steps, allocates=allocates, flush=self._flush)
        return executor.execute(
            steps,
            allocates=allocates,
            flush=self._flush,
            capture_insert=capture_insert,
            capture_revision=capture_revision,
        )
