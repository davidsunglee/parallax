"""``parallax.snapshot.handle._read_scope`` — the Read Scope both Handles share.

A ``Database``'s reads and a ``Transaction``'s run one ladder: re-entry is
refused, the operation's selected read model is obtained, this call's own
arguments are judged — for a read publishing Entity Class instances, a selection
that can materialize none at all first, then the query lowered to the canonical
node — the shared gate runs, the activity opens, the executor runs, and the
result is published. A streamed read is that ladder deferred rather than a
second one: the verb lowers what it was handed and judges the page size it was
named with, and answers an inert delivery, which crosses the gate and opens its
own activity when its scope is entered and reaches back here for each page. Only
the bracket around execution differs between a standalone read and one
participating in a transaction, so the ladder belongs here once and the
difference belongs below it, behind a private execution policy the two factories
construct.

The four capabilities that policy answers are the whole of what varies: which
selected read model serves the operation, what an eager read runs inside, what a
stream's own activity is, and what one page runs inside. A participating read's
force-flush, its connection, its Concurrency Preference, its observation ledger,
and the parentage of every activity it opens are all reached through those four
and through nothing else — which is what makes "the gate precedes the flush" and
"the activity opens inside the flush" the order of calls in this module rather
than a rule two Handles each restate.

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
the narrower thing: what stays inside this module even so — the execution policy
and its two adapters, which only the factories below construct, and each class's
own internals.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from parallax.core.db_port import DbPort
from parallax.core.entity import EntityGraphConstruction
from parallax.core.entity._layout import CatalogedModel
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
from parallax.snapshot.handle._errors import SnapshotConnectionError
from parallax.snapshot.handle._page import At, PagePlan, StreamPage, read_stream_page
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
from parallax.snapshot.handle._retention import ObservationLedger
from parallax.snapshot.handle._stream import SnapshotStream, check_batch_size

__all__ = [
    "ReadInputs",
    "ReadScope",
    "SelectedReadModel",
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


@dataclass(frozen=True, slots=True)
class SelectedReadModel:
    """The model ONE read is served under: the cataloged model it resolves,
    plans, and converts against, and — for a class-backed model — the Entity
    Graph Construction collaboration that materializes its rows into instances.

    A property of the operation rather than of the Handle. A ``Database`` may
    answer the same value for every read it serves and a ``Transaction`` answers
    one fixed value for its whole life, but the scope above assumes neither: it
    takes the record its execution policy hands back for THIS operation, and a
    stream keeps the one it opened under through all of its pages.

    The write codec is deliberately absent. A read never derives a row, so a
    record carrying one would offer the write half to every read composition
    that holds it. The construction is the only half that can be missing at all:
    a member layout and a row are both derived from accepted metadata, so a
    descriptor-backed model reaches a fully functional catalog while reaching no
    materializer — which is exactly the refusal :meth:`materializing` states.
    """

    model: CatalogedModel
    construction: EntityGraphConstruction | None

    def materializing(self) -> EntityGraphConstruction:
        """The graph construction a modeled read needs, or refuse before any I/O.

        Absent exactly for a descriptor-backed Domain Model, which composes no
        Entity Class and therefore serves the Wire and write lanes while
        materializing nothing. The refusal lands before the shared gate and
        therefore before a participating read's force-flush, so a Handle that
        cannot materialize a Snapshot at all answers that before it answers
        anything about the query.
        """
        if self.construction is None:
            raise SnapshotConnectionError(
                "this read is served under a model that composed no Entity Class, so it "
                "cannot materialize a Snapshot (snapshot-class-backed-model-required)"
            )
        return self.construction


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


class _ReadExecution(Protocol):
    """What a read's lane decides, and the whole of it.

    Each capability that executes is handed the scope's body for one operation
    and runs it inside its own bracket, which is where the force-flush, the
    activity opening, and the activity's parentage live. Nothing above needs to
    know which lane it is composed with, and nothing here decides anything about
    the query.
    """

    def begin(self) -> SelectedReadModel:
        """The model this operation is served under, chosen inside the read
        boundary and after re-entry has been refused."""
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
    :meth:`open_stream` and :meth:`page` are for: they are the scope from the
    delivery's side, and they answer it from the same execution policy every
    eager read runs under. The scope itself holds no model and no page, so a
    delivery hands back the ONE selection it was opened under for each of its
    pages, and no page and no root reaches a second scope or a second policy.
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
        selected = self._execution.begin()
        construction = selected.materializing()
        return self._graph(
            selected,
            object_query_node(query),
            typed_publication(selected.model.meta, construction),
        )

    def stream(self, query: ObjectQuery[Any, Any], batch_size: int) -> SnapshotStream[Any]:
        """One Typed streamed read, delivered as Entity Class instances.

        The refusal order is :meth:`find`'s, with this call's own page size
        judged among its arguments: re-entry, then a selection that can
        materialize no Snapshot at all, then the query and the size it was
        named with.
        """
        refuse_reentry(self._lifecycle)
        selected = self._execution.begin()
        construction = selected.materializing()
        return self._streamed(
            selected,
            object_query_node(query),
            typed_publication(selected.model.meta, construction),
            batch_size,
        )

    def read_rows(self, node: ObjectQueryNode) -> RowsResult:
        """One row-form read, published as transformed rows and no graph.

        The values lane needs no materializer, so it crosses no classless
        refusal; it records no observation either, which is why its body passes
        no ledger in either lane.
        """
        refuse_reentry(self._lifecycle)
        selected = self._execution.begin()
        # The gate precedes the bracket, and therefore precedes a participating
        # read's force-flush: a refused read flushes nothing.
        validated = preflight(node, model=selected.model.meta, form="rows")

        def published(read: ReadActivity, inputs: ReadInputs) -> RowsResult:
            return find_rows(
                validated,
                selected.model,
                inputs.port,
                preference=inputs.preference,
                read=read,
            )

        return self._execution.eager(node.target, "ROWS", published)

    def wire_find(self, query: WireQuery) -> Snapshot[Any]:
        """One Wire whole-result read, published as frozen Wire nodes.

        The refusal order is :meth:`find`'s without its classless rung — no Wire
        node is an Entity Class instance, so none needs a materializer: re-entry,
        then the selection, then this call's own argument, which for a Wire entry
        is the spelling it was handed lowered to the canonical node.
        """
        refuse_reentry(self._lifecycle)
        selected = self._execution.begin()
        return self._graph(selected, wire_query_node(query), wire_publication(selected.model.meta))

    def wire_stream(self, query: WireQuery, batch_size: int) -> SnapshotStream[Any]:
        """One Wire streamed read, delivered as frozen Wire nodes.

        :meth:`wire_find`'s ladder with the page size judged among this call's
        own arguments, after the query it was named beside.
        """
        refuse_reentry(self._lifecycle)
        selected = self._execution.begin()
        return self._streamed(
            selected, wire_query_node(query), wire_publication(selected.model.meta), batch_size
        )

    def open_stream(
        self, target: ActivityTarget, interface: ReadInterface, batch_size: int
    ) -> SnapshotStreamActivity:
        """The activity one delivery observes itself through, opened when its
        scope is entered and after everything that scope can refuse."""
        return self._execution.open_stream(target, interface, batch_size)

    def page(
        self, page_plan: PagePlan, at: At, model: CatalogedModel, batch: StreamBatchActivity
    ) -> StreamPage:
        """One page of a delivery, read inside this lane's own bracket.

        A page IS an eager read of a bounded root query, so it threads the same
        port, Concurrency Preference, and observation ledger an eager graph read
        here does — and takes its model from the delivery, which holds the one
        selection it was opened under rather than asking for a second.
        """

        def read(calls: DatabaseCallScope, inputs: ReadInputs) -> StreamPage:
            return read_stream_page(
                page_plan,
                at,
                model,
                inputs.port,
                preference=inputs.preference,
                ledger=inputs.ledger,
                calls=calls,
            )

        return self._execution.page(batch, read)

    def _streamed(
        self,
        selected: SelectedReadModel,
        node: ObjectQueryNode,
        publication: ResultPublication,
        batch_size: int,
    ) -> SnapshotStream[Any]:
        """The stream-construction tail both read interfaces run.

        Constructing a delivery opens no activity and reaches no executor: the
        gate, the page plan, and every statement belong to the entered scope, so
        a stream nobody enters observes nothing and reads nothing. What is
        settled here is what this call named — the page size, refused before any
        plan and any I/O — and the selection the delivery will keep through all
        of its pages.
        """
        check_batch_size(batch_size)
        return SnapshotStream(node, selected.model, publication, self, batch_size=batch_size)

    def _graph(
        self,
        selected: SelectedReadModel,
        node: ObjectQueryNode,
        publication: ResultPublication,
    ) -> Snapshot[Any]:
        """The eager graph-form tail both read interfaces run.

        The gate, the milestone-set dispatch, and the executor entry are the
        read; the publication decides only how its result is stated. A
        milestone-set read runs :func:`find_history`, which retains no evidence
        at all, so its roots stand at coordinates no keyed write may address.
        """
        validated = preflight(node, model=selected.model.meta, form="graph")

        def published(read: ReadActivity, inputs: ReadInputs) -> Snapshot[Any]:
            if scans_validated_axis(validated.temporal):
                return publication.from_history(
                    find_history(
                        validated,
                        selected.model,
                        inputs.port,
                        read=read,
                    )
                )
            return publication.from_find(
                find(
                    validated,
                    selected.model,
                    inputs.port,
                    preference=inputs.preference,
                    ledger=inputs.ledger,
                    calls=read,
                )
            )

        return self._execution.eager(node.target, publication.interface, published)


@dataclass(frozen=True, slots=True)
class _StandaloneExecution:
    """A read outside any transaction: its own Root Execution, and no flush.

    Non-transactional in the three ways that reach the executor: no read lock,
    no Concurrency Preference, and no ledger — which is what leaves the evidence
    a standalone read retains unstamped by any participation.
    """

    lifecycle: InstalledLifecycle | None
    selected: SelectedReadModel
    inputs: ReadInputs

    def begin(self) -> SelectedReadModel:
        return self.selected

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
        # Database Call, conversion, and materialization are all inside it.
        with open_read_root(self.lifecycle, target=target, interface=interface) as read:
            return body(read, self.inputs)

    def open_stream(
        self, target: ActivityTarget, interface: ReadInterface, batch_size: int, /
    ) -> SnapshotStreamActivity:
        return open_snapshot_stream_root(
            self.lifecycle, target=target, interface=interface, batch_size=batch_size
        )

    def page[T](
        self, batch: StreamBatchActivity, body: Callable[[DatabaseCallScope, ReadInputs], T], /
    ) -> T:
        # Nothing precedes the batch here — a standalone stream flushes nothing
        # — so it opens where the page begins.
        with batch as calls:
            return body(calls, self.inputs)


@dataclass(frozen=True, slots=True)
class _ParticipatingExecution:
    """A read inside a transaction: the force-flush, and the attempt's children.

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

    def begin(self) -> SelectedReadModel:
        return self.selected

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
    selected: SelectedReadModel,
    port: DbPort,
) -> ReadScope:
    return ReadScope(
        lifecycle, _StandaloneExecution(lifecycle, selected, ReadInputs(port, None, None))
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
