from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping, Sequence
from contextlib import ExitStack
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Final, Never, Protocol, cast

from parallax.core.execution_lifecycle._activity import (
    DatabaseCallActivity,
    DatabaseCallScope,
)
from parallax.core.internal import read_planning
from parallax.core.internal.base import InternalError
from parallax.core.internal.db_port import DatabaseConnection, PipelineStatement, Row
from parallax.core.internal.metamodel import EntityIdentity
from parallax.core.internal.object_query._resolved import (
    ContinuationCoordinate,
    ResolvedObjectQuery,
)
from parallax.core.internal.read_delivery._fetch import (
    attach_back_reference,
    attach_children,
    attach_empty,
    correlation_member,
    execute_read,
    gather_keys,
    guarded_parents,
    parent_refs,
)
from parallax.core.internal.read_delivery._page import (
    INERT_OBSERVER,
    ROOT_LEVEL,
    MaterializationObserver,
    Page,
    PageBuilder,
    SourceLevel,
)
from parallax.core.internal.read_delivery._paging import PagingParameters, TieFound, page_decision
from parallax.core.internal.read_delivery._read_plan import (
    EmptyRead,
    ReadPlan,
)
from parallax.core.internal.read_delivery._row_converter import (
    FetchedRowObserver,
    ReadRowConverter,
)
from parallax.core.internal.read_delivery._row_decoding import row_coordinates
from parallax.core.internal.sql_gen._compile import CompiledRead
from parallax.core.internal.sql_gen._context import SQL_GENERATION_FAILED
from parallax.core.internal.temporal_read import TemporalShape

__all__ = [
    "EMPTY_PAGE_ORIGIN_COLLECTOR",
    "EagerPageResult",
    "EmptyPageOriginCollector",
    "FetchedRowObserver",
    "HistoryPageResult",
    "PageContinuation",
    "PageOriginCollector",
    "PageReadContext",
    "PageReader",
    "PageResult",
]


class PageOriginCollector[Origin](FetchedRowObserver, Protocol):
    """A fetched row observer that also answers the origins of a sealed Page.

    :meth:`origins_for` is asked once, after the Page it observed is sealed, and
    its mapping travels with the Page by reference, keyed by fetched row index.
    """

    def origins_for(self, page: Page, /) -> Mapping[int, Origin]: ...


class EmptyPageOriginCollector:
    """The collector of a read that retains no origin: it records nothing and
    answers every sealed Page with the same empty mapping.

    Stateless, so one shared instance serves every such Page."""

    __slots__ = ()

    def observe_fetched_row(
        self, fetched_row: int, entity: EntityIdentity, document: object | None
    ) -> None:
        del fetched_row, entity, document

    def origins_for(self, page: Page, /) -> Mapping[int, Never]:
        del page
        return _NO_ORIGINS


_NO_ORIGINS: Final[Mapping[int, Never]] = MappingProxyType({})

EMPTY_PAGE_ORIGIN_COLLECTOR: Final = EmptyPageOriginCollector()


@dataclass(frozen=True, slots=True)
class PageReadContext[Origin]:
    port: DatabaseConnection
    calls: DatabaseCallScope
    origin_collector: PageOriginCollector[Origin] = EMPTY_PAGE_ORIGIN_COLLECTOR


@dataclass(frozen=True, slots=True)
class PageContinuation:
    delivered: int
    resume_from: ContinuationCoordinate | None
    exhausted: bool
    tie: TieFound | None


@dataclass(frozen=True, slots=True)
class PageResult[Origin]:
    page: Page
    includes: read_planning.IncludeTree
    origins: Mapping[int, Origin] = MappingProxyType({})
    documents: tuple[object | None, ...] | None = None
    continuation: PageContinuation | None = None


type EagerPageResult[Origin] = PageResult[Origin]


@dataclass(frozen=True, slots=True)
class HistoryPageResult:
    page: Page
    milestones: TemporalShape
    includes: read_planning.IncludeTree


@dataclass(slots=True)
class _RootRead:
    plan: ReadPlan
    converter: ReadRowConverter
    rows: list[Row]
    coordinates: tuple[ContinuationCoordinate | None, ...]
    observer: MaterializationObserver = INERT_OBSERVER

    def take_rows(self) -> list[Row]:
        rows = self.rows
        self.rows = []
        return rows


