"""``parallax.snapshot.handle._read_scope`` — the Read Scope both Handles share.

A ``Database``'s reads and a ``Transaction``'s run one ladder: re-entry is
refused, the read is begun — which is where a standalone operation adopts the
Serving Model's current selection — this call's own arguments are judged: for a
read publishing Entity Class instances, a selection that can materialize none at
all first, then the query lowered to the canonical node; the shared gate runs,
the activity opens, the executor runs, and the result is published stamped with
the edition it was read under. A streamed read is that ladder deferred rather
than a second one: the verb lowers what it was handed and judges the page size
it was named with, and answers an inert delivery that begins its read, crosses
the gate, and opens its own activity when its scope is entered, and reaches back
here for each page. Only the bracket around execution differs between a
standalone read and one participating in a transaction, so the ladder belongs
here once and the difference belongs below it, behind a private execution policy
the two factories construct.

What that policy answers is a begun read: the selection one operation is served
under, and the four brackets everything done under it runs inside — what an
eager read runs inside, what a stream's own activity is, what one page runs
inside, and what one advance of a delivery runs inside. A participating read's
force-flush, its connection, its Concurrency Preference, its observation ledger,
and the parentage of every activity it opens are all reached through those and
through nothing else — which is what makes "the gate precedes the flush" and
"the activity opens inside the flush" the order of calls in this module rather
than a rule two Handles each restate. A standalone begun read is also where an
ordinary failure escaping the execution is named under the edition it adopted:
the root activity is opened before that bracket, so a Provider that fails to
open, like every refusal the ladder makes before the bracket, keeps its own
type.

This module is an implementation boundary rather than an extension point.
:data:`WireQuery` alone is re-exported from ``parallax.snapshot.handle``, because
the spellings a Wire read accepts are vocabulary of a public signature; nothing
else here crosses that boundary, nothing here reaches ``parallax.snapshot`` at
all, and module privacy is what closes construction.

Its ``spec/python.md`` §7 scope states what a read ladder reaches. Batch writes,
Transaction-Time writes, and Bitemporal writes fall outside its closure although
the parent scope is granted all three; bounded automatic retry does not, because
``m-execution-lifecycle`` — which the re-entry gate and the read roots require —
declares an edge to it.

Every name this module publishes is spelled bare: privacy from the package
outwards is carried by this MODULE's leading underscore and by the package's
frozen ``__all__``, not by per-name underscores. A leading underscore here marks
the narrower thing: what stays inside this module even so — the execution policy,
the begun read it answers, and its two adapters, which only the factories below
construct, and each class's own internals.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from parallax.core.db_port import DbPort
from parallax.core.entity import EntityGraphConstruction
from parallax.core.execution_lifecycle import ReadInterface
from parallax.core.execution_lifecycle._activity import (
    ActivityTarget,
    DatabaseCallScope,
    InstalledLifecycle,
    ReadActivity,
    SnapshotStreamActivity,
    StreamBatchActivity,
    TransactionAttemptActivity,
    open_read_root,
    open_snapshot_stream_root,
    refuse_reentry,
)
from parallax.core.object_query import ObjectQueryNode, deserialize
from parallax.core.object_query._fluent import ObjectQuery, object_query_node
from parallax.core.temporal_read import scans_validated_axis
from parallax.core.unit_work import Concurrency, UnitOfWork

# Sibling implementation modules. None of these names carries a leading
# underscore, precisely because it crosses a module boundary: privacy is carried
# by the private MODULE names and by the package's frozen `__all__`, not by
# per-name underscores.
from parallax.snapshot.handle._adoption import AdoptedExecution
from parallax.snapshot.handle._errors import SnapshotConnectionError
from parallax.snapshot.handle._page import At, PagePlan, StreamPage, read_stream_page
from parallax.snapshot.handle._preflight import preflight
from parallax.snapshot.handle._publication import (
    SelectedReadModel,
    ServingModel,
    read_projection,
)
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
from parallax.snapshot.handle._retention import ObservationLedger
from parallax.snapshot.handle._stream import SnapshotStream, StreamRead, check_batch_size

__all__ = [
    "ReadInputs",
    "ReadScope",
    "WireQuery",
    "materializing",
    "participating_read_scope",
    "publication_for",
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

    It lives beside the verbs rather than beside the view because lowering IS an
    argument of the call: a Wire read refuses re-entry before it looks at what it
    was handed, so a mapping no deserializer could accept is refused as re-entry
    when it arrives from inside a lifecycle context, exactly as an unusable Typed
    query is.
    """
    if isinstance(query, ObjectQueryNode):
        return query
    if isinstance(query, Mapping):
        return deserialize(query)
    return object_query_node(query)


