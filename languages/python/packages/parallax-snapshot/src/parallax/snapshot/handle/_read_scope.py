from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from parallax.core import deep_fetch
from parallax.core.db_port import DatabaseConnection
from parallax.core.execution._page_origins import ObservedPageProjections
from parallax.core.execution._retention import ObservationLedger
from parallax.core.execution_lifecycle import ReadInterface
from parallax.core.execution_lifecycle._activity import (
    ActivityTarget,
    DatabaseCallScope,
    InstalledLifecycle,
    ReadActivity,
    StreamActivity,
    StreamBatchActivity,
    TransactionAttemptActivity,
    open_read_root,
    open_stream_root,
    refuse_reentry,
)
from parallax.core.metamodel import Metamodel
from parallax.core.object_query import ObjectQueryNode, deserialize
from parallax.core.object_query._fluent import ObjectQuery, object_query_node
from parallax.core.object_query._validated import ValidatedObjectQuery
from parallax.core.read_delivery import RowsResult
from parallax.core.read_delivery._delivery import deliver_find, deliver_history
from parallax.core.read_delivery._page_reader import (
    EagerPageRequest,
    PageReader,
    StreamPageRequest,
    StreamPageResult,
)
from parallax.core.read_delivery._paging import At, PagingPlan
from parallax.core.read_delivery._publication import Publication
from parallax.core.read_delivery._read_plan import ReadPlanner
from parallax.core.read_delivery._row_lane import find_rows
from parallax.core.read_delivery._stream import StreamDelivery, StreamRead, check_batch_size
from parallax.core.temporal_read import scans_validated_axis
from parallax.core.unit_work import Concurrency, ReadOrigin, UnitOfWork

# Sibling implementation modules. None of these names carries a leading
# underscore, precisely because it crosses a module boundary: privacy is carried
# by the private MODULE names and by the package's frozen `__all__`, not by
# per-name underscores.
from parallax.snapshot.handle._adoption import AdoptedExecution
from parallax.snapshot.handle._concurrency import CONCURRENCY
from parallax.snapshot.handle._connection_lifecycle import (
    enter_connection,
    exit_connection,
)
from parallax.snapshot.handle._execution_authority import ExecutionCapture
from parallax.snapshot.handle._preflight import preflight
from parallax.snapshot.handle._publication import (
    SelectedReadModel,
    ServingModel,
    read_projection,
)

__all__ = [
    "ReadScope",
    "WireQuery",
    "participating_read_scope",
    "standalone_read_scope",
    "wire_query_node",
]

type WireQuery = ObjectQuery[Any, Any] | ObjectQueryNode | Mapping[str, object]
"""What a Wire read accepts: the canonical Object Query mapping, the canonical
node itself, or — on a class-backed model — the Typed authoring value."""


def wire_query_node(query: WireQuery) -> ObjectQueryNode:
    """``query`` as the one canonical Object Query node every read lowers through.

    Accepting three spellings adds no query semantics: the mapping goes through
    `m-object-query`'s own deserializer, the Typed value through the same
    accessor ``db.find`` uses, and a node passes as itself. Nothing here
    validates the query — the shared read gate does, after this resolution and
    before any I/O — so all three spellings meet the same refusals.

    It is a stable converter a read is handed rather than a step the read
    performs first: a Wire read refuses re-entry before it looks at what it was
    handed, so a mapping no deserializer could accept is refused as re-entry
    when it arrives from inside a lifecycle context, exactly as an unusable Typed
    query is.
    """
    if isinstance(query, ObjectQueryNode):
        return query
    if isinstance(query, Mapping):
        return deserialize(query)
    return object_query_node(query)


@dataclass(frozen=True, slots=True)
class ReadInputs:
    """What the executor triad takes that varies by lane, as one value.

    A standalone read carries the connection its own operation acquired, no
    Concurrency Preference, and no ledger; a participating one carries the
    attempt's connection, the unit of work's preference, and the unit of work
    itself as the ledger retained evidence indexes into. Either way the
    connection is the one the operation currently holds rather than anything the
    Handle retains, which is what makes an operation's statements provably run
    on the connection that operation acquired.
    """

    connection: DatabaseConnection
    preference: Concurrency | None
    ledger: ObservationLedger | None