def _drain_rows(rows: list[Row]) -> Iterator[Row]:
    """Yield transferred driver rows while releasing each consumed tuple."""
    for index in range(len(rows)):
        row = rows[index]
        rows[index] = cast("Row", ())
        yield row


@dataclass(frozen=True, slots=True)
class _PendingFetch:
    index: int
    step: read_planning.QueryFetchStep
    parents: tuple[int, ...]
    compiled: CompiledRead
    converter: ReadRowConverter


def _pipelined_rows(
    pending: Sequence[_PendingFetch], port: DatabaseConnection, calls: DatabaseCallScope
) -> list[list[Row]]:
    """Run the pending fetches as one pipeline, each inside its own Database Call
    bracket, and answer their rows in pending order."""
    if not pending:
        return []
    with ExitStack() as stack:
        call_contexts: list[DatabaseCallActivity] = []
        for fetch in pending:
            context = calls.database_call(fetch.compiled.statement, "read", fetch.compiled.target)
            call_contexts.append(context.__enter__())
            stack.push(context.__exit__)
        batches = port.execute_pipeline(
            tuple(
                PipelineStatement(
                    fetch.compiled.statement.sql,
                    fetch.compiled.statement.binds,
                    fetch.compiled.document_reads,
                )
                for fetch in pending
            ),
            read_only=True,
        )
        for call, rows in zip(call_contexts, batches, strict=True):
            call.read_completed(rows)
    return batches


def _page_observer(observer: MaterializationObserver) -> MaterializationObserver | None:
    return None if observer is INERT_OBSERVER else observer


def _recorded_rows(
    builder: PageBuilder,
    source: SourceLevel,
    converter: ReadRowConverter,
    rows: Iterable[Row],
    origin_collector: PageOriginCollector[Any],
) -> tuple[int, ...]:
    """Record ``rows`` into ``builder`` at ``source`` under ``converter``, the
    read those provider rows were bound under, reporting each fetched row to
    ``origin_collector`` unless it records nothing.

    The report pairs the SAME row's raw document with the fetched row
    recording produced. Once that fetched row's Page-owned Entity State is
    judged, a consumer reads it by fetched row index; no second member row is
    decoded or reconstructed.
    """
    return converter.record_rows(
        rows,
        builder,
        source,
        None if origin_collector is EMPTY_PAGE_ORIGIN_COLLECTOR else origin_collector,
    )


