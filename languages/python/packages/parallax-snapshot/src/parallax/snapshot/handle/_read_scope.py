"""``parallax.snapshot.handle._read_scope`` — the Read Scope both Handles share.

A ``Database`` and a ``Transaction`` run one read ladder: re-entry is refused,
the operation's selected read model is obtained, a classless connection is
refused, the query is lowered, the shared gate runs, the activity opens, the
executor runs, and the result is published. Only the bracket around execution
differs between a standalone read and one participating in a transaction, so the
ladder belongs here once and the difference belongs below it, behind a private
execution policy the two factories construct.

The four capabilities that policy answers are the whole of what varies: which
selected read model serves the operation, what an eager read runs inside, what a
stream's own activity is, and what one page runs inside. A participating read's
force-flush, its connection, its Concurrency Preference, its observation ledger,
and the parentage of every activity it opens are all reached through those four
and through nothing else — which is what makes "the gate precedes the flush" and
"the activity opens inside the flush" the order of calls in this module rather
than a rule two Handles each restate.

This module is an implementation boundary rather than an extension point:
nothing here is re-exported from ``parallax.snapshot.handle`` or
``parallax.snapshot``, and module privacy is what closes construction.

Its ``spec/python.md`` §7 scope states what a read ladder reaches. Batch writes,
Transaction-Time writes, and Bitemporal writes fall outside its closure although
the parent scope is granted all three; bounded automatic retry does not, because
``m-execution-lifecycle`` — which the re-entry gate and the read roots require —
declares an edge to it.

Every name here is spelled bare: privacy is carried by this MODULE's leading
underscore and by the package's frozen ``__all__``, not by per-name underscores.
"""

from __future__ import annotations

from collections.abc import Callable
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
from parallax.core.object_query import ObjectQueryNode
from parallax.core.object_query._fluent import ObjectQuery, object_query_node
from parallax.core.temporal_read import scans_validated_axis
from parallax.core.unit_work import Concurrency, UnitOfWork

# Sibling implementation modules. None of these names carries a leading
# underscore, precisely because it crosses a module boundary: privacy is carried
# by the private MODULE names and by the package's frozen `__all__`, not by
# per-name underscores.
from parallax.snapshot.handle._errors import SnapshotConnectionError
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

__all__ = [
    "ReadInputs",
    "ReadScope",
    "SelectedReadModel",
    "participating_read_scope",
    "standalone_read_scope",
]


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
    """One Handle's whole read composition: the verbs its Typed surface and its
    Wire view both delegate to.

    Every verb owns its refusal ladder from its own first line, which is what
    makes re-entry completeness structural: there is one module to read for all
    of it, rather than one call site per public door. Below the ladder the shared
    gate, the milestone-set dispatch, and the executor entry are written once for
    both interfaces and both lanes; which materializer publishes a result is
    chosen per call and is never scope state.
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

    def wire_find(self, node: ObjectQueryNode) -> Snapshot[Any]:
        """One Wire whole-result read, published as frozen Wire nodes."""
        refuse_reentry(self._lifecycle)
        selected = self._execution.begin()
        return self._graph(selected, node, wire_publication(selected.model.meta))

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
    """The Read Scope a ``Database`` owns: standalone execution over ``port``."""
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
    """The Read Scope a ``Transaction`` owns: participating execution over the
    attempt's own connection, unit of work, and activity."""
    return ReadScope(
        lifecycle,
        _ParticipatingExecution(
            selected, uow, attempt, ReadInputs(conn, uow.settings.concurrency, uow)
        ),
    )
