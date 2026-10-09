from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from contextlib import ExitStack
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Any, Protocol, cast, overload

from parallax.core import deep_fetch
from parallax.core.db_port import DatabaseConnection, PipelineStatement, Row
from parallax.core.entity._layout import CatalogedModel
from parallax.core.execution_lifecycle._activity import (
    DatabaseCallActivity,
    DatabaseCallScope,
)
from parallax.core.metamodel import EntityIdentity
from parallax.core.object_query._resolved import (
    ContinuationCoordinate,
    ResolvedObjectQuery,
    ResolvedTemporalSelection,
)
from parallax.core.read_delivery._fetch import (
    attach_back_reference,
    attach_children,
    attach_empty,
    correlation_member,
    execute_read,
    gather_keys,
    guarded_parents,
    parent_refs,
)
from parallax.core.read_delivery._page import (
    INERT_OBSERVER,
    ROOT_LEVEL,
    MaterializationObserver,
    Page,
    PageBuilder,
    SourceLevel,
    ViewSchema,
)
from parallax.core.read_delivery._paging import At, PagingPlan, TieFound, page_decision
from parallax.core.read_delivery._read_plan import ReadPlan, ReadPlanner
from parallax.core.read_delivery._row_converter import ReadRowConverter, bind
from parallax.core.sql_gen import SqlGenError
from parallax.core.sql_gen._compile import CompiledRead
from parallax.core.temporal_read import Pin, TemporalShape, resolved_query_pin
from parallax.core.unit_work import Concurrency

__all__ = [
    "EagerPageRequest",
    "EagerPageResult",
    "FlatPageRequest",
    "FlatPageResult",
    "HistoryPageResult",
    "PageOrigins",
    "PageProjectionObserver",
    "PageReader",
    "StreamPageRequest",
    "StreamPageResult",
    "convert_rows",
]


class PageProjectionObserver(Protocol):
    """What Page conversion reports about each projection it registers."""

    def observe_projection(
        self, node: int, entity: EntityIdentity, document: object | None
    ) -> None: ...


class PageOrigins[Origin](PageProjectionObserver, Protocol):
    """A projection observer that also answers the origins of a sealed Page.

    :meth:`origins_for` is asked once, after the Page it observed is sealed, and
    its mapping travels with the Page by reference, keyed by projection index.
    """

    def origins_for(self, page: Page, /) -> Mapping[int, Origin]: ...


@dataclass(frozen=True, slots=True)
class EagerPageRequest[Origin]:
    """Inputs for one eager Page read."""

    query: ResolvedObjectQuery
    model: CatalogedModel
    port: DatabaseConnection
    preference: Concurrency | None
    origins: PageOrigins[Origin]
    calls: DatabaseCallScope
    planner: ReadPlanner
    edition: str = ""


@dataclass(frozen=True, slots=True)
class EagerPageResult[Origin]:
    """An eager read's sealed delivery Page.

    ``includes`` is the query's own Include Paths as the relationship views a
    wire unwind follows. The Page alone cannot supply them: it keeps every view
    any level loaded onto a node, so a back-reference would revisit its target
    forever. The reader knows the plan, so it hands the tree on.

    ``sources`` is the origin each observed projection's value will carry,
    keyed by that projection's own index in the Page, exactly as the request's
    origin capability answered it.
    """

    page: Page
    includes: deep_fetch.IncludeTree
    sources: Mapping[int, Origin] = MappingProxyType({})


@dataclass(frozen=True, slots=True)
class HistoryPageResult:
    """A milestone-set read's one database-ordered Page of flat roots.

    ``milestones`` is the target family's Temporal Shape, whose axis starts are
    each root's own edge.
    """

    page: Page
    milestones: TemporalShape
    includes: deep_fetch.IncludeTree


@dataclass(frozen=True, slots=True)
class FlatPageRequest:
    """Inputs for one statement whose rows form a root-only Page."""

    model: CatalogedModel
    compiled: CompiledRead
    read: Callable[[], Sequence[Row]]
    pin: Pin
    converter: ReadRowConverter | None = None


@dataclass(frozen=True, slots=True)
class FlatPageResult:
    """One flat batch and the Page-owned Entity States that judge it.

    Each row's `familyVariant` and shared document are retained beside the Page.
    Provider rows end at Page assembly.
    """

    variants: tuple[str | None, ...]
    documents: tuple[object | None, ...]
    page: Page


@dataclass(frozen=True, slots=True)
class StreamPageRequest[Origin]:
    """Inputs for one bounded Page in an already planned delivery."""

    paging: PagingPlan
    at: At
    model: CatalogedModel
    port: DatabaseConnection
    preference: Concurrency | None
    origins: PageOrigins[Origin]
    calls: DatabaseCallScope
    planner: ReadPlanner
    edition: str = ""