def materializing(selected: SelectedReadModel, /) -> EntityGraphConstruction:
    """The graph construction a modeled read needs, or refuse before any I/O.

    Absent exactly for a descriptor-backed Domain Model, which composes no
    Entity Class and therefore serves the Wire and write lanes while
    materializing nothing. The refusal lands before the shared gate and
    therefore before a participating read's force-flush, so a Handle that
    cannot materialize a Snapshot at all answers that before it answers
    anything about the query. It is a function here rather than a method of the
    record because the record's sealed scope may not name the refusal.
    """
    if selected.construction is None:
        raise SnapshotConnectionError(
            "this read is served under a model that composed no Entity Class, so it "
            "cannot materialize a Snapshot (snapshot-class-backed-model-required)"
        )
    return selected.construction


def publication_for(selected: SelectedReadModel, interface: ReadInterface, /) -> ResultPublication:
    """The publication one read through ``interface`` publishes under ``selected``.

    A Typed publication needs the graph construction, so this is where a
    selection that can materialize no Snapshot at all refuses a Typed read —
    before the query is judged and before any I/O — while a Wire publication
    crosses no such rung. Either carries the selection's edition, so every
    envelope it publishes is stamped with what the read was served under.
    """
    if interface == "TYPED":
        return typed_publication(selected.model.meta, materializing(selected), selected.edition)
    if interface == "WIRE":
        return wire_publication(selected.model.meta, selected.edition)
    raise ValueError(f"the values lane publishes no graph, so {interface!r} names no publication")


@dataclass(frozen=True, slots=True)
class ReadInputs:
    """What the executor triad takes that varies by lane, as one value.

    A standalone read carries the Handle's own long-lived port, no Concurrency
    Preference, and no ledger; a participating one carries the attempt's
    connection, the unit of work's preference, and the unit of work itself as the
    ledger retained evidence indexes into. Built once when the scope is
    constructed, so no read and no page assembles one.
    """

    port: DbPort
    preference: Concurrency | None
    ledger: ObservationLedger | None


