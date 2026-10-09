from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from parallax.core.db_port import DatabaseConnection
from parallax.core.execution._adoption import AdoptedExecution
from parallax.core.execution._concurrency import CONCURRENCY
from parallax.core.execution._connection_lifecycle import enter_connection, exit_connection
from parallax.core.execution._page_origins import ObservedPageProjections
from parallax.core.execution._preflight import preflight
from parallax.core.execution._publication import SelectedReadModel
from parallax.core.execution._retention import ObservationLedger
from parallax.core.execution_authority._authority import ExecutionCapture
from parallax.core.execution_lifecycle import ReadInterface
from parallax.core.execution_lifecycle._activity import (
    ActivityTarget,
    DatabaseCallScope,
    InstalledLifecycle,
    ReadActivity,
    StreamActivity,
    StreamBatchActivity,
    open_read_root,
    open_stream_root,
)
from parallax.core.metamodel import Metamodel
from parallax.core.object_query import ObjectQueryNode
from parallax.core.object_query._resolved import ResolvedObjectQuery
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
from parallax.core.read_delivery._stream import StreamRead
from parallax.core.temporal_read import scans_resolved_axis
from parallax.core.unit_work import Concurrency, ReadOrigin

__all__ = [
    "BegunRead",
    "ReadInputs",
    "StandaloneRead",
    "read_graph",
    "read_page",
    "read_rows",
    "resolved",
]


@dataclass(frozen=True, slots=True)
class ReadInputs:
    """What the executor triad takes that varies by lane, as one value.

    A standalone read carries the connection its own operation acquired, no
    Concurrency Preference, and no ledger; a participating one carries the
    attempt's connection, the unit of work's preference, and the unit of work
    itself as the ledger retained evidence indexes into. Either way the
    connection is the one the operation currently holds rather than anything a
    scope retains, which is what makes an operation's statements provably run
    on the connection that operation acquired.
    """

    connection: DatabaseConnection
    preference: Concurrency | None
    ledger: ObservationLedger | None


class BegunRead(StreamRead[SelectedReadModel], Protocol):
    """One operation's read, begun: the selection it is served under, and the
    bracket everything done under that selection runs inside.

    Each capability that executes is handed one operation's body and runs it
    inside its own bracket, which is where the force-flush, the activity
    opening, the activity's parentage, and — for a standalone read — the
    edition an escaping failure is named under live. Nothing that calls it needs
    to know which lane it is, and nothing here decides anything about the
    query. Every call of one begun read runs under the one selection it began
    with, by construction rather than by threading a parameter.
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

    def paged[T](
        self, batch: StreamBatchActivity, body: Callable[[DatabaseCallScope, ReadInputs], T], /
    ) -> T:
        """Run one page's ``body`` inside this lane's bracket and inside
        ``batch``, which this opens rather than the loop above."""
        ...


def read_graph[Eager](
    read: BegunRead,
    node: ObjectQueryNode,
    publication: Publication[ReadOrigin, Eager],
    planner: ReadPlanner,
) -> Eager:
    """The eager graph-form tail every representation and both lanes run.

    The gate, the milestone-set dispatch, and the delivery entry are the read;
    the publication decides only how its result is stated. The gate precedes
    the bracket, and therefore a participating read's force-flush. A
    milestone-set read retains no evidence at all, so its roots stand at
    coordinates no keyed write may address. Each eager Page's projection
    observer is created inside the bracket, after any read gate.
    """
    selected = read.selected
    checked = preflight(node, model=selected.model.meta, form="graph")

    def published(activity: ReadActivity, inputs: ReadInputs) -> Eager:
        if scans_resolved_axis(checked.temporal):
            return deliver_history(
                checked,
                selected.model,
                inputs.connection,
                publication=publication,
                read=activity,
                edition=selected.edition,
                preference=inputs.preference,
                planner=planner,
            )
        return deliver_find(
            EagerPageRequest(
                checked,
                selected.model,
                inputs.connection,
                inputs.preference,
                ObservedPageProjections(selected.model.meta, ledger=inputs.ledger, scanned=False),
                activity,
                planner,
                selected.edition,
            ),
            publication,
        )

    return read.eager(node.target, publication.interface, published)


def read_rows(read: BegunRead, node: ObjectQueryNode, planner: ReadPlanner) -> RowsResult:
    """One row-form read, published as transformed rows and no graph.

    The values lane needs no materializer, so it crosses no classless refusal;
    it records no observation either, which is why its body passes no ledger in
    either lane. The gate precedes the bracket, so a refused read flushes
    nothing.
    """
    selected = read.selected
    checked = preflight(node, model=selected.model.meta, form="rows")

    def published(activity: ReadActivity, inputs: ReadInputs) -> RowsResult:
        return find_rows(
            checked,
            selected.model,
            inputs.connection,
            edition=selected.edition,
            versions=CONCURRENCY,
            preference=inputs.preference,
            read=activity,
            planner=planner,
        )

    return read.eager(node.target, "rows", published)


def resolved(read: BegunRead, node: ObjectQueryNode, /) -> ResolvedObjectQuery:
    """``node`` through the shared read gate, under the model ``read`` serves."""
    return preflight(node, model=read.meta, form="graph")


def read_page(
    read: BegunRead,
    paging: PagingPlan,
    at: At,
    batch: StreamBatchActivity,
    planner: ReadPlanner,
    /,
    *,
    scanned: bool,
) -> StreamPageResult[ReadOrigin]:
    """One page of a delivery, read inside its begun read's own bracket.

    A page IS an eager read of a bounded root query, so it threads the same
    connection, Concurrency Preference, and observation ledger an eager graph
    read does — and takes its model from the read the delivery was begun as,
    which holds the one selection it was opened under. A standalone page leases
    its own connection; a participating page uses the attempt's. The page's
    projection observer is created inside that bracket, after any read gate.
    """
    selected = read.selected
    model = selected.model

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
                planner,
                selected.edition,
            )
        )

    return read.paged(batch, body)


class StandaloneRead:
    """One standalone operation's read: its own Root Execution, its own
    connection, no flush, and the edition it adopted named on whatever ordinary
    failure escapes it.

    Non-transactional in the three ways that reach the executor: no read lock,
    no Concurrency Preference, and no ledger — which is what leaves the evidence
    a standalone read retains unstamped by any participation. Built per
    operation by its Execution Scope, over the selection that operation
    adopted, so everything done through it runs under that one selection
    however long a delivery through it takes.

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

    def paged[T](
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