@dataclass(frozen=True, slots=True)
class StreamPageResult[Origin]:
    """One streamed Page and the minimal state needed to continue its delivery."""

    page: Page
    includes: deep_fetch.IncludeTree
    sources: Mapping[int, Origin]
    delivered: int
    resume_from: ContinuationCoordinate | None
    exhausted: bool
    tie: TieFound | None


@dataclass(slots=True)
class _RootRead:
    plan: ReadPlan
    converter: ReadRowConverter
    rows: list[Row]
    coordinates: tuple[ContinuationCoordinate | None, ...]
    temporal: tuple[ResolvedTemporalSelection, ...]
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
    step: deep_fetch.QueryFetchStep
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
                    port.dialect.to_driver_sql(fetch.compiled.statement.sql),
                    fetch.compiled.statement.binds,
                    fetch.compiled.document_reads,
                )
                for fetch in pending
            )
        )
        for call, rows in zip(call_contexts, batches, strict=True):
            call.read_completed(rows)
    return batches


def _page_observer(observer: MaterializationObserver) -> MaterializationObserver | None:
    return None if observer is INERT_OBSERVER else observer


def convert_rows(
    builder: PageBuilder,
    source: SourceLevel,
    converter: ReadRowConverter,
    rows: Iterable[Row],
    observer: PageProjectionObserver,
) -> tuple[int, ...]:
    """Convert ``rows`` into ``builder``, reporting each one while it is still live.

    ``converter`` is the read those provider rows convert and are observed
    under: the layout, projected documents, and attribute contracts a row needs
    were derived when that read was bound, so nothing here re-derives what the
    statement projected.

    ``source`` is where in the plan these rows land, which is what sizes each
    projection's view row: the levels attaching BELOW this one are what its rows
    can receive.

    The report pairs the SAME row's raw document with the projection conversion
    produced. Once that projection's Page-owned Entity State is judged, a
    consumer reads it by projection index; no second member row is decoded or
    reconstructed.

    Each row is reported under its OWN resolved concrete Entity — the mapping
    the conversion resolved for it — rather than under the level-wide position
    the query addressed. The root and every level run through here, so that one
    rule reaches an abstract-target root's concrete, a polymorphic level's
    concrete, and an included child alike.
    """
    refs: list[int] = []
    for row in rows:
        ref, resolved, document, _variant = converter.convert_row(row, builder, source=source)
        refs.append(ref)
        observer.observe_projection(ref, resolved, document)
    return tuple(refs)