class _BegunRead(StreamRead, Protocol):
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

    @property
    def selected(self) -> SelectedReadModel:
        """The model this operation is served under."""
        ...

    def eager[T](
        self,
        target: ActivityTarget,
        interface: ReadInterface,
        body: Callable[[ReadActivity, ReadInputs], T],
        /,
    ) -> T:
        """Run one whole-result read's ``body`` inside this lane's bracket."""
        ...

    def open_stream(
        self, target: ActivityTarget, interface: ReadInterface, batch_size: int, /
    ) -> SnapshotStreamActivity:
        """This lane's own Snapshot Stream activity, unentered."""
        ...

    def page[T](
        self, batch: StreamBatchActivity, body: Callable[[DatabaseCallScope, ReadInputs], T], /
    ) -> T:
        """Run one page's ``body`` inside this lane's bracket and inside
        ``batch``, which this opens rather than the loop above."""
        ...

    def advance[T](self, body: Callable[[], T], /) -> T:
        """Run one advance of a delivery's view inside this lane's failure
        bracket, after the delivery has settled what the advance did."""
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
    """One Handle's read composition: the whole-result, streamed, and row-form
    verbs its Typed surface and its Wire view both delegate to.

    Every verb owns its refusal ladder from its own first line, so a read that
    arrives here refuses re-entry in one module rather than at one call site per
    public door. Below the ladder the shared gate, the milestone-set dispatch,
    and the executor entry are written once for both interfaces and both lanes;
    which materializer publishes a result is chosen per call and is never scope
    state.

    A stream retains this object for its whole delivery, which is what
    :meth:`begin`, :meth:`publication`, and :meth:`page` are for: they are the
    scope from the delivery's side, and they answer it from the same execution
    policy every eager read runs under. The scope itself holds no model and no
    page, so a delivery hands back the ONE read it was begun as for each of
    its pages, and no page and no root reaches a second scope or a second
    policy.
    """

    __slots__ = ("_execution", "_lifecycle")

    def __init__(self, lifecycle: InstalledLifecycle | None, execution: _ReadExecution) -> None:
        self._lifecycle = lifecycle
        self._execution = execution

    def find(self, query: ObjectQuery[Any, Any]) -> Snapshot[Any]:
        """One Typed whole-result read, published as Entity Class instances."""
        # Re-entry is refused first of all: a call that arrived from inside one
        # of this Handle's own lifecycle contexts is refused before the model it
        # would be served under, this query's shape, or anything downstream of
        # them is even consulted (`m-execution-lifecycle`).
        refuse_reentry(self._lifecycle)
        read = self._execution.begin()
        publication = publication_for(read.selected, "TYPED")
        return self._graph(read, object_query_node(query), publication)

    def stream(self, query: ObjectQuery[Any, Any], batch_size: int) -> SnapshotStream[Any]:
        """One Typed streamed read, delivered as Entity Class instances.

        Re-entry is refused, then this call's own arguments are judged — the
        query lowered, then the page size it was named with — and nothing
        model-dependent is: the delivery begins its read at entry, which is
        where a selection that can materialize no Snapshot at all refuses it.
        """
        refuse_reentry(self._lifecycle)
        return self._streamed(object_query_node(query), "TYPED", batch_size)

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
                inputs.port,
                edition=selected.edition,
                preference=inputs.preference,
                read=activity,
            )

        return read.eager(node.target, "ROWS", published)

    def wire_find(self, query: WireQuery) -> Snapshot[Any]:
        """One Wire whole-result read, published as frozen Wire nodes.

        The refusal order is :meth:`find`'s without its classless rung — no Wire
        node is an Entity Class instance, so none needs a materializer: re-entry,
        then the read begun, then this call's own argument, which for a Wire
        entry is the spelling it was handed lowered to the canonical node.
        """
        refuse_reentry(self._lifecycle)
        read = self._execution.begin()
        publication = publication_for(read.selected, "WIRE")
        return self._graph(read, wire_query_node(query), publication)

    def wire_stream(self, query: WireQuery, batch_size: int) -> SnapshotStream[Any]:
        """One Wire streamed read, delivered as frozen Wire nodes.

        :meth:`stream`'s ladder over a Wire spelling: re-entry, then the query
        lowered, then the page size judged, and the read begun at entry.
        """
        refuse_reentry(self._lifecycle)
        return self._streamed(wire_query_node(query), "WIRE", batch_size)

    def begin(self) -> _BegunRead:
        """The read one delivery is begun as, when its scope is entered and
        before anything that scope can refuse."""
        return self._execution.begin()

    def publication(
        self, selected: SelectedReadModel, interface: ReadInterface, /
    ) -> ResultPublication:
        """How one delivery publishes its roots under the read it was begun
        as, chosen at entry exactly as an eager read chooses it at the call."""
        return publication_for(selected, interface)

    def page(
        self, read: _BegunRead, page_plan: PagePlan, at: At, batch: StreamBatchActivity
    ) -> StreamPage:
        """One page of a delivery, read inside its begun read's own bracket.

        A page IS an eager read of a bounded root query, so it threads the same
        port, Concurrency Preference, and observation ledger an eager graph read
        here does — and takes its model from the read the delivery was begun
        as, which holds the one selection it was opened under rather than
        asking for a second.
        """
        model = read.selected.model

        def body(calls: DatabaseCallScope, inputs: ReadInputs) -> StreamPage:
            return read_stream_page(
                page_plan,
                at,
                model,
                inputs.port,
                preference=inputs.preference,
                ledger=inputs.ledger,
                calls=calls,
            )

        return read.page(batch, body)

    def _streamed(
        self, node: ObjectQueryNode, interface: ReadInterface, batch_size: int
    ) -> SnapshotStream[Any]:
        """The stream-construction tail both read interfaces run.

        Constructing a delivery begins no read, opens no activity, and reaches
        no executor: the selection, the gate, the page plan, and every statement
        belong to the entered scope, so a stream nobody enters adopts nothing,
        observes nothing, and reads nothing. What is settled here is what this
        call named — the lowered query, the interface, and the page size, the
        last refused before any plan and any I/O.
        """
        check_batch_size(batch_size)
        return SnapshotStream(node, interface, self, batch_size=batch_size)

    def _graph(
        self,
        read: _BegunRead,
        node: ObjectQueryNode,
        publication: ResultPublication,
    ) -> Snapshot[Any]:
        """The eager graph-form tail both read interfaces run.

        The gate, the milestone-set dispatch, and the executor entry are the
        read; the publication decides only how its result is stated. A
        milestone-set read runs :func:`find_history`, which retains no evidence
        at all, so its roots stand at coordinates no keyed write may address.
        """
        selected = read.selected
        validated = preflight(node, model=selected.model.meta, form="graph")

        def published(activity: ReadActivity, inputs: ReadInputs) -> Snapshot[Any]:
            if scans_validated_axis(validated.temporal):
                return publication.from_history(
                    find_history(
                        validated,
                        selected.model,
                        inputs.port,
                        read=activity,
                    )
                )
            return publication.from_find(
                find(
                    validated,
                    selected.model,
                    inputs.port,
                    preference=inputs.preference,
                    ledger=inputs.ledger,
                    calls=activity,
                )
            )

        return read.eager(node.target, publication.interface, published)


