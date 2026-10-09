from __future__ import annotations

from collections.abc import Callable
from typing import Any

from parallax.core import deep_fetch
from parallax.core.db_port import IsolationLevel
from parallax.core.execution._adoption import AdoptedExecution
from parallax.core.execution._attempt import Attempt
from parallax.core.execution._options import OMITTED, DatabaseOptions, Omitted, patch_options
from parallax.core.execution._publication import (
    SelectedReadModel,
    ServingModel,
    read_projection,
)
from parallax.core.execution._read_policy import (
    StandaloneRead,
    read_graph,
    read_page,
    read_rows,
    resolved,
)
from parallax.core.execution._runner import TransactionRunner
from parallax.core.execution_authority._authority import ExecutionCapture
from parallax.core.execution_lifecycle._activity import (
    InstalledLifecycle,
    StreamBatchActivity,
    refuse_reentry,
)
from parallax.core.object_query import ObjectQueryNode
from parallax.core.object_query._resolved import ResolvedObjectQuery
from parallax.core.read_delivery import RowsResult
from parallax.core.read_delivery._page_reader import StreamPageResult
from parallax.core.read_delivery._paging import At, PagingPlan
from parallax.core.read_delivery._publication import Publication
from parallax.core.read_delivery._read_plan import ReadPlanner
from parallax.core.read_delivery._stream import StreamDelivery, check_batch_size
from parallax.core.unit_work import Concurrency, ReadOrigin

__all__ = ["ExecutionScope"]


class ExecutionScope:
    """One authority-selected, connectionless execution scope over a root's
    shared resources: its captured authority, its option defaults, and the
    standalone reads and transactions run under them.

    Every operation refuses re-entry on its own first line. A lifecycle supplies
    two stable functions per read — the converter that lowers its query
    spelling to the canonical node, and the builder of the Publication its
    result is stated through — and a factory per transaction that turns each
    fully constructed :class:`Attempt` into the transaction its callback is
    handed.

    Each standalone operation adopts whatever selection is current when it
    begins, through an adoption of its own, and is served under that selection
    for its whole execution. The scope holds the bound context SOURCE rather than
    a connection, because a connection belongs to one operation. A stream
    retains this scope for its whole delivery, and each of its pages is read
    inside the one read the delivery was begun as.
    """

    __slots__ = ("_capture", "_lifecycle", "_options", "_planner", "_runner", "_serving")

    def __init__(
        self,
        runner: TransactionRunner,
        capture: ExecutionCapture,
        options: DatabaseOptions,
        *,
        lifecycle: InstalledLifecycle | None,
        serving: ServingModel,
        planner: ReadPlanner,
    ) -> None:
        self._runner = runner
        self._capture = capture
        self._options = options
        self._lifecycle = lifecycle
        self._serving = serving
        self._planner = planner

    def with_options(
        self,
        *,
        max_retries: int | Omitted = OMITTED,
        concurrency: Concurrency | Omitted = OMITTED,
        retry_optimistic_conflicts: bool | Omitted = OMITTED,
        isolation: IsolationLevel | Omitted = OMITTED,
    ) -> ExecutionScope:
        """This scope's authority and resources under patched option defaults."""
        return ExecutionScope(
            self._runner,
            self._capture,
            patch_options(
                self._options,
                max_retries=max_retries,
                concurrency=concurrency,
                retry_optimistic_conflicts=retry_optimistic_conflicts,
                isolation=isolation,
            ),
            lifecycle=self._lifecycle,
            serving=self._serving,
            planner=self._planner,
        )

    def read[Q, Eager](
        self,
        query: Q,
        /,
        *,
        convert_query: Callable[[Q], ObjectQueryNode],
        build_publication: Callable[[SelectedReadModel], Publication[ReadOrigin, Eager]],
    ) -> Eager:
        """One standalone whole-result read, published through
        ``build_publication``.

        Re-entry is refused first of all: a call that arrived from inside one of
        this root's own lifecycle contexts is refused before the model it would
        be served under, this query's shape, or anything downstream of them is
        even consulted (`m-execution-lifecycle`). The read is then begun and its
        publication built, which is where a selection that cannot publish the
        requested representation refuses — before the query is lowered and
        before the gate.
        """
        refuse_reentry(self._lifecycle)
        read = self.begin()
        publication = build_publication(read.selected)
        return read_graph(read, convert_query(query), publication, self._planner)

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
    ) -> StreamDelivery[StandaloneRead, P]:
        """One standalone streamed delivery, constructed and not yet entered.

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
        """One standalone row-form read, published as transformed rows."""
        refuse_reentry(self._lifecycle)
        return read_rows(self.begin(), node, self._planner)

    def begin(self) -> StandaloneRead:
        """One operation's read, adopting the selection current now."""
        adopted = AdoptedExecution(self._serving)
        selected = read_projection(adopted.adopt())
        return StandaloneRead(self._lifecycle, adopted, selected, self._capture)

    def resolved(self, read: StandaloneRead, node: ObjectQueryNode, /) -> ResolvedObjectQuery:
        return resolved(read, node)

    def page(
        self,
        read: StandaloneRead,
        paging: PagingPlan,
        at: At,
        batch: StreamBatchActivity,
        /,
        *,
        scanned: bool,
    ) -> StreamPageResult[ReadOrigin]:
        return read_page(read, paging, at, batch, self._planner, scanned=scanned)

    def transact[Tx, T](
        self,
        fn: Callable[[Tx], T],
        transaction_for: Callable[[Attempt], Tx],
        /,
        *,
        max_retries: int | Omitted = OMITTED,
        concurrency: Concurrency | Omitted = OMITTED,
        retry_optimistic_conflicts: bool | Omitted = OMITTED,
        isolation: IsolationLevel | Omitted = OMITTED,
    ) -> T:
        """Run ``fn`` in a transaction under this scope's authority, joining the
        active one where this root opened it.

        Each explicit option overrides this scope's default for an outer
        invocation and must equal the active transaction's for a join; an
        omitted one inherits.
        """
        return self._runner.transact(
            fn,
            transaction_for,
            capture=self._capture,
            defaults=self._options,
            max_retries=max_retries,
            concurrency=concurrency,
            retry_optimistic_conflicts=retry_optimistic_conflicts,
            isolation=isolation,
        )