class _BegunRead(StreamRead[SelectedReadModel], Protocol):
    """One operation's read, begun: the selection it is served under, and the
    bracket everything done under that selection runs inside.

    Each capability that executes is handed the scope's body for one operation
    and runs it inside its own bracket, which is where the force-flush, the
    activity opening, the activity's parentage, and — for a standalone read —
    the edition an escaping failure is named under live. Nothing above needs
    to know which lane it is composed with, and nothing here decides anything
    about the query. Every call of one begun read runs under the one selection
    it began with, by construction rather than by threading a parameter.
    """

    def eager[T](
        self,
        target: ActivityTarget,
        interface: ReadInterface,
        body: Callable[[ReadActivity, ReadInputs], T],
        /,
    ) -> T:
        """Run one whole-result read's ``body`` inside this lane's bracket."""
        ...

    def page[T](
        self, batch: StreamBatchActivity, body: Callable[[DatabaseCallScope, ReadInputs], T], /
    ) -> T:
        """Run one page's ``body`` inside this lane's bracket and inside
        ``batch``, which this opens rather than the loop above."""
        ...


class _ReadExecution(Protocol):
    """What a read's lane decides, and the whole of it: how one operation's
    read is begun.

    A standalone execution is one shared object per Handle and begins each
    operation as a read of its own, adopting afresh; a participating one is
    its transaction's and begins every operation as the same fixed read.
    """

    def begin(self) -> _BegunRead:
        """This operation's read, begun inside the read boundary and after
        re-entry has been refused."""
        ...