@dataclass(frozen=True, slots=True)
class _StandaloneRead:
    """One standalone operation's read: its own Root Execution, no flush, and
    the edition it adopted named on whatever ordinary failure escapes it.

    Non-transactional in the three ways that reach the executor: no read lock,
    no Concurrency Preference, and no ledger — which is what leaves the evidence
    a standalone read retains unstamped by any participation. Built per
    operation by :class:`_StandaloneExecution`, over the selection that
    operation adopted, so everything done through it runs under that one
    selection however long a delivery through it takes.
    """

    lifecycle: InstalledLifecycle | None
    adopted: AdoptedExecution
    selected: SelectedReadModel
    inputs: ReadInputs

    def eager[T](
        self,
        target: ActivityTarget,
        interface: ReadInterface,
        body: Callable[[ReadActivity, ReadInputs], T],
        /,
    ) -> T:
        # The Root Execution opens AFTER the gate and spans through publication:
        # the gate is deterministic and reaches no port, so a refused read
        # creates no root and calls no Provider, while planning, lowering, every
        # Database Call, conversion, and materialization are all inside it. It
        # is opened OUTSIDE the failure bracket and entered inside it: a
        # Provider that fails to open keeps its own type, and the root's own
        # Finished event sees the underlying failure before the caller sees it
        # named under this read's edition.
        root = open_read_root(
            self.lifecycle, target=target, interface=interface, edition=self.selected.edition
        )

        def inside() -> T:
            with root as read:
                return body(read, self.inputs)

        return self.adopted.contextualized(inside)

    def open_stream(
        self, target: ActivityTarget, interface: ReadInterface, batch_size: int, /
    ) -> SnapshotStreamActivity:
        return open_snapshot_stream_root(
            self.lifecycle,
            target=target,
            interface=interface,
            batch_size=batch_size,
            edition=self.selected.edition,
        )

    def page[T](
        self, batch: StreamBatchActivity, body: Callable[[DatabaseCallScope, ReadInputs], T], /
    ) -> T:
        # Nothing precedes the batch here — a standalone stream flushes nothing
        # — so it opens where the page begins. The page is not bracketed on its
        # own: the batch and the stream above it report the underlying failure,
        # and the advance that reached this page names the edition once.
        with batch as calls:
            return body(calls, self.inputs)

    def advance[T](self, body: Callable[[], T], /) -> T:
        return self.adopted.contextualized(body)


@dataclass(frozen=True, slots=True)
class _StandaloneExecution:
    """A Handle's reads outside any transaction: one begun read per operation.

    It holds the Serving Model rather than a selection, so each operation it
    begins adopts whatever selection is current at that call, through an
    adoption of its own, and is served under that selection for its whole
    execution — a publication landing afterwards reaches the next operation and
    never this one.
    """

    lifecycle: InstalledLifecycle | None
    serving: ServingModel
    inputs: ReadInputs

    def begin(self) -> _StandaloneRead:
        adopted = AdoptedExecution(self.serving)
        selected = read_projection(adopted.adopt())
        return _StandaloneRead(self.lifecycle, adopted, selected, self.inputs)


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
    ) -> SnapshotStreamActivity:
        return self.attempt.snapshot_stream(target, interface, batch_size)

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
    port: DbPort,
) -> ReadScope:
    return ReadScope(
        lifecycle, _StandaloneExecution(lifecycle, serving, ReadInputs(port, None, None))
    )


def participating_read_scope(
    *,
    lifecycle: InstalledLifecycle | None,
    selected: SelectedReadModel,
    uow: UnitOfWork,
    conn: DbPort,
    attempt: TransactionAttemptActivity,
) -> ReadScope:
    return ReadScope(
        lifecycle,
        _ParticipatingExecution(
            selected, uow, attempt, ReadInputs(conn, uow.settings.concurrency, uow)
        ),
    )