@dataclass(frozen=True, slots=True)
class PageReader:
    """Plans, executes, converts, and seals one Page per request."""

    observer: MaterializationObserver = INERT_OBSERVER

    @overload
    def read_page[Origin](self, request: EagerPageRequest[Origin]) -> EagerPageResult[Origin]: ...

    @overload
    def read_page(self, request: FlatPageRequest) -> FlatPageResult: ...

    @overload
    def read_page[Origin](self, request: StreamPageRequest[Origin]) -> StreamPageResult[Origin]: ...

    def read_page(
        self,
        request: EagerPageRequest[Any] | FlatPageRequest | StreamPageRequest[Any],
    ) -> EagerPageResult[Any] | FlatPageResult | StreamPageResult[Any]:
        """Plan, execute, and assemble one Page from typed inputs."""
        if isinstance(request, EagerPageRequest):
            roots = self._read_root(
                request.query,
                request.model,
                request.port,
                preference=request.preference,
                calls=request.calls,
                edition=request.edition,
                planner=request.planner,
            )
            return self._build_page(
                roots, request.model, request.port, origins=request.origins, calls=request.calls
            )
        if isinstance(request, FlatPageRequest):
            self.observer.prepared(1)
            self.observer.statement_rendered(ROOT_LEVEL)
            rows = request.read()
            self.observer.statement_executed(ROOT_LEVEL, len(rows))
            converter = request.converter or bind(request.model, request.compiled)
            builder = PageBuilder(ViewSchema.of(), _page_observer(self.observer))
            converted = tuple(
                converter.convert_row(row, builder, source=ROOT_LEVEL) for row in rows
            )
            return FlatPageResult(
                tuple(item[3] for item in converted),
                tuple(item[2] for item in converted),
                builder.finish(tuple(item[0] for item in converted), request.pin),
            )

        return self._read_stream_page(request)

    def _read_root(
        self,
        query: ResolvedObjectQuery,
        model: CatalogedModel,
        port: DatabaseConnection,
        *,
        preference: Concurrency | None = None,
        calls: DatabaseCallScope,
        edition: str = "",
        planner: ReadPlanner,
        plan: ReadPlan | None = None,
    ) -> _RootRead:
        """Plan and execute the root statement for one Page."""
        if plan is None:
            plan = planner.plan(
                edition=edition,
                model=model,
                dialect=port.dialect,
                query=query,
                result_form="instance",
                preference=preference,
            )
        compiled_read, converter = plan.root_read()
        self.observer.prepared(plan.fetch_count + 1)
        self.observer.statement_rendered(ROOT_LEVEL)
        driver_rows = execute_read(port, compiled_read, calls)
        self.observer.statement_executed(ROOT_LEVEL, len(driver_rows))
        return _RootRead(
            plan=plan,
            converter=converter,
            rows=list(driver_rows),
            coordinates=compiled_read.row_coordinates(driver_rows),
            temporal=query.temporal,
            observer=self.observer,
        )

    @staticmethod
    def _coordinates(root_read: _RootRead) -> tuple[ContinuationCoordinate, ...]:
        coordinates = root_read.coordinates
        if any(coordinate is None for coordinate in coordinates):
            raise SqlGenError("a paging read returned a root carrying no evaluated coordinate")
        return cast("tuple[ContinuationCoordinate, ...]", coordinates)

    def _build_page[Origin](
        self,
        root_read: _RootRead,
        model: CatalogedModel,
        port: DatabaseConnection,
        *,
        origins: PageOrigins[Origin],
        calls: DatabaseCallScope,
    ) -> EagerPageResult[Origin]:
        """Convert roots and execute every reachable fetch step into one Page."""
        meta = model.meta
        plan = root_read.plan
        includes = plan.include_tree()
        builder = plan.page_builder(_page_observer(root_read.observer))
        root_rows = root_read.take_rows()
        root_refs = convert_rows(
            builder, ROOT_LEVEL, root_read.converter, _drain_rows(root_rows), origins
        )
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
                if isinstance(step, deep_fetch.BackReferenceFetchStep):
                    attach_back_reference(builder, meta, includes, step, parents)
                    completed.add(index)
                    continue
                keys = gather_keys(
                    builder,
                    parents,
                    correlation_member(meta, step.owner.identity),
                )
                if not keys:
                    attach_empty(builder, includes, step, parents)
                    completed.add(index)
                    continue
                compiled, converter = plan.fetch_read(index, keys)
                root_read.observer.statement_rendered(index + 1)
                pending.append(_PendingFetch(index, step, parents, compiled, converter))

            if len(pending) == 1:
                batches = [execute_read(port, pending[0].compiled, calls)]
            else:
                batches = _pipelined_rows(pending, port, calls)
            for fetch, rows in zip(pending, batches, strict=True):
                root_read.observer.statement_executed(fetch.index + 1, len(rows))
                child_refs = convert_rows(builder, fetch.index + 1, fetch.converter, rows, origins)
                attach_children(builder, meta, includes, fetch.step, fetch.parents, child_refs)
                fetch_refs[fetch.index] = child_refs
                completed.add(fetch.index)

        page = builder.finish(root_refs, resolved_query_pin(root_read.temporal))
        return EagerPageResult(page=page, includes=includes, sources=origins.origins_for(page))

    def _read_stream_page[Origin](
        self, request: StreamPageRequest[Origin]
    ) -> StreamPageResult[Origin]:
        """Execute one streamed Page and retain only its continuation boundary."""
        paging = request.paging
        parameters = paging.parameters_for(request.at.emitted)
        query = (
            paging.plan.first(limit=parameters.size)
            if request.at.coordinate is None
            else paging.plan.after(request.at.coordinate, limit=parameters.size)
        )
        root_read = self._read_root(
            query,
            request.model,
            request.port,
            preference=request.preference,
            calls=request.calls,
            edition=request.edition,
            planner=request.planner,
        )
        coordinates = self._coordinates(root_read)
        terms = tuple(term.member.identity for term in query.order_by)
        verdict = page_decision(parameters, terms, coordinates)
        kept = replace(
            root_read,
            rows=root_read.rows[: verdict.keep],
            coordinates=root_read.coordinates[: verdict.keep],
        )
        discarded_rows = root_read.take_rows()
        del discarded_rows, root_read
        result = self._build_page(
            kept, request.model, request.port, origins=request.origins, calls=request.calls
        )
        return StreamPageResult(
            page=result.page,
            includes=result.includes,
            sources=result.sources,
            delivered=verdict.keep,
            resume_from=coordinates[verdict.keep - 1] if verdict.keep else None,
            exhausted=verdict.exhausted,
            tie=verdict.tie,
        )