@dataclass(frozen=True, slots=True)
class PageReader:
    """Execute, record, and seal one plan-driven Page."""

    observer: MaterializationObserver = INERT_OBSERVER

    def read_page[Origin](
        self,
        plan: ReadPlan,
        context: PageReadContext[Origin],
        paging: PagingParameters | None = None,
    ) -> PageResult[Origin]:
        self.observer.prepared(plan.fetch_count + 1)
        collector = (
            context.origin_collector if plan.collects_evidence else EMPTY_PAGE_ORIGIN_COLLECTOR
        )
        root = plan.root_read()
        if isinstance(root, EmptyRead):
            page = plan.page_builder(_page_observer(self.observer)).finish((), plan.pin)
            return PageResult(
                page,
                plan.include_tree(),
                collector.origins_for(page),
                None,
                PageContinuation(0, None, True, None) if paging is not None else None,
            )
        root_read = self._read_root(plan, root, context)
        continuation_result = None
        if paging is not None:
            coordinates = self._coordinates(root_read)
            assert isinstance(plan.query, ResolvedObjectQuery)
            terms = tuple(term.member.identity for term in plan.query.order_by)
            verdict = page_decision(paging, terms, coordinates)
            root_read.rows = root_read.rows[: verdict.keep]
            root_read.coordinates = root_read.coordinates[: verdict.keep]
            continuation_result = PageContinuation(
                verdict.keep,
                coordinates[verdict.keep - 1] if verdict.keep else None,
                verdict.exhausted,
                verdict.tie,
            )
        return self._build_page(root_read, context, collector, continuation_result)

    def _read_root[Origin](
        self,
        plan: ReadPlan,
        root: tuple[CompiledRead, ReadRowConverter],
        context: PageReadContext[Origin],
    ) -> _RootRead:
        compiled, converter = root
        self.observer.statement_rendered(ROOT_LEVEL)
        driver_rows = execute_read(context.port, compiled, context.calls)
        self.observer.statement_executed(ROOT_LEVEL, len(driver_rows))
        return _RootRead(
            plan,
            converter,
            list(driver_rows),
            row_coordinates(compiled.result_contract, driver_rows),
            self.observer,
        )

    @staticmethod
    def _coordinates(root_read: _RootRead) -> tuple[ContinuationCoordinate, ...]:
        coordinates = root_read.coordinates
        if any(coordinate is None for coordinate in coordinates):
            raise InternalError(
                SQL_GENERATION_FAILED,
                "a paging read returned a root carrying no evaluated coordinate",
            )
        return cast("tuple[ContinuationCoordinate, ...]", coordinates)

    @staticmethod
    def _record_roots[Origin](
        root_read: _RootRead,
        builder: PageBuilder,
        rows: list[Row],
        origin_collector: PageOriginCollector[Origin],
    ) -> tuple[tuple[int, ...], tuple[object | None, ...] | None]:
        plan = root_read.plan
        if plan.purpose != "write_support":
            return _recorded_rows(
                builder, ROOT_LEVEL, root_read.converter, _drain_rows(rows), origin_collector
            ), None
        recorded = tuple(
            root_read.converter.record_row(row, builder, source=ROOT_LEVEL)
            for row in _drain_rows(rows)
        )
        root = plan.root_read()
        assert not isinstance(root, EmptyRead)
        documents = (
            tuple(item[2] for item in recorded)
            if root[0].result_contract.shared_document is not None
            else None
        )
        return tuple(item[0] for item in recorded), documents

    def _build_page[Origin](
        self,
        root_read: _RootRead,
        context: PageReadContext[Origin],
        origin_collector: PageOriginCollector[Origin],
        continuation_result: PageContinuation | None,
    ) -> PageResult[Origin]:
        plan = root_read.plan
        meta = plan.model.meta
        port, calls = context.port, context.calls
        includes = plan.include_tree()
        builder = plan.page_builder(_page_observer(root_read.observer))
        root_rows = root_read.take_rows()
        root_refs, documents = self._record_roots(root_read, builder, root_rows, origin_collector)
        del root_rows

        fetch_refs: list[tuple[int, ...]] = [()] * plan.fetch_count
        completed: set[int] = set()
        while len(completed) < plan.fetch_count:
            ready = plan.ready_fetches(completed)
            pending: list[_PendingFetch] = []
            for index in ready:
                step = plan.fetch_step(index)
                parents = guarded_parents(
                    builder,
                    includes,
                    step,
                    parent_refs(step.parent, root_refs, fetch_refs),
                )
                completed.add(index)
                if not parents:
                    continue
                prepared = plan.prepared_fetch(index)
                if isinstance(prepared, EmptyRead):
                    attach_empty(builder, includes, step, parents)
                    continue
                if prepared is None:
                    assert isinstance(step, read_planning.BackReferenceFetchStep)
                    attach_back_reference(builder, meta, includes, step, parents)
                    continue
                assert isinstance(step, read_planning.QueryFetchStep)
                keys = gather_keys(
                    builder,
                    parents,
                    correlation_member(meta, step.owner.identity),
                )
                if not keys:
                    attach_empty(builder, includes, step, parents)
                    continue
                template, converter = prepared
                root_read.observer.statement_rendered(index + 1)
                pending.append(
                    _PendingFetch(
                        index,
                        step,
                        parents,
                        template.render(keys, query=plan.query),
                        converter,
                    )
                )

            if len(pending) == 1:
                batches = [execute_read(port, pending[0].compiled, calls)]
            else:
                batches = _pipelined_rows(pending, port, calls)
            for fetch, rows in zip(pending, batches, strict=True):
                root_read.observer.statement_executed(fetch.index + 1, len(rows))
                child_refs = _recorded_rows(
                    builder, fetch.index + 1, fetch.converter, rows, origin_collector
                )
                attach_children(builder, meta, includes, fetch.step, fetch.parents, child_refs)
                fetch_refs[fetch.index] = child_refs

        page = builder.finish(root_refs, plan.pin)
        return PageResult(
            page, includes, origin_collector.origins_for(page), documents, continuation_result
        )