class ReadScope:
    """One Handle's read policy: the whole-result, streamed, and row-form reads
    every lifecycle facade delegates to.

    Every operation owns its refusal ladder from its own first line, so a read
    that arrives here refuses re-entry in one module rather than at one call
    site per public door. A lifecycle supplies two stable functions per call:
    the converter that lowers its query spelling to the canonical node, and the
    builder of the Publication its result is stated through. Below the ladder
    the shared gate, the milestone-set dispatch, and the delivery entry are
    written once for every representation and both lanes.

    A stream retains this object for its whole delivery as its scope:
    :meth:`begin`, :meth:`validated`, and :meth:`page` answer it from the same
    execution policy every eager read runs under. The scope itself holds no
    model and no page, so a delivery hands back the ONE read it was begun as for
    each of its pages, and no page and no root reaches a second scope or a
    second policy.
    """

    __slots__ = ("_execution", "_lifecycle", "_planner")

    def __init__(
        self,
        lifecycle: InstalledLifecycle | None,
        execution: _ReadExecution,
        planner: ReadPlanner,
    ) -> None:
        self._lifecycle = lifecycle
        self._execution = execution
        self._planner = planner

    def read[Q, Eager](
        self,
        query: Q,
        /,
        *,
        convert_query: Callable[[Q], ObjectQueryNode],
        build_publication: Callable[[SelectedReadModel], Publication[ReadOrigin, Eager]],
    ) -> Eager:
        """One whole-result read, published through ``build_publication``.

        Re-entry is refused first of all: a call that arrived from inside one of
        this Handle's own lifecycle contexts is refused before the model it
        would be served under, this query's shape, or anything downstream of
        them is even consulted (`m-execution-lifecycle`). The read is then
        begun and its publication built, which is where a selection that cannot
        publish the requested representation refuses — before the query is
        lowered, before the gate, and before a participating read's
        force-flush.
        """
        refuse_reentry(self._lifecycle)
        read = self._execution.begin()
        publication = build_publication(read.selected)
        return self._graph(read, convert_query(query), publication)

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
    ) -> StreamDelivery[_BegunRead, P]:
        """One streamed delivery, constructed and not yet entered.

        Re-entry is refused, then this call's own arguments are judged — the
        query lowered, then the page size it was named with — and nothing
        model-dependent is: the delivery begins its read at entry, which is
        where its publication is built. Constructing a delivery begins no read,
        opens no activity, and reaches no executor.
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
        """One row-form read, published as transformed rows and no graph.

        The values lane needs no materializer, so it crosses no classless
        refusal; it records no observation either, which is why its body passes
        no ledger in either lane.
        """
        refuse_reentry(self._lifecycle)
        read = self._execution.begin()
        selected = read.selected
        # The gate precedes the bracket, and therefore precedes a participating
        # read's force-flush: a refused read flushes nothing.
        validated = preflight(node, model=selected.model.meta, form="rows")

        def published(activity: ReadActivity, inputs: ReadInputs) -> RowsResult:
            return find_rows(
                validated,
                selected.model,
                inputs.connection,
                edition=selected.edition,
                versions=CONCURRENCY,
                preference=inputs.preference,
                read=activity,
                planner=self._planner,
            )

        return read.eager(node.target, "rows", published)

    def begin(self) -> _BegunRead:
        """The read one delivery is begun as, when its scope is entered and
        before anything that scope can refuse."""
        return self._execution.begin()

    def validated(self, read: _BegunRead, node: ObjectQueryNode, /) -> ValidatedObjectQuery:
        """``node`` through the shared read gate, under the model ``read`` serves."""
        return preflight(node, model=read.meta, form="graph")

    def page(
        self,
        read: _BegunRead,
        paging: PagingPlan,
        at: At,
        batch: StreamBatchActivity,
        /,
        *,
        scanned: bool,
    ) -> StreamPageResult[ReadOrigin]:
        """One page of a delivery, read inside its begun read's own bracket.

        A page IS an eager read of a bounded root query, so it threads the same
        connection, Concurrency Preference, and observation ledger an eager graph
        read here does — and takes its model from the read the delivery was begun
        as, which holds the one selection it was opened under. A standalone page
        leases its own connection; a participating page uses the attempt's. The
        page's projection observer is created inside that bracket, after any
        read gate.
        """
        model = read.selected.model

        def body(calls: DatabaseCallScope, inputs: ReadInputs) -> StreamPageResult[ReadOrigin]:
            return PageReader().read_page(
                StreamPageRequest(
                    paging,
                    at,
                    model,
                    inputs.connection,
                    inputs.preference,
                    ObservedPageProjections(model.meta, ledger=inputs.ledger, scanned=scanned),
                    calls,
                    self._planner,
                    read.selected.edition,
                )
            )

        return read.page(batch, body)

    def _graph[Eager](
        self,
        read: _BegunRead,
        node: ObjectQueryNode,
        publication: Publication[ReadOrigin, Eager],
    ) -> Eager:
        """The eager graph-form tail every representation runs.

        The gate, the milestone-set dispatch, and the delivery entry are the
        read; the publication decides only how its result is stated. A
        milestone-set read retains no evidence at all, so its roots stand at
        coordinates no keyed write may address.
        """
        selected = read.selected
        validated = preflight(node, model=selected.model.meta, form="graph")

        def published(activity: ReadActivity, inputs: ReadInputs) -> Eager:
            if scans_validated_axis(validated.temporal):
                return deliver_history(
                    validated,
                    selected.model,
                    inputs.connection,
                    publication=publication,
                    read=activity,
                    edition=selected.edition,
                    preference=inputs.preference,
                    planner=self._planner,
                )
            return deliver_find(
                EagerPageRequest(
                    validated,
                    selected.model,
                    inputs.connection,
                    inputs.preference,
                    ObservedPageProjections(
                        selected.model.meta, ledger=inputs.ledger, scanned=False
                    ),
                    activity,
                    self._planner,
                    selected.edition,
                ),
                publication,
            )

        return read.eager(node.target, publication.interface, published)


class _StandaloneRead:
    """One standalone operation's read: its own Root Execution, its own
    connection, no flush, and the edition it adopted named on whatever ordinary
    failure escapes it.

    Non-transactional in the three ways that reach the executor: no read lock,
    no Concurrency Preference, and no ledger — which is what leaves the evidence
    a standalone read retains unstamped by any participation. Built per
    operation by :class:`_StandaloneExecution`, over the selection that
    operation adopted, so everything done through it runs under that one
    selection however long a delivery through it takes.

    It is also where a standalone operation's connection policy lives. An eager
    read brackets one around its whole execution; each delivery page brackets a
    lease inside its own Stream Batch.
    """

    __slots__ = ("adopted", "capture", "lifecycle", "selected")

    def __init__(
        self,
        lifecycle: InstalledLifecycle | None,
        adopted: AdoptedExecution,
        selected: SelectedReadModel,
        capture: ExecutionCapture,
    ) -> None:
        self.lifecycle = lifecycle
        self.adopted = adopted
        self.selected = selected
        self.capture = capture

    def eager[T](
        self,
        target: ActivityTarget,
        interface: ReadInterface,
        body: Callable[[ReadActivity, ReadInputs], T],
        /,
    ) -> T:
        # The Root Execution opens AFTER the gate and spans through publication:
        # the gate is deterministic and reaches no connection, so a refused read
        # creates no root and calls no Provider, while acquisition, planning,
        # lowering, every Database Call, conversion, and materialization are all
        # inside it. It is opened OUTSIDE the failure bracket and entered inside
        # it: a Provider that fails to open keeps its own type, and the root's
        # own Finished event sees the underlying failure before the caller sees
        # it named under this read's edition.
        root = open_read_root(
            self.lifecycle, target=target, interface=interface, edition=self.selected.edition
        )

        def inside() -> T:
            with root as read:
                # One connection for the whole read: every root and relationship
                # statement, the conversion, and the publication it is
                # materialized into. Held until the result exists, because a
                # graph half-built from rows is not a result anything may return.
                resource = self.capture.source.new_context()
                connection, held_since_ns = enter_connection(resource, read)
                try:
                    published = body(read, ReadInputs(connection, None, None))
                except BaseException as failure:
                    exit_connection(resource, read, held_since_ns, failure)
                    raise
                exit_connection(resource, read, held_since_ns, None)
                return published

        return self.adopted.contextualized(inside)

    @property
    def meta(self) -> Metamodel:
        return self.selected.model.meta

    @property
    def edition(self) -> str:
        return self.selected.edition

    def open_stream(
        self, target: ActivityTarget, interface: ReadInterface, batch_size: int, /
    ) -> StreamActivity:
        return open_stream_root(
            self.lifecycle,
            target=target,
            interface=interface,
            batch_size=batch_size,
            edition=self.selected.edition,
        )

    def release(self, failure: BaseException | None, /) -> None:
        del failure

    def page[T](
        self, batch: StreamBatchActivity, body: Callable[[DatabaseCallScope, ReadInputs], T], /
    ) -> T:
        with batch as calls:
            resource = self.capture.source.new_context()
            connection, held_since_ns = enter_connection(resource, batch)
            try:
                result = body(calls, ReadInputs(connection, None, None))
            except BaseException as failure:
                exit_connection(resource, batch, held_since_ns, failure)
                raise
            exit_connection(resource, batch, held_since_ns, None)
            return result

    def advance[T](self, body: Callable[[], T], /) -> T:
        return self.adopted.contextualized(body)


@dataclass(frozen=True, slots=True)
class _StandaloneExecution:
    """A Handle's reads outside any transaction: one begun read per operation.

    It holds the Serving Model rather than a selection, so each operation it
    begins adopts whatever selection is current at that call, through an
    adoption of its own, and is served under that selection for its whole
    execution — a publication landing afterwards reaches the next operation and
    never this one. It holds the bound context SOURCE for the same reason it
    holds the Serving Model and not a selection: a connection belongs to one
    operation, so what is retained here is the ability to create one acquisition
    under the selected authority rather than a connection already acquired.
    """

    lifecycle: InstalledLifecycle | None
    serving: ServingModel
    capture: ExecutionCapture

    def begin(self) -> _StandaloneRead:
        adopted = AdoptedExecution(self.serving)
        selected = read_projection(adopted.adopt())
        return _StandaloneRead(self.lifecycle, adopted, selected, self.capture)


@dataclass(frozen=True, slots=True)
class _ParticipatingExecution:
    """A read inside a transaction: the force-flush, and the attempt's children.

    It is its own begun read, because its selection is the transaction's,
    fixed when the attempt adopted, and nothing it does is bracketed on its
    own: a failure inside it propagates to the invocation, which names the
    attempt's edition once.

    ``uow.read`` flushes pending writes before it runs what it was handed, so
    read-your-own-writes holds at every read and at every page. The activity
    opens INSIDE that flush, which is what makes the dependency batch the read
    forces out an ordered SIBLING of it under the same attempt rather than a
    scope containing it (`m-execution-lifecycle`).

    ``uow.settings.concurrency`` is read once, when the scope is constructed: it
    is fixed for a transaction's life, and each level derives its own effective
    strategy from it and that level's own Optimistic Lock Facet.
    """

    selected: SelectedReadModel
    uow: UnitOfWork
    attempt: TransactionAttemptActivity
    inputs: ReadInputs

    def begin(self) -> _ParticipatingExecution:
        return self

    @property
    def meta(self) -> Metamodel:
        return self.selected.model.meta

    @property
    def edition(self) -> str:
        return self.selected.edition

    def release(self, failure: BaseException | None, /) -> None:
        """Nothing: participating work never checked anything out.

        The attempt owns the connection for its whole life, and a stream inside
        it is one more thing running on that connection rather than a second
        borrower of it.
        """
        del failure

    def advance[T](self, body: Callable[[], T], /) -> T:
        return body()

    def eager[T](
        self,
        target: ActivityTarget,
        interface: ReadInterface,
        body: Callable[[ReadActivity, ReadInputs], T],
        /,
    ) -> T:
        return self.uow.read(lambda: self._inside_read(target, interface, body))

    def _inside_read[T](
        self,
        target: ActivityTarget,
        interface: ReadInterface,
        body: Callable[[ReadActivity, ReadInputs], T],
    ) -> T:
        with self.attempt.read(target, interface) as read:
            return body(read, self.inputs)

    def open_stream(
        self, target: ActivityTarget, interface: ReadInterface, batch_size: int, /
    ) -> StreamActivity:
        return self.attempt.stream(target, interface, batch_size)

    def page[T](
        self, batch: StreamBatchActivity, body: Callable[[DatabaseCallScope, ReadInputs], T], /
    ) -> T:
        return self.uow.read(lambda: self._inside_page(batch, body))

    def _inside_page[T](
        self, batch: StreamBatchActivity, body: Callable[[DatabaseCallScope, ReadInputs], T]
    ) -> T:
        with batch as calls:
            return body(calls, self.inputs)


def standalone_read_scope(
    *,
    lifecycle: InstalledLifecycle | None,
    serving: ServingModel,
    capture: ExecutionCapture,
    planner: ReadPlanner,
) -> ReadScope:
    return ReadScope(
        lifecycle,
        _StandaloneExecution(lifecycle, serving, capture),
        planner,
    )


def participating_read_scope(
    *,
    lifecycle: InstalledLifecycle | None,
    selected: SelectedReadModel,
    uow: UnitOfWork,
    conn: DatabaseConnection,
    attempt: TransactionAttemptActivity,
    planner: ReadPlanner,
) -> ReadScope:
    return ReadScope(
        lifecycle,
        _ParticipatingExecution(
            selected, uow, attempt, ReadInputs(conn, uow.settings.concurrency, uow)
        ),
        planner,
    )
